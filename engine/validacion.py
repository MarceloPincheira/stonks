"""Validación y normalización del escenario que llega desde el frontend.

Es la única puerta de entrada al motor: todo lo que sigue asume que el diccionario ya
tiene todas las claves y los rangos verificados.
"""

from __future__ import annotations

from datetime import date as _date
from typing import Any

from .tipos import AporteExtraordinario, Escenario, Payload, Tramo


class ValidationError(ValueError):
    pass


def _num(payload: Payload, key: str, default: Any) -> int:
    value = payload.get(key, default)
    if value in (None, ""):
        return default
    try:
        return int(value)
    except (TypeError, ValueError):
        raise ValidationError(f"El campo '{key}' debe ser un número entero.") from None


def _pct(payload: Payload, key: str, default: float = 0.0) -> float:
    value = payload.get(key, default)
    if value in (None, ""):
        return default
    try:
        return float(value)
    except (TypeError, ValueError):
        raise ValidationError(f"El campo '{key}' debe ser numérico.") from None


def normalize_input(payload: Payload) -> Escenario:
    """Valida y normaliza el payload que llega desde el frontend."""
    try:
        years = int(payload.get("years"))
    except (TypeError, ValueError):
        raise ValidationError("El horizonte en años debe ser numérico.") from None
    if years < 1 or years > 100:
        raise ValidationError("El horizonte debe estar entre 1 y 100 años.")

    model = payload.get("model") or "simple"
    if model not in ("simple", "dividends"):
        raise ValidationError("Modelo desconocido.")

    annual_return = _pct(payload, "annual_return")
    dividend_yield = _pct(payload, "dividend_yield")
    appreciation = _pct(payload, "appreciation")
    inflation = _pct(payload, "inflation")
    income_goal = _pct(payload, "income_goal")
    dividend_tax = _pct(payload, "dividend_tax")

    if inflation <= -100:
        raise ValidationError("La inflación anual no puede ser -100% o menor.")
    if income_goal < 0:
        raise ValidationError("La meta de ingreso no puede ser negativa.")
    if not 0 <= dividend_tax <= 100:
        raise ValidationError("El impuesto sobre los repartos debe estar entre 0% y 100%.")

    if model == "simple":
        if annual_return <= -100:
            raise ValidationError("La rentabilidad anual no puede ser -100% o menor.")
    else:
        if appreciation <= -100:
            raise ValidationError("La plusvalía anual no puede ser -100% o menor.")
        if dividend_yield < 0:
            raise ValidationError("El dividend yield no puede ser negativo.")
        # El motor capitaliza la plusvalía todos los meses y reinvierte el dividendo,
        # o sea que COMPONE las dos fuentes. Declararlas como suma simple dejaba la
        # etiqueta ("9,21% anual") por debajo de lo que la simulación entregaba.
        annual_return = ((1 + appreciation / 100) * (1 + dividend_yield / 100) - 1) * 100

    payout_months = []
    for raw in payload.get("payout_months") or [3, 6, 9, 12]:
        try:
            m = int(raw)
        except (TypeError, ValueError):
            raise ValidationError("Los meses de pago deben ser números del 1 al 12.") from None
        if not 1 <= m <= 12:
            raise ValidationError("Los meses de pago deben estar entre 1 y 12.")
        if m not in payout_months:
            payout_months.append(m)
    payout_months.sort()
    if model == "dividends" and not payout_months:
        raise ValidationError("Define al menos un mes de pago de dividendos.")

    raw_ranges = payload.get("ranges") or []
    ranges: list[Tramo] = []
    for i, r in enumerate(raw_ranges, start=1):
        try:
            start = int(r.get("start_month"))
            end = int(r.get("end_month"))
            amount = float(r.get("amount"))
        except (TypeError, ValueError):
            raise ValidationError(f"Tramo {i}: los valores deben ser numéricos.") from None
        if start < 1:
            raise ValidationError(f"Tramo {i}: el mes inicial debe ser 1 o mayor.")
        if end < start:
            raise ValidationError(f"Tramo {i}: el mes final no puede ser menor al inicial.")
        if amount < 0:
            raise ValidationError(f"Tramo {i}: el monto no puede ser negativo.")
        ranges.append({"start_month": start, "end_month": end, "amount": amount})

    ranges.sort(key=lambda r: r["start_month"])
    for prev, cur in zip(ranges, ranges[1:]):
        if cur["start_month"] <= prev["end_month"]:
            raise ValidationError(
                f"Los tramos {prev['start_month']}-{prev['end_month']} y "
                f"{cur['start_month']}-{cur['end_month']} se solapan."
            )

    # Aportes extraordinarios: van amarrados a un mes de calendario, no a un número de
    # mes de la proyección, así que hace falta saber cuándo parte la inversión.
    hoy = _date.today()
    start_year = int(_num(payload, "start_year", hoy.year))
    start_month = int(_num(payload, "start_month", hoy.month))
    if not 1 <= start_month <= 12:
        raise ValidationError("El mes de inicio debe estar entre 1 y 12.")

    lump_sums: list[AporteExtraordinario] = []
    for raw in payload.get("lump_sums") or []:
        amount = _pct(raw, "amount")
        if amount < 0:
            raise ValidationError("Un aporte extraordinario no puede ser negativo.")
        try:
            year = int(raw.get("year"))
            month = int(raw.get("month"))
        except (TypeError, ValueError):
            raise ValidationError("El aporte extraordinario necesita mes y año.") from None
        if not 1 <= month <= 12:
            raise ValidationError("El mes del aporte extraordinario debe estar entre 1 y 12.")
        if not 1900 <= year <= 2200:
            raise ValidationError("El año del aporte extraordinario está fuera de rango.")
        if amount > 0:
            lump_sums.append({"year": year, "month": month, "amount": amount})

    # Fase de retiro: hasta qué edad estirar el patrimonio. Por defecto la expectativa
    # de vida que usa la AFP para calcular la pensión, que es el horizonte natural.
    start_age = _pct(payload, "start_age")
    life_age = _pct(payload, "life_age")
    retire_to_age = _pct(payload, "retire_to_age") or life_age
    if retire_to_age and start_age and retire_to_age <= start_age:
        raise ValidationError("La edad objetivo debe ser mayor que tu edad actual.")
    work_until_age = _pct(payload, "work_until_age")
    work_until_month = payload.get("work_until_month")
    work_until_month = None if work_until_month in (None, "") else int(work_until_month)
    spend_mode = payload.get("spend_mode") or "goal"
    if spend_mode not in ("goal", "target_age"):
        raise ValidationError("Modo de gasto desconocido.")

    # Pensión de la AFP: desde la edad de jubilación parte de la meta la paga ella,
    # así que la inversión sólo tiene que cubrir la diferencia. Llega calculada desde
    # el perfil (server.py); el escenario sólo guarda si se considera o no.
    pension_monthly = _pct(payload, "pension_monthly")
    if pension_monthly < 0:
        raise ValidationError("La pensión mensual no puede ser negativa.")
    pension_start_month = payload.get("pension_start_month")
    if pension_start_month in (None, ""):
        pension_start_month = None
    else:
        try:
            pension_start_month = int(pension_start_month)
        except (TypeError, ValueError):
            raise ValidationError("El mes de inicio de la pensión debe ser numérico.") from None
        if pension_start_month < 1:
            pension_start_month = 1

    name = (payload.get("name") or "").strip() or "Escenario sin nombre"
    currency = (payload.get("currency") or "CLP").strip()[:8]

    return {
        "name": name[:120],
        "annual_return": annual_return,
        "years": years,
        "currency": currency,
        "model": model,
        "dividend_yield": dividend_yield,
        "appreciation": appreciation,
        "inflation": inflation,
        "income_goal": income_goal,
        "dividend_tax": dividend_tax,
        "index_contributions": bool(payload.get("index_contributions", False)),
        "start_year": start_year,
        "start_month": start_month,
        "lump_sums": lump_sums,
        "start_age": start_age,
        "life_age": life_age,
        "retire_to_age": retire_to_age,
        "work_until_age": work_until_age,
        "work_until_month": work_until_month,
        "afp_summary": payload.get("afp_summary"),
        "spend_mode": spend_mode,
        # los None son meses anteriores al inicio de la serie AFP: huecos, no ceros
        "afp_monthly": [
            None if x is None else float(x) for x in (payload.get("afp_monthly") or [])
        ],
        "include_pension": bool(payload.get("include_pension", True)),
        "pension_monthly": pension_monthly,
        "pension_start_month": pension_start_month,
        "reinvest": bool(payload.get("reinvest", True)),
        "payout_months": payout_months,
        "ranges": ranges,
    }
