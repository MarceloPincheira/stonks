"""Proyección del saldo AFP: cotizaciones, rentabilidad y pago de la pensión.

Trabaja en pesos de hoy: la cotización se mantiene constante en poder adquisitivo (el
sueldo se reajusta con la inflación) y el fondo rinde su tasa real.
"""
from .parametros import (APORTE_EMPLEADOR_CUENTA, CESANTIA_INDEFINIDO, COTIZACION_OBLIGATORIA,
                         EDAD_PENSION, EDAD_SALIDA_FONDO_A, EXPECTATIVA_VIDA, SALUD,
                         TASA_TECNICA, TOPE_CESANTIA_UF, TOPE_IMPONIBLE_UF, UTM_REFERENCIA)
from .fondos import fondo_a_edad, fondo_por_defecto, rentabilidad_a_edad
from .pension import pension_mensual
from .tributario import impuesto_unico

def proyectar(perfil, hasta_edad=None, trabajo_hasta=None):
    """Proyecta el saldo de la AFP mes a mes hasta la edad de pensión, y desde ahí
    hasta `hasta_edad` (por defecto la expectativa de vida) consumiéndolo en pensiones.

    `trabajo_hasta` es la edad en que se deja de cotizar (por defecto, la de pensión).
    Si es menor, el saldo sigue rentando hasta jubilar pero sin plata nueva: la pensión
    se calcula igual a la edad legal, porque adelantarla tiene requisitos propios que
    esto no modela.

    Trabaja en pesos de hoy: la cotización se mantiene constante en poder adquisitivo
    (el sueldo se reajusta con la inflación) y el fondo rinde su tasa real.
    """
    sexo = perfil["sexo"]
    edad = perfil["edad"]
    edad_pension = EDAD_PENSION[sexo]
    meses = max(0, int(round((edad_pension - edad) * 12)))
    fin_trabajo = edad_pension if not trabajo_hasta else min(trabajo_hasta, edad_pension)

    uf = perfil["uf"]
    tope = TOPE_IMPONIBLE_UF * uf
    # Sólo la renta imponible paga cotizaciones, y sólo hasta el tope. Las
    # asignaciones no imponibles (colación, movilización) no cotizan ni descuentan:
    # entran enteras al líquido.
    sueldo_imponible = perfil["sueldo_imponible"]
    no_imponible = perfil.get("no_imponible", 0.0) or 0.0
    imponible = min(sueldo_imponible, tope)

    cotizacion = imponible * COTIZACION_OBLIGATORIA / 100
    comision = imponible * perfil["comision_afp"] / 100
    aporte_empleador = imponible * perfil["aporte_empleador"] / 100
    salud_legal = imponible * SALUD / 100
    # El adicional de Isapre se paga por sobre el 7% legal y sale del mismo líquido,
    # pero no es cotización obligatoria: no rebaja la base del impuesto.
    adicional = (perfil.get("salud_extra", 0.0) or 0.0) if perfil.get("salud") == "isapre" else 0.0
    salud = salud_legal + adicional
    imponible_cesantia = min(sueldo_imponible, TOPE_CESANTIA_UF * uf)
    cesantia = (imponible_cesantia * CESANTIA_INDEFINIDO / 100
                if perfil["contrato_indefinido"] else 0.0)

    base_tributable = sueldo_imponible - cotizacion - comision - salud_legal - cesantia
    impuesto = impuesto_unico(base_tributable, perfil.get("utm", UTM_REFERENCIA))

    saldo = perfil["saldo_afp"]
    filas = []
    saldos_acumulacion = []
    meses_cotizando = 0
    for m in range(1, meses + 1):
        edad_actual = edad + (m - 1) / 12
        tasa_anual = rentabilidad_a_edad(
            edad_actual, perfil["fondo"], sexo, perfil.get("trayectoria", "fijo"),
            perfil.get("destino_salida_a", "B")) / 100
        tasa_mensual = (1 + tasa_anual) ** (1 / 12) - 1
        # sin trabajo no hay cotización, pero el saldo sigue rentando
        entra = (cotizacion + aporte_empleador) if edad_actual < fin_trabajo else 0.0
        if entra:
            meses_cotizando += 1
        saldo = (saldo + entra) * (1 + tasa_mensual)
        saldos_acumulacion.append(saldo)
        if m % 12 == 0 or m == meses:
            filas.append({
                "mes": m,
                "edad": round(edad + m / 12, 1),
                "fondo": fondo_a_edad(
                    edad + m / 12, perfil["fondo"], sexo, perfil.get("trayectoria", "fijo"),
                    perfil.get("destino_salida_a", "B")),
                "tasa_real": round(tasa_anual * 100, 2),
                "saldo": round(saldo, 2),
                "pension": 0.0,
                "fase": "acumulación",
            })

    # Saldo y pensión van en pesos de hoy: la tasa técnica también es real.
    pension = pension_mensual(saldo, sexo)
    cnu = (saldo / pension / 12) if pension > 0 else 0.0
    saldo_al_jubilar = saldo

    # Fase de retiro: el saldo sigue rentando a la tasa técnica mientras paga la
    # pensión, así que se agota justo al llegar a la expectativa de vida. Es la
    # contracara del CNU: el mismo supuesto, visto mes a mes.
    edad_final = (edad_pension + EXPECTATIVA_VIDA[sexo]) if hasta_edad is None else hasta_edad
    meses_retiro = max(0, int(round((edad_final - edad_pension) * 12)))
    tasa_retiro = (1 + TASA_TECNICA / 100) ** (1 / 12) - 1
    saldos_retiro = []
    for k in range(1, meses_retiro + 1):
        saldo = max(0.0, saldo * (1 + tasa_retiro) - pension)
        saldos_retiro.append(saldo)
        edad_k = edad_pension + k / 12
        if k % 12 == 0 or k == meses_retiro:
            filas.append({
                "mes": meses + k,
                "edad": round(edad_k, 1),
                "fondo": "pensionado",
                "tasa_real": TASA_TECNICA,
                "saldo": round(saldo, 2),
                "pension": round(pension, 2),
                "fase": "retiro",
            })

    aportado = (cotizacion + aporte_empleador) * meses_cotizando
    return {
        "meses_hasta_pension": meses,
        "trabajo_hasta": round(fin_trabajo, 2),
        "meses_cotizando": meses_cotizando,
        "edad_pension": edad_pension,
        "imponible": round(imponible, 2),
        "no_imponible": round(no_imponible, 2),
        "bruto_total": round(sueldo_imponible + no_imponible, 2),
        "topado": sueldo_imponible > tope,
        "tope_imponible": round(tope, 2),
        "tope_cesantia": round(TOPE_CESANTIA_UF * uf, 2),
        "topado_cesantia": sueldo_imponible > TOPE_CESANTIA_UF * uf,
        "descuentos": {
            "cotizacion": round(cotizacion, 2),
            "comision": round(comision, 2),
            "salud": round(salud, 2),
            "cesantia": round(cesantia, 2),
            "impuesto": round(impuesto, 2),
            "total": round(cotizacion + comision + salud + cesantia + impuesto, 2),
        },
        "base_tributable": round(base_tributable, 2),
        "utm": perfil.get("utm", UTM_REFERENCIA),
        "liquido_aprox": round(
            sueldo_imponible + no_imponible - cotizacion - comision - salud - cesantia - impuesto,
            2),
        "aporte_empleador_mensual": round(aporte_empleador, 2),
        "saldo_actual": round(perfil["saldo_afp"], 2),
        "saldo_al_jubilar": round(saldo_al_jubilar, 2),
        # Saldo mes a mes desde hoy hasta la expectativa de vida, para el gráfico.
        "serie_mensual": [round(x, 2) for x in saldos_acumulacion + saldos_retiro],
        "edad_final": round(edad_final, 2),
        "meses_retiro": meses_retiro,
        "total_cotizado": round(aportado, 2),
        "rentabilidad_ganada": round(saldo_al_jubilar - perfil["saldo_afp"] - aportado, 2),
        "fondo_elegido": perfil["fondo"],
        # Con un esquema de traspasos por edad la elección de fondo no se aplica: el
        # esquema asigna por edad. Se informa cuál se usó de verdad para que la UI
        # pueda decirlo en vez de callarlo.
        "fondo_ignorado": perfil.get("trayectoria", "fijo") != "fijo",
        "fondo_inicial": fondo_a_edad(
            edad, perfil["fondo"], sexo, perfil.get("trayectoria", "fijo"),
            perfil.get("destino_salida_a", "B")),
        "fondo_final": fondo_a_edad(
            edad_pension, perfil["fondo"], sexo, perfil.get("trayectoria", "fijo"),
            perfil.get("destino_salida_a", "B")),
        "pension_mensual": round(pension, 2),
        "cnu": round(cnu, 2),
        "expectativa_vida": EXPECTATIVA_VIDA[sexo],
        "tasa_tecnica": TASA_TECNICA,
        "sale_de_a": (perfil.get("trayectoria", "fijo") == "fijo"
                      and perfil["fondo"] == "A" and edad < EDAD_SALIDA_FONDO_A[sexo]),
        "edad_salida_a": EDAD_SALIDA_FONDO_A[sexo],
        "trayectoria": perfil.get("trayectoria", "fijo"),
        "fondo_por_defecto": fondo_por_defecto(edad, sexo),
        "detalle": filas,
    }
