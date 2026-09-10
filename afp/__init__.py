"""Sistema previsional chileno: parámetros legales y proyección del saldo AFP.

El paquete separa los parámetros (que caducan y se actualizan) del cálculo (que no), y
reexporta aquí la superficie pública para que quien lo use siga escribiendo
`afp.proyectar(...)` sin saber en qué archivo vive cada pieza.
"""
from .edad import edad_desde
from .fondos import (_mezcla_a_edad, fondo_a_edad, fondo_por_defecto, fondo_vigente,
                     rentabilidad_a_edad)
from .parametros import (APORTE_EMPLEADOR_CUENTA, CESANTIA_INDEFINIDO, COMISIONES,
                         COTIZACION_OBLIGATORIA, EDAD_PENSION, EDAD_SALIDA_FONDO_A,
                         ETAPAS_TRASPASO, EXPECTATIVA_VIDA, FONDOS_GENERACIONALES_DESDE, HITOS,
                         IUSC, PASO_ANUAL, RENTABILIDAD_REAL, SALUD, TASA_TECNICA,
                         TOPE_CESANTIA_UF, TOPE_IMPONIBLE_UF, TRAMOS, UF_REFERENCIA,
                         UTM_REFERENCIA)
from .pension import pension_mensual
from .proyeccion import proyectar
from .tributario import impuesto_unico
