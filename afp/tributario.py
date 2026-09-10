"""Impuesto único de segunda categoría (art. 42 N°1 y 52 de la LIR)."""
from .parametros import IUSC

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
