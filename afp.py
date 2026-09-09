"""Parámetros legales del sistema previsional chileno y proyección del saldo AFP.

Todas las rentabilidades de los fondos son REALES (por sobre la inflación), tal como
las publica la Superintendencia de Pensiones. Eso es cómodo aquí: al proyectar en
pesos de hoy no hay que sumarles inflación, y al pasar a nominales se compone con
ella: (1+real)*(1+inflación)-1.
"""

# Rentabilidad real anualizada del SISTEMA desde el inicio de los multifondos
# (septiembre 2002), según la Superintendencia de Pensiones.
RENTABILIDAD_REAL = {"A": 5.95, "B": 5.11, "C": 4.30, "D": 3.47, "E": 2.80}

# Ley 21.735: los multifondos A-E se reemplazan por diez fondos generacionales
# asignados por año de nacimiento, sin elección en el ahorro obligatorio. La
# proyección sigue usando la trayectoria de los multifondos porque los nuevos aún
# no tienen rentabilidad observada. Formato AAAA-MM; el frontend lo escribe en prosa.
FONDOS_GENERACIONALES_DESDE = "2027-04"

# Comisión sobre la renta imponible. Se descuenta del sueldo pero NO entra a la
# cuenta individual: es el precio de administración. Conviene verificarla, cambia.
COMISIONES = {
    "Uno": 0.49, "Modelo": 0.58, "PlanVital": 1.16, "Habitat": 1.27,
    "Capital": 1.44, "Cuprum": 1.44, "ProVida": 1.45,
}

COTIZACION_OBLIGATORIA = 10.0   # a la cuenta individual
SALUD = 7.0                     # FONASA o Isapre (el plan puede costar más)
CESANTIA_INDEFINIDO = 0.6       # seguro de cesantía, contrato indefinido
TOPE_IMPONIBLE_UF = 90.0        # tope 2026 para AFP y salud
# El seguro de cesantía se rige por su propio tope, bastante más alto: usar el de la
# AFP subestima el descuento de quien gana entre 90 y 135,2 UF. (AFC / SP, 2026.)
TOPE_CESANTIA_UF = 135.2

# Ley 21.735 (2025): la cotización del empleador sube gradualmente hasta 8,5% en
# 2033, pero sólo una fracción llega a la cuenta individual; el resto financia el
# Seguro Social Previsional y el FAPP. Hoy esa fracción es 0,1%.
APORTE_EMPLEADOR_CUENTA = 0.1

EDAD_PENSION = {"hombre": 65, "mujer": 60}

# Impuesto Único de Segunda Categoría (art. 52 LIR, tabla mensual del SII). La escala
# está en UTM, así que no envejece con la inflación: basta con actualizar la UTM.
# Cada fila: (tope del tramo en UTM, factor, rebaja en UTM). None = último tramo.
# El SII la publica en forma directa -- impuesto = base * factor - rebaja -- y las
# rebajas empalman los tramos: 0,04*30-0,54 = 0,08*30-1,74 = 0,66 UTM, y así.
# Ojo con los dos últimos tramos: el del 35% llega hasta 310 UTM (no 150), y por eso
# la rebaja del 40% es 38,82 -- 0,35*310-23,32 = 0,40*310-38,82 = 85,18 UTM. Cortarlo
# antes deja la escala continua igual, así que el error no se delata solo.
IUSC = [
    (13.5, 0.000, 0.00),      # exento
    (30.0, 0.040, 0.54),
    (50.0, 0.080, 1.74),
    (70.0, 0.135, 4.49),
    (90.0, 0.230, 11.14),
    (120.0, 0.304, 17.80),
    (310.0, 0.350, 23.32),
    (None, 0.400, 38.82),
]

# Valores de referencia, editables en el perfil porque cambian todos los meses.
UTM_REFERENCIA = 71721.0     # septiembre 2026, SII
UF_REFERENCIA = 40884.32     # 8 de septiembre de 2026, Banco Central

# Asignación por defecto del DL 3.500, art. 23, para quien nunca eligió fondo:
#   B  hombres y mujeres HASTA los 35
#   C  hombres DESDE 36 HASTA 55  ·  mujeres DESDE 36 HASTA 50
#   D  hombres DESDE 56           ·  mujeres DESDE 51
TRAMOS = {
    "hombre": {"b_hasta": 35, "c_hasta": 55, "traspaso_desde": 56},
    "mujer": {"b_hasta": 35, "c_hasta": 50, "traspaso_desde": 51},
}

# Regla obligatoria del art. 23: al cumplir 56 (hombres) o 51 (mujeres), el saldo por
# cotizaciones obligatorias que esté en el Fondo A debe salir de ahí en 90 días.
EDAD_SALIDA_FONDO_A = {"hombre": 56, "mujer": 51}

# Esquema de traspasos futuros según edad (Compendio de Pensiones, cap. II). No es
# automático para todos: se contrata con la AFP. El traspaso es GRADUAL en cinco
# etapas de 20% -- 20% al cumplir la edad, y 20% más cada año hasta completar el
# 100% a los cuatro años. Las cotizaciones nuevas van de inmediato al fondo nuevo.
ETAPAS_TRASPASO = 4          # años que tarda en completarse
PASO_ANUAL = 0.20            # fracción del saldo que se mueve cada año

HITOS = {
    "basico": {
        "hombre": [(0, "B"), (36, "C"), (56, "D")],
        "mujer": [(0, "B"), (36, "C"), (51, "D")],
    },
    "ampliado": {
        "hombre": [(0, "A"), (31, "B"), (36, "C"), (56, "D"), (61, "E")],
        "mujer": [(0, "A"), (31, "B"), (36, "C"), (51, "D"), (56, "E")],
    },
}


# --- pensión ---------------------------------------------------------------
# Tasa de Interés Técnica del Retiro Programado (TITRP): la fija la SP cada trimestre
# ponderando la tasa implícita de las rentas vitalicias del año anterior con la
# rentabilidad promedio de los fondos de los últimos cinco años. Es una tasa REAL
# --el sistema opera en UF--, así que calza con proyectar en pesos de hoy.
TASA_TECNICA = 3.45          # tercer trimestre de 2026, Circular N° 2.417 de la SP

# Expectativa de vida a la edad de pensión, tablas de mortalidad 2020 con sus
# factores de mejoramiento: hombre de 65 vive hasta ~86,6; mujer de 60, hasta ~90,8.
EXPECTATIVA_VIDA = {"hombre": 21.6, "mujer": 30.8}


def pension_mensual(saldo, sexo, tasa=None):
    """Pensión mensual que financia un saldo, en la misma moneda del saldo.

    La AFP divide el saldo por doce veces el **Capital Necesario Unitario**: el valor
    presente de una pensión de una unidad anual, ponderando cada periodo futuro por la
    probabilidad de seguir vivo (y la del grupo familiar) y descontando a la tasa
    técnica. Aquí el CNU se aproxima con una renta cierta a lo largo de la expectativa
    de vida -- la misma idea sin arrastrar las tablas de mortalidad completas.

    La aproximación sobrestima algo el CNU (el valor presente es cóncavo en la
    duración, así que el promedio de los plazos vale menos que el plazo promedio) y
    por lo tanto deja la pensión del lado conservador. Tampoco modela que el retiro
    programado se recalcula cada año y va decreciendo: esto se parece más a una renta
    vitalicia, que es constante en UF.
    """
    if saldo <= 0:
        return 0.0
    i = (TASA_TECNICA if tasa is None else tasa) / 100
    mensual = (1 + i) ** (1 / 12) - 1
    n = round(EXPECTATIVA_VIDA[sexo] * 12)
    factor = n if mensual == 0 else (1 - (1 + mensual) ** -n) / mensual
    return saldo / factor


def impuesto_unico(base_tributable, utm):
    """Impuesto de segunda categoría mensual.

    La base es la renta imponible MENOS las cotizaciones obligatorias efectivamente
    pagadas (que se calculan sólo hasta el tope de 90 UF). Las asignaciones no
    imponibles razonables -- colación, movilización -- no son renta afecta, así que
    no entran; tampoco rebaja el adicional de Isapre, que no es cotización obligatoria.
    """
    if base_tributable <= 0 or utm <= 0:
        return 0.0
    en_utm = base_tributable / utm
    for tope, factor, rebaja in IUSC:
        if tope is None or en_utm <= tope:
            return max(0.0, base_tributable * factor - rebaja * utm)
    return 0.0


def _mezcla_a_edad(edad, sexo, contrato):
    """Fracción del saldo en cada fondo a esa edad, según el traspaso gradual.

    Devuelve {fondo: peso}. Antes del primer hito todo está en el fondo inicial;
    en cada hito el traspaso avanza 20% por año hasta completarse en cuatro.
    """
    hitos = HITOS[contrato][sexo]
    pesos = {hitos[0][1]: 1.0}
    for i in range(1, len(hitos)):
        edad_hito, destino = hitos[i]
        if edad < edad_hito:
            break
        avance = min(1.0, PASO_ANUAL * (1 + int(edad - edad_hito)))
        movido = {f: p * avance for f, p in pesos.items()}
        pesos = {f: p * (1 - avance) for f, p in pesos.items()}
        pesos[destino] = pesos.get(destino, 0.0) + sum(movido.values())
        pesos = {f: p for f, p in pesos.items() if p > 1e-9}
    return pesos


def edad_desde(nacimiento, hoy=None):
    """Edad exacta en años (con decimales) a partir de una fecha ISO 'YYYY-MM-DD'."""
    from datetime import date

    hoy = hoy or date.today()
    y, m, d = (int(x) for x in str(nacimiento).split("-")[:3])
    nace = date(y, m, d)
    años = hoy.year - nace.year - ((hoy.month, hoy.day) < (nace.month, nace.day))
    # fracción transcurrida desde el último cumpleaños
    try:
        ultimo = nace.replace(year=nace.year + años)
    except ValueError:                      # 29 de febrero en año no bisiesto
        ultimo = nace.replace(year=nace.year + años, day=28)
    try:
        siguiente = nace.replace(year=nace.year + años + 1)
    except ValueError:
        siguiente = nace.replace(year=nace.year + años + 1, day=28)
    fraccion = (hoy - ultimo).days / max(1, (siguiente - ultimo).days)
    return round(años + fraccion, 2)


def fondo_por_defecto(edad, sexo):
    """El fondo que la ley asigna si el afiliado no elige."""
    t = TRAMOS[sexo]
    if edad <= t["b_hasta"]:
        return "B"
    if edad <= t["c_hasta"]:
        return "C"
    return "D"


def fondo_vigente(edad, fondo_elegido, sexo, destino_salida_a="B"):
    """El fondo A no admite el saldo obligatorio desde los 56 (hombres) o 51 (mujeres).

    La ley obliga a salir, pero deja elegir cualquiera de los otros cuatro: el destino
    es decisión del afiliado, no un traspaso automático a un fondo determinado.
    El fondo B, en cambio, no tiene restricción de edad en ningún tramo.
    """
    if fondo_elegido == "A" and edad >= EDAD_SALIDA_FONDO_A[sexo]:
        return destino_salida_a
    return fondo_elegido


def rentabilidad_a_edad(edad, fondo_elegido, sexo, trayectoria="fijo", destino_salida_a="B"):
    """Rentabilidad real esperada a esa edad, según la trayectoria elegida.

    'fijo'    -> te quedas en tu fondo, salvo la salida obligatoria del A.
    'basico'  -> esquema de traspasos por edad, contrato básico (termina en D).
    'ampliado'-> contrato ampliado (termina en E).
    """
    if trayectoria == "fijo":
        return RENTABILIDAD_REAL[fondo_vigente(edad, fondo_elegido, sexo, destino_salida_a)]

    pesos = _mezcla_a_edad(edad, sexo, trayectoria)
    return sum(RENTABILIDAD_REAL[f] * p for f, p in pesos.items())


def fondo_a_edad(edad, fondo_elegido, sexo, trayectoria="fijo", destino_salida_a="B"):
    """Etiqueta legible del fondo (o mezcla) en que estarías a esa edad."""
    if trayectoria == "fijo":
        return fondo_vigente(edad, fondo_elegido, sexo, destino_salida_a)
    pesos = _mezcla_a_edad(edad, sexo, trayectoria)
    orden = sorted(pesos.items(), key=lambda kv: -kv[1])
    if len(orden) == 1 or orden[0][1] > 0.99:
        return orden[0][0]
    return " / ".join(f"{f} {round(p * 100)}%" for f, p in orden)


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
