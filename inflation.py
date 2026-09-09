"""Serie histórica del IPC de Chile y ventanas para estimar inflación esperada.

Variación anual del IPC a diciembre de cada año (dic-dic), fuente Banco Central /
INE. Se parte en el año 2000 a propósito: Chile adoptó metas de inflación con tipo
de cambio flotante en 1999, así que los años anteriores (inflación de 30% en 1990,
convergiendo desde el ciclo inflacionario del siglo XX) pertenecen a otro régimen
monetario y mezclarlos sesgaría la estimación al alza.
"""

IPC_CL = {
    2000: 4.5, 2001: 2.6, 2002: 2.8, 2003: 1.1, 2004: 2.4, 2005: 3.7, 2006: 2.6,
    2007: 7.8, 2008: 7.1, 2009: -1.4, 2010: 3.0, 2011: 4.4, 2012: 1.5, 2013: 3.0,
    2014: 4.6, 2015: 4.4, 2016: 2.7, 2017: 2.3, 2018: 2.6, 2019: 3.0, 2020: 3.0,
    2021: 7.2, 2022: 12.8, 2023: 3.9, 2024: 4.5, 2025: 4.2,
}

LAST_YEAR = max(IPC_CL)
CENTRAL_BANK_TARGET = 3.0

# Episodios que una ventana corta puede perderse por completo.
CRISES = {
    2007: "alza global de alimentos y energía",
    2008: "crisis financiera global",
    2009: "deflación post-crisis",
    2020: "pandemia",
    2021: "shock inflacionario global",
    2022: "peak inflacionario (29 años)",
}


def geometric_mean(years):
    """Media geométrica: la correcta para tasas que se componen.

    La aritmética sobreestima, porque promediar +12,8% y -1,4% no equivale al
    efecto compuesto real de vivir ambos años.
    """
    rates = [IPC_CL[y] for y in years if y in IPC_CL]
    if not rates:
        return None
    product = 1.0
    for r in rates:
        product *= 1 + r / 100
    return (product ** (1 / len(rates)) - 1) * 100


def window(n_years):
    """Los últimos n años disponibles de la serie."""
    return range(LAST_YEAR - n_years + 1, LAST_YEAR + 1)


def presets():
    """Opciones de ventana para el selector, de más corta a más larga."""
    options = [
        {
            "key": "target",
            "label": f"Meta del Banco Central ({CENTRAL_BANK_TARGET:.1f}%)",
            "value": CENTRAL_BANK_TARGET,
            "detail": "El ancla oficial de política monetaria, con banda de ±1 punto.",
            "crises": 0,
        }
    ]
    for n in (10, 20, len(IPC_CL)):
        years = list(window(n))
        value = round(geometric_mean(years), 2)
        crises = sum(1 for y in years if y in CRISES)
        span = f"{years[0]}-{years[-1]}"
        options.append(
            {
                "key": f"w{n}",
                "label": f"Últimos {n} años · {span} ({value:.2f}%)",
                "value": value,
                "detail": f"Media geométrica de {n} años. Incluye {crises} años de crisis.",
                "crises": crises,
                "recommended": n == len(IPC_CL),
            }
        )
    return options
