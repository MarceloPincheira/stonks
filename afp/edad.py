"""Edad exacta a partir de la fecha de nacimiento."""

from __future__ import annotations

from datetime import date


def edad_desde(nacimiento: str, hoy: date | None = None) -> float:
    """Edad exacta en años (con decimales) a partir de una fecha ISO 'YYYY-MM-DD'."""
    hoy = hoy or date.today()
    y, m, d = (int(x) for x in str(nacimiento).split("-")[:3])
    nace = date(y, m, d)
    años = hoy.year - nace.year - ((hoy.month, hoy.day) < (nace.month, nace.day))
    # fracción transcurrida desde el último cumpleaños
    try:
        ultimo = nace.replace(year=nace.year + años)
    except ValueError:  # 29 de febrero en año no bisiesto
        ultimo = nace.replace(year=nace.year + años, day=28)
    try:
        siguiente = nace.replace(year=nace.year + años + 1)
    except ValueError:
        siguiente = nace.replace(year=nace.year + años + 1, day=28)
    fraccion = (hoy - ultimo).days / max(1, (siguiente - ultimo).days)
    return round(años + fraccion, 2)
