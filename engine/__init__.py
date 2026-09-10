"""Motor de proyección.

El paquete se divide por fase del cálculo -- validar, acumular, desacumular, medir
sensibilidad -- y reexporta aquí la superficie pública para que quien lo use siga
escribiendo `engine.project(...)` sin saber en qué archivo vive cada pieza.
"""

from .acumulacion import monthly_amount_table, project
from .retiro import _max_spend, _retirement_path
from .sensibilidad import sensitivity
from .validacion import ValidationError, normalize_input

__all__ = [
    "ValidationError",
    "_max_spend",
    "_retirement_path",
    "monthly_amount_table",
    "normalize_input",
    "project",
    "sensitivity",
]
