"""Parámetros legales del sistema previsional chileno y de la tributación laboral.

Todas las rentabilidades de los fondos son REALES (por sobre la inflación), tal como las
publica la Superintendencia de Pensiones. Eso es cómodo aquí: al proyectar en pesos de hoy
no hay que sumarles inflación, y al pasar a nominales se compone con ella.

Estos valores caducan: conviene contrastarlos con la fuente antes de confiar en un
resultado. Cada uno lleva anotado de dónde sale y de qué fecha es.
"""

RENTABILIDAD_REAL = {"A": 5.95, "B": 5.11, "C": 4.30, "D": 3.47, "E": 2.80}

# Ley 21.735: los multifondos A-E se reemplazan por diez fondos generacionales
# asignados por año de nacimiento, sin elección en el ahorro obligatorio. La
# proyección sigue usando la trayectoria de los multifondos porque los nuevos aún
# no tienen rentabilidad observada. Formato AAAA-MM; el frontend lo escribe en prosa.
FONDOS_GENERACIONALES_DESDE = "2027-04"

# Comisión sobre la renta imponible. Se descuenta del sueldo pero NO entra a la
# cuenta individual: es el precio de administración. Conviene verificarla, cambia.
COMISIONES = {
    "Uno": 0.49,
    "Modelo": 0.58,
    "PlanVital": 1.16,
    "Habitat": 1.27,
    "Capital": 1.44,
    "Cuprum": 1.44,
    "ProVida": 1.45,
}

COTIZACION_OBLIGATORIA = 10.0  # a la cuenta individual
SALUD = 7.0  # FONASA o Isapre (el plan puede costar más)
CESANTIA_INDEFINIDO = 0.6  # seguro de cesantía, contrato indefinido
TOPE_IMPONIBLE_UF = 90.0  # tope 2026 para AFP y salud
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
    (13.5, 0.000, 0.00),  # exento
    (30.0, 0.040, 0.54),
    (50.0, 0.080, 1.74),
    (70.0, 0.135, 4.49),
    (90.0, 0.230, 11.14),
    (120.0, 0.304, 17.80),
    (310.0, 0.350, 23.32),
    (None, 0.400, 38.82),
]

# Valores de referencia, editables en el perfil porque cambian todos los meses.
UTM_REFERENCIA = 71721.0  # septiembre 2026, SII
UF_REFERENCIA = 40884.32  # 8 de septiembre de 2026, Banco Central

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
ETAPAS_TRASPASO = 4  # años que tarda en completarse
PASO_ANUAL = 0.20  # fracción del saldo que se mueve cada año

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
TASA_TECNICA = 3.45  # tercer trimestre de 2026, Circular N° 2.417 de la SP

# Expectativa de vida a la edad de pensión, tablas de mortalidad 2020 con sus
# factores de mejoramiento: hombre de 65 vive hasta ~86,6; mujer de 60, hasta ~90,8.
EXPECTATIVA_VIDA = {"hombre": 21.6, "mujer": 30.8}
