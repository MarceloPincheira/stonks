"""Sistema previsional chileno: parámetros legales y proyección del saldo AFP.

El paquete separa los parámetros (que caducan y se actualizan) del cálculo (que no), y
reexporta aquí la superficie pública para que quien lo use siga escribiendo
`afp.proyectar(...)` sin saber en qué archivo vive cada pieza.
"""
from .parametros import *          # noqa: F401,F403  -- constantes legales
from .parametros import IUSC, EDAD_PENSION, RENTABILIDAD_REAL, COMISIONES
from .edad import edad_desde
from .tributario import impuesto_unico
from .pension import pension_mensual
from .fondos import (_mezcla_a_edad, fondo_a_edad, fondo_por_defecto, fondo_vigente,
                     rentabilidad_a_edad)
from .proyeccion import proyectar
