"""Banda de sensibilidad: cuánto se mueven las cifras con ±1 pp de retorno e inflación.

La proyección es determinista y publicar una edad de agotamiento sin decir cuánto se
mueve promete una precisión que el modelo no tiene.
"""
from .acumulacion import project

# La proyección es determinista: una inflación, un retorno, una expectativa de vida.
# Publicar "se agota a los 71" sin decir cuánto se mueve esa cifra si el retorno baja
# un punto es prometer una precisión que el modelo no tiene, así que el resultado
# viaja acompañado del rango que producen ±1 pp de retorno y ±1 pp de inflación.

def _variante(data, retorno=0.0, inflacion=0.0):
    """Copia del escenario con el retorno y/o la inflación movidos en pp."""
    d = dict(data)
    d["inflation"] = data["inflation"] + inflacion
    if data["model"] == "dividends":
        d["appreciation"] = data["appreciation"] + retorno
        d["annual_return"] = (
            (1 + d["appreciation"] / 100) * (1 + d["dividend_yield"] / 100) - 1) * 100
    else:
        d["annual_return"] = data["annual_return"] + retorno
    return d


def _extraer(result):
    ret = result.get("retirement") or {}
    return {
        "depletion_age": ret.get("depletion_age"),
        "max_spend_today": ret.get("max_spend_today"),
        "final_real_balance": result.get("final_real_balance"),
        "fi_year": result.get("fi_year"),
    }


def _rango(valores):
    """min/max de una métrica, tolerando los None (no se agota / no alcanza FI)."""
    concretos = [v for v in valores if v is not None]
    if not concretos:
        return {"min": None, "max": None, "indefinido": True}
    return {
        "min": min(concretos),
        "max": max(concretos),
        # si alguna variante no se agota (o nunca alcanza FI), el rango es abierto
        "indefinido": len(concretos) < len(valores),
    }


def sensitivity(data, result, paso=1.0):
    """Cuánto se mueven las cifras clave con ±`paso` pp de retorno y de inflación.

    Cuatro proyecciones extra sobre el mismo escenario. No es un Monte Carlo: es la
    banda mínima honesta para que un número con pinta de exacto no se lea como tal.
    """
    casos = {
        "retorno_baja": _variante(data, retorno=-paso),
        "retorno_sube": _variante(data, retorno=+paso),
        "inflacion_sube": _variante(data, inflacion=+paso),
        "inflacion_baja": _variante(data, inflacion=-paso),
    }
    salidas = {"central": _extraer(result)}
    for nombre, escenario in casos.items():
        try:
            salidas[nombre] = _extraer(project(escenario))
        except (ValueError, KeyError, ZeroDivisionError):
            continue

    metricas = ("depletion_age", "max_spend_today", "final_real_balance", "fi_year")
    rangos = {m: _rango([s[m] for s in salidas.values()]) for m in metricas}
    for m in metricas:
        rangos[m]["central"] = salidas["central"][m]
    return {"paso_pp": paso, "casos": salidas, "rangos": rangos}
