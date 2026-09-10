"""Documentación del proyecto servida desde la propia app.

De nada sirve escribir cómo se calcula cada cifra si para leerlo hay que ir a buscar un
archivo al repositorio.
"""

import os
import re

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

DOC_RE = re.compile(r"^/api/docs/([a-z]+)$")

# Documentación del proyecto, servida desde la propia app: de nada sirve escribir cómo se
# calcula cada cifra si para leerlo hay que ir a buscar un archivo al repositorio. El
# nombre del archivo NUNCA sale de la URL -- se resuelve por esta tabla -- para que la
# ruta no se pueda usar para leer cualquier archivo del disco.
DOCS = {
    "modelo": (
        "MODELO.md",
        "Cómo se calcula",
        "Especificación técnica del modelo: cada fórmula tal como está implementada, "
        "el supuesto que la sostiene y el sesgo que introduce.",
    ),
    "auditoria": (
        "AUDITORIA.md",
        "Auditoría del modelo",
        "Los hallazgos de la revisión adversarial, con su reproducción numérica "
        "y cómo quedó cada uno.",
    ),
    "manual": (
        "README.md",
        "Manual",
        "Qué hace la app, cómo se usa y de dónde sale cada parámetro legal.",
    ),
}
