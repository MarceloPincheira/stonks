"""Conversión del saldo acumulado en pensión: Capital Necesario Unitario."""

from __future__ import annotations

from .parametros import EXPECTATIVA_VIDA, TASA_TECNICA


def pension_mensual(saldo: float, sexo: str, tasa: float | None = None) -> float:
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
