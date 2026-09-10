"""La costura entre el perfil previsional y el escenario de inversión.

Aquí se valida el perfil y se alinean las dos líneas de tiempo: la serie de la AFP arranca
hoy y la proyección de la inversión en la fecha que fije el perfil.
"""
from datetime import date

import afp
import db
import engine

def con_perfil(payload):
    """Agrega al payload lo que sale del perfil: cuándo parte la inversión y la pensión.

    La fecha de inicio hace falta para ubicar los aportes extraordinarios, que se
    escriben como mes de calendario y no como número de mes de la proyección.

    La pensión no se guarda en el escenario: sale del perfil, así que cambiar de AFP o
    de fondo la actualiza en todos los escenarios a la vez. El escenario sólo recuerda
    si hay que considerarla.
    """
    datos = db.get_profile()
    perfil = datos.get("profile")
    if not perfil:
        return payload
    payload = {**payload,
               "start_year": perfil["inicio_anio"], "start_month": perfil["inicio_mes"]}
    try:
        proyeccion = afp.proyectar(perfil, trabajo_hasta=payload.get("work_until_age") or None)
    except (KeyError, ValueError):
        return payload

    # La serie de la AFP arranca hoy y la inversión en inicio_mes/inicio_anio: hay que
    # alinearlas antes de mandarlas al motor, que sólo entiende meses de proyección.
    #
    # Dos cuidados que antes no estaban:
    #   * `serie_mensual` parte en el mes SIGUIENTE a hoy, así que el saldo de hoy hay
    #     que ponerlo delante; sin eso toda la curva quedaba corrida un mes.
    #   * si la inversión empezó ANTES que hoy no hay saldo AFP que mostrar en esos
    #     meses: van en None (hueco en el gráfico), no descartados. Descartarlos sin
    #     dejar el hueco desplazaba la curva entera hacia atrás, y el desplazamiento
    #     crecía un mes por cada mes que pasaba sin volver a guardar el perfil.
    hoy = date.today()
    desfase = (perfil["inicio_anio"] - hoy.year) * 12 + (perfil["inicio_mes"] - hoy.month)
    # índice t = meses transcurridos desde hoy; t = 0 es el saldo actual
    serie = [proyeccion["saldo_actual"]] + proyeccion["serie_mensual"]
    alineada = [
        serie[j] if 0 <= (j := desfase + k) < len(serie) else None
        for k in range(len(serie) - desfase)
    ]
    # Si la proyección arranca en el pasado, ahí el afiliado era más joven: usar la
    # edad de hoy descuadraba la edad de jubilación y la de agotamiento del patrimonio.
    edad_inicio = perfil["edad"] + desfase / 12

    # Mes de la proyección en que se cumple la edad de pensión. La inversión parte en
    # inicio_mes/inicio_anio, que no tiene por qué coincidir con el cumpleaños.
    y, m, _ = (int(x) for x in str(perfil["nacimiento"]).split("-")[:3])
    anio_pension = y + afp.EDAD_PENSION[perfil["sexo"]]
    desde = ((anio_pension - perfil["inicio_anio"]) * 12
             + (m - perfil["inicio_mes"]) + 1)
    # Mes de la proyección en que se deja de trabajar: ahí se cortan las cotizaciones
    # y también los aportes al fondo, que salen del mismo sueldo.
    fin_trabajo = proyeccion["trabajo_hasta"]
    hasta_mes = int(round((fin_trabajo - edad_inicio) * 12))

    return {**payload,
            "pension_monthly": proyeccion["pension_mensual"],
            "pension_start_month": max(1, desde),
            "start_age": round(edad_inicio, 2),
            "life_age": proyeccion["edad_final"],
            "work_until_age": fin_trabajo,
            "work_until_month": max(0, hasta_mes),
            "afp_monthly": alineada,
            "afp_summary": {k: proyeccion[k] for k in (
                "saldo_actual", "saldo_al_jubilar", "pension_mensual", "edad_pension",
                "fondo_inicial", "fondo_final", "topado", "tope_imponible", "descuentos",
                "trabajo_hasta", "meses_cotizando", "cnu", "expectativa_vida")}}


def normalizar_perfil(payload):
    """Valida el perfil; los campos numéricos llegan como texto desde el formulario."""
    def num(key, default=0.0, minimo=None, maximo=None):
        try:
            v = float(payload.get(key, default) or default)
        except (TypeError, ValueError):
            raise engine.ValidationError(f"El campo '{key}' debe ser numérico.")
        if minimo is not None and v < minimo:
            raise engine.ValidationError(f"El campo '{key}' no puede ser menor que {minimo}.")
        if maximo is not None and v > maximo:
            raise engine.ValidationError(f"El campo '{key}' no puede ser mayor que {maximo}.")
        return v

    sexo = payload.get("sexo") or "hombre"
    if sexo not in afp.EDAD_PENSION:
        raise engine.ValidationError("Sexo no reconocido para los tramos legales.")
    fondo = (payload.get("fondo") or "B").upper()
    if fondo not in afp.RENTABILIDAD_REAL:
        raise engine.ValidationError("El fondo debe ser A, B, C, D o E.")
    trayectoria = payload.get("trayectoria") or "fijo"
    if trayectoria not in ("fijo", "basico", "ampliado"):
        raise engine.ValidationError("Trayectoria de fondos no reconocida.")
    destino_salida_a = (payload.get("destino_salida_a") or "B").upper()
    if destino_salida_a not in ("B", "C", "D", "E"):
        raise engine.ValidationError("Al salir del fondo A el destino debe ser B, C, D o E.")

    nacimiento = (payload.get("nacimiento") or "").strip()
    try:
        edad = afp.edad_desde(nacimiento)
    except (ValueError, IndexError, AttributeError):
        raise engine.ValidationError("Ingresa una fecha de nacimiento válida.")
    if not 15 <= edad <= 100:
        raise engine.ValidationError("La edad derivada de esa fecha está fuera de rango (15 a 100).")
    if edad >= afp.EDAD_PENSION[sexo]:
        raise engine.ValidationError(
            f"La edad ya alcanzó la de pensión ({afp.EDAD_PENSION[sexo]}): no hay años por proyectar."
        )
    return {
        "edad": edad,
        "nacimiento": nacimiento,
        "sexo": sexo,
        "inicio_mes": int(num("inicio_mes", 1, 1, 12)),
        "inicio_anio": int(num("inicio_anio", 2026, 1900, 2200)),
        "sueldo_imponible": num("sueldo_imponible", num("sueldo_bruto", 0, 0), 0),
        "no_imponible": num("no_imponible", 0, 0),
        "afp": (payload.get("afp") or "Habitat")[:40],
        "comision_afp": num("comision_afp", 1.27, 0, 10),
        "fondo": fondo,
        "saldo_afp": num("saldo_afp", 0, 0),
        "salud": (payload.get("salud") or "fonasa")[:20],
        "salud_extra": num("salud_extra", 0, 0),
        "contrato_indefinido": bool(payload.get("contrato_indefinido", True)),
        "aporte_empleador": num("aporte_empleador", afp.APORTE_EMPLEADOR_CUENTA, 0, 20),
        "uf": num("uf", afp.UF_REFERENCIA, 1),
        "utm": num("utm", afp.UTM_REFERENCIA, 1),
        "trayectoria": trayectoria,
        "destino_salida_a": destino_salida_a,
    }
