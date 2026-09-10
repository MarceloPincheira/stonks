"""Fase de desacumulación: consumir el patrimonio hasta la edad objetivo."""
from __future__ import annotations

from typing import Any

from .tipos import Deflactor


def _retirement_path(
    spend_today: float,
    start_month: int,
    end_month: int,
    portfolio: float,
    deflator: Deflactor,
    monthly_rate: float,
    accrual_rate: float,
    payout_months: list[int],
    pension_today: float,
    pension_start: int | None,
    accrual0: float = 0.0,
    rows: bool = False,
) -> tuple[list[dict[str, float]], int | None, float]:
    """Consume el patrimonio mes a mes desde que se deja de aportar.

    Cada mes hay que juntar `spend_today` en pesos de hoy. Lo pone primero la pensión
    de la AFP, después los dividendos del mes -- que no se descuentan del capital, misma
    convención que en la acumulación -- y lo que falte se vende del fondo. Si sobra,
    vuelve al fondo. Devuelve (filas, mes en que se agota, saldo final).
    """
    detalle = []
    agotado = None
    devengo = accrual0
    for m in range(start_month + 1, end_month + 1):
        d = deflator(m)
        necesita = spend_today * d
        pension = pension_today * d if pension_start and m >= pension_start else 0.0
        # El reparto se devenga todos los meses sobre el valor capitalizado y se paga
        # acumulado en su mes, igual que en la acumulación.
        devengo += portfolio * (1 + monthly_rate) * accrual_rate
        dividendo = 0.0
        if accrual_rate and ((m - 1) % 12) + 1 in payout_months:
            dividendo, devengo = devengo, 0.0
        ingreso = pension + dividendo
        del_fondo = max(0.0, necesita - ingreso)
        sobra = max(0.0, ingreso - necesita)

        # no se puede vender más de lo que queda: lo que falte es déficit
        del_fondo_real = min(del_fondo, portfolio)
        if del_fondo > portfolio + 1e-6 and agotado is None:
            agotado = m
        portfolio = max(0.0, portfolio - del_fondo_real + sobra) * (1 + monthly_rate)

        if rows:
            detalle.append({
                "month": m,
                "balance": round(portfolio, 2),
                "need": round(necesita, 2),
                "pension": round(pension, 2),
                "dividend": round(dividendo, 2),
                "from_portfolio": round(del_fondo_real, 2),
                "shortfall": round(del_fondo - del_fondo_real, 2),
                "need_real": round(spend_today, 2),
                "balance_real": round(portfolio / d, 2),
            })
    return detalle, agotado, portfolio


def _max_spend(objetivo_mes: int, **kw: Any) -> float:
    """Cuánto se puede gastar al mes (en pesos de hoy) para llegar justo a cero.

    Bisección: el saldo final es monótono decreciente en el gasto, así que basta con
    buscar el gasto más chico que lo deja en cero al llegar a la edad objetivo.

    El techo de partida (un doceavo del patrimonio) sólo acota si quedan doce meses o
    más por delante; con horizontes cortos hay que duplicarlo hasta que sobre nada, o
    la bisección converge al propio techo y devuelve un máximo falsamente bajo.
    """
    bajo, alto = 0.0, max(1.0, kw["portfolio"]) / 12 + kw["pension_today"] + 1
    for _ in range(64):
        if _retirement_path(alto, end_month=objetivo_mes, **kw)[2] <= 1:
            break
        bajo, alto = alto, alto * 2
    for _ in range(80):
        medio = (bajo + alto) / 2
        _, _, final = _retirement_path(medio, end_month=objetivo_mes, **kw)
        if final > 1:
            bajo = medio
        else:
            alto = medio
    return bajo
