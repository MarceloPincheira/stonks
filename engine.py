"""Motor de proyección: aportes por tramos + capitalización mensual compuesta.

Dos modelos:
  * 'simple'    -> una sola tasa de retorno total anual, reinvertida siempre.
  * 'dividends' -> plusvalía de la cuota + dividendos periódicos, con la opción
                   de reinvertirlos o cobrarlos en efectivo.
"""


from datetime import date as _date


class ValidationError(ValueError):
    pass


def _num(payload, key, default):
    value = payload.get(key, default)
    if value in (None, ""):
        return default
    try:
        return int(value)
    except (TypeError, ValueError):
        raise ValidationError(f"El campo '{key}' debe ser un número entero.")


def _pct(payload, key, default=0.0):
    value = payload.get(key, default)
    if value in (None, ""):
        return default
    try:
        return float(value)
    except (TypeError, ValueError):
        raise ValidationError(f"El campo '{key}' debe ser numérico.")


def normalize_input(payload):
    """Valida y normaliza el payload que llega desde el frontend."""
    try:
        years = int(payload.get("years"))
    except (TypeError, ValueError):
        raise ValidationError("El horizonte en años debe ser numérico.")
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

    if inflation <= -100:
        raise ValidationError("La inflación anual no puede ser -100% o menor.")
    if income_goal < 0:
        raise ValidationError("La meta de ingreso no puede ser negativa.")

    if model == "simple":
        if annual_return <= -100:
            raise ValidationError("La rentabilidad anual no puede ser -100% o menor.")
    else:
        if appreciation <= -100:
            raise ValidationError("La plusvalía anual no puede ser -100% o menor.")
        if dividend_yield < 0:
            raise ValidationError("El dividend yield no puede ser negativo.")
        annual_return = appreciation + dividend_yield

    payout_months = []
    for raw in payload.get("payout_months") or [3, 6, 9, 12]:
        try:
            m = int(raw)
        except (TypeError, ValueError):
            raise ValidationError("Los meses de pago deben ser números del 1 al 12.")
        if not 1 <= m <= 12:
            raise ValidationError("Los meses de pago deben estar entre 1 y 12.")
        if m not in payout_months:
            payout_months.append(m)
    payout_months.sort()
    if model == "dividends" and not payout_months:
        raise ValidationError("Define al menos un mes de pago de dividendos.")

    raw_ranges = payload.get("ranges") or []
    ranges = []
    for i, r in enumerate(raw_ranges, start=1):
        try:
            start = int(r.get("start_month"))
            end = int(r.get("end_month"))
            amount = float(r.get("amount"))
        except (TypeError, ValueError):
            raise ValidationError(f"Tramo {i}: los valores deben ser numéricos.")
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

    lump_sums = []
    for raw in payload.get("lump_sums") or []:
        amount = _pct(raw, "amount")
        if amount < 0:
            raise ValidationError("Un aporte extraordinario no puede ser negativo.")
        try:
            year = int(raw.get("year"))
            month = int(raw.get("month"))
        except (TypeError, ValueError):
            raise ValidationError("El aporte extraordinario necesita mes y año.")
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
            raise ValidationError("El mes de inicio de la pensión debe ser numérico.")
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
        "afp_monthly": [float(x) for x in (payload.get("afp_monthly") or [])],
        "include_pension": bool(payload.get("include_pension", True)),
        "pension_monthly": pension_monthly,
        "pension_start_month": pension_start_month,
        "reinvest": bool(payload.get("reinvest", True)),
        "payout_months": payout_months,
        "ranges": ranges,
    }


def _retirement_path(spend_today, start_month, end_month, portfolio, deflator,
                     monthly_rate, per_payout, payout_months, pension_today,
                     pension_start, rows=False):
    """Consume el patrimonio mes a mes desde que se deja de aportar.

    Cada mes hay que juntar `spend_today` en pesos de hoy. Lo pone primero la pensión
    de la AFP, después los dividendos del mes -- que no se descuentan del capital, misma
    convención que en la acumulación -- y lo que falte se vende del fondo. Si sobra,
    vuelve al fondo. Devuelve (filas, mes en que se agota, saldo final).
    """
    detalle = []
    agotado = None
    for m in range(start_month + 1, end_month + 1):
        d = deflator(m)
        necesita = spend_today * d
        pension = pension_today * d if pension_start and m >= pension_start else 0.0
        dividendo = portfolio * per_payout if per_payout and ((m - 1) % 12) + 1 in payout_months else 0.0
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


def _max_spend(objetivo_mes, **kw):
    """Cuánto se puede gastar al mes (en pesos de hoy) para llegar justo a cero.

    Bisección: el saldo final es monótono decreciente en el gasto, así que basta con
    buscar el gasto más chico que lo deja en cero al llegar a la edad objetivo.
    """
    bajo, alto = 0.0, max(1.0, kw["portfolio"]) / 12 + kw["pension_today"] + 1
    for _ in range(80):
        medio = (bajo + alto) / 2
        _, _, final = _retirement_path(medio, end_month=objetivo_mes, **kw)
        if final > 1:
            bajo = medio
        else:
            alto = medio
    return bajo


def monthly_amount_table(ranges, total_months):
    """Devuelve una lista de largo total_months con el aporte de cada mes."""
    table = [0.0] * total_months
    for r in ranges:
        start = max(1, r["start_month"])
        end = min(total_months, r["end_month"])
        for m in range(start, end + 1):
            table[m - 1] = r["amount"]
    return table


def project(data):
    """Proyecta mes a mes. El aporte entra al inicio del mes y renta ese mismo mes.

    En el modelo con dividendos, la plusvalía se capitaliza todos los meses y el
    dividendo se paga en los meses indicados, calculado sobre el valor del
    portafolio en ese momento. La plusvalía histórica de un fondo de reparto ya
    viene neta de los repartos, así que el dividendo NO se descuenta del capital.
    """
    total_months = data["years"] * 12
    dividends_on = data["model"] == "dividends"
    reinvest = data["reinvest"]

    growth_pct = data["appreciation"] if dividends_on else data["annual_return"]
    monthly_rate = (1 + growth_pct / 100.0) ** (1 / 12) - 1

    payout_months = data["payout_months"]
    per_payout = (
        (data["dividend_yield"] / 100.0) / len(payout_months)
        if dividends_on and payout_months
        else 0.0
    )

    amounts = monthly_amount_table(data["ranges"], total_months)

    # Los aportes salen del sueldo: cuando se deja de trabajar, se acaban. Los tramos
    # definidos más allá de esa edad se recortan en vez de ignorarse en silencio.
    hasta = data["work_until_month"]
    recortado = 0
    if hasta is not None and hasta < total_months:
        recortado = sum(1 for a in amounts[hasta:] if a > 0)
        amounts = amounts[:max(0, hasta)] + [0.0] * (total_months - max(0, hasta))

    # Deflactar es dividir por (1+i)^t, no restar la inflación.
    inflation_rate = data["inflation"] / 100.0
    deflator = lambda m: (1 + inflation_rate) ** (m / 12)
    goal_monthly_today = data["income_goal"]

    # Con aportes indexados, el monto escrito es "pesos de hoy" y sube una vez al año,
    # como un reajuste salarial. Sin indexar, es un monto nominal fijo que pierde
    # poder adquisitivo con los años.
    index_contributions = data["index_contributions"]
    def contribution_factor(m):
        return (1 + inflation_rate) ** ((m - 1) // 12) if index_contributions else 1.0

    # Aportes extraordinarios. El monto se escribe en pesos de HOY, así que llevarlo al
    # mes en que cae es multiplicarlo por el mismo factor con que se deflacta el resto:
    # es la única forma de que "vender el terreno en marzo de 2032 por $80 M de hoy"
    # signifique el mismo poder adquisitivo que $80 M hoy.
    lump_by_month = {}
    lump_rows = []
    for l in data["lump_sums"]:
        m = (l["year"] - data["start_year"]) * 12 + (l["month"] - data["start_month"]) + 1
        dentro = 1 <= m <= total_months
        nominal = l["amount"] * deflator(m) if dentro else None
        if dentro:
            lump_by_month[m] = lump_by_month.get(m, 0.0) + nominal
        lump_rows.append({
            "year": l["year"], "month": l["month"], "amount": l["amount"],
            "projection_month": m if dentro else None,
            "in_range": dentro,
            "amount_nominal": round(nominal, 2) if dentro else None,
        })

    portfolio = 0.0      # valor de mercado dentro del fondo
    cash = 0.0           # dividendos cobrados y no reinvertidos
    invested = 0.0       # aportes de tu bolsillo, sin reinversión
    reinvested = 0.0     # dividendos que volvieron al fondo
    dividends_total = 0.0
    dividends_real = 0.0
    months = []

    invested_real = 0.0     # cada aporte llevado a pesos de hoy en su momento
    reinvested_real = 0.0   # ídem para cada dividendo reinvertido
    for m in range(1, total_months + 1):
        lump = lump_by_month.get(m, 0.0)
        contribution = amounts[m - 1] * contribution_factor(m) + lump
        invested += contribution
        invested_real += contribution / deflator(m)
        growth = (portfolio + contribution) * monthly_rate
        portfolio = portfolio + contribution + growth

        dividend = 0.0
        if dividends_on and ((m - 1) % 12) + 1 in payout_months:
            dividend = portfolio * per_payout
            dividends_total += dividend
            dividends_real += dividend / deflator(m)
            if reinvest:
                portfolio += dividend
                reinvested += dividend
                reinvested_real += dividend / deflator(m)
            else:
                cash += dividend

        months.append(
            {
                "month": m,
                "contribution": round(contribution, 2),
                "lump": round(lump, 2),
                "invested": round(invested, 2),
                "interest": round(growth, 2),
                "dividend": round(dividend, 2),
                "dividends_total": round(dividends_total, 2),
                "dividends_real": round(dividends_real, 2),
                "reinvested_total": round(reinvested, 2),
                # capital total puesto a trabajar = bolsillo + dividendos reinvertidos
                "cost_basis": round(invested + reinvested, 2),
                # el capital puesto a trabajar, medido en pesos de hoy
                "cost_basis_real": round(invested_real + reinvested_real, 2),
                "cash": round(cash, 2),
                # plusvalía = valor de mercado menos el capital puesto en el fondo.
                # Se cumple siempre: ganancia = dividendos acumulados + plusvalía.
                "capital_gain": round(portfolio - (invested + reinvested), 2),
                "portfolio": round(portfolio, 2),
                # mismo dinero expresado en pesos de hoy
                "real_balance": round((portfolio + cash) / deflator(m), 2),
                "invested_real": round(invested_real, 2),
                "balance": round(portfolio + cash, 2),
            }
        )

    yearly = []
    prev_dividends = 0.0
    for m in months:
        if m["month"] % 12:
            continue
        yearly.append(
            {
                "year": m["month"] // 12,
                "month": m["month"],
                "invested": m["invested"],
                "invested_real": m["invested_real"],
                "reinvested_total": m["reinvested_total"],
                "cost_basis_real": m["cost_basis_real"],
                "cost_basis": m["cost_basis"],
                "capital_gain": m["capital_gain"],
                "portfolio": m["portfolio"],
                "cash": m["cash"],
                # lo repartido durante ese año, no el acumulado histórico
                "dividends_year": round(m["dividends_total"] - prev_dividends, 2),
                "dividends_total": m["dividends_total"],
                "dividends_real": m["dividends_real"],
                "balance": m["balance"],
                "gain": round(m["balance"] - m["invested"], 2),
            }
        )
        prev_dividends = m["dividends_total"]

    # --- retiro sostenible -------------------------------------------------
    # Para que el capital NO pierda poder adquisitivo debe crecer al menos como la
    # inflación. La plusvalía aporta g; el resto tiene que salir de reinvertir parte
    # de los dividendos. Lo que queda libre para vivir es:
    #     tasa sostenible = yield - max(0, inflación - plusvalía)
    # Si la plusvalía ya iguala a la inflación, puedes consumir todo el dividendo.
    growth_gap = max(0.0, data["inflation"] - growth_pct)
    sustainable_rate = data["dividend_yield"] - growth_gap if dividends_on else 0.0
    reinvest_share = (growth_gap / data["dividend_yield"] * 100) if dividends_on and data["dividend_yield"] > 0 else None

    # Desde la edad de jubilación la AFP paga una pensión y la meta que debe cubrir la
    # inversión baja en esa cantidad. La pensión se toma constante en pesos de hoy
    # (las rentas vitalicias y el retiro programado se pagan en UF), o sea que en
    # nominal crece con la inflación igual que la meta.
    pension_today = data["pension_monthly"] if data["include_pension"] else 0.0
    pension_start = data["pension_start_month"] if pension_today > 0 else None

    for y in yearly:
        d = deflator(y["month"])
        div_year = y["dividends_year"]
        # lo que costará en el año Y vivir como hoy con goal_monthly_today
        goal_monthly = goal_monthly_today * d
        # el año en que empieza la pensión se prorratea por los meses que alcanza a pagar
        if pension_start is None:
            meses_con_pension = 0
        else:
            meses_con_pension = max(0, min(y["month"], total_months) - max(y["month"] - 11, pension_start) + 1)
        pension_monthly = pension_today * d * min(1.0, meses_con_pension / 12)
        goal_from_portfolio = max(0.0, goal_monthly - pension_monthly)

        received_monthly = div_year / 12
        y["goal_monthly"] = round(goal_monthly, 2)
        y["pension_monthly"] = round(pension_monthly, 2)
        y["goal_from_portfolio"] = round(goal_from_portfolio, 2)
        y["dividend_monthly"] = round(received_monthly, 2)
        y["dividend_monthly_real"] = round(received_monthly / d, 2)
        y["real_balance"] = round(y["balance"] / d, 2)
        # la cobertura se mide contra lo que falta DESPUÉS de la pensión; si la pensión
        # sola ya alcanza, la meta está cubierta sin tocar la inversión.
        y["covered_by_pension"] = goal_monthly > 0 and goal_from_portfolio <= 0
        if goal_monthly <= 0:
            y["coverage"] = None
        elif goal_from_portfolio <= 0:
            y["coverage"] = 100.0
        else:
            y["coverage"] = round(received_monthly / goal_from_portfolio * 100, 2)
        # lo que podrías retirar ese año dejando el capital intacto en términos reales
        sustainable_monthly = y["portfolio"] * (sustainable_rate / 100) / 12
        y["sustainable_monthly"] = round(max(0.0, sustainable_monthly), 2)
        if goal_monthly <= 0:
            y["sustainable_coverage"] = None
        elif goal_from_portfolio <= 0:
            y["sustainable_coverage"] = 100.0
        else:
            y["sustainable_coverage"] = round(sustainable_monthly / goal_from_portfolio * 100, 2)

    balance = portfolio + cash
    gain = balance - invested
    last_year_dividends = dividends_total - (
        yearly[-2]["dividends_total"] if len(yearly) > 1 else 0.0
    )

    # el año objetivo es aquel en que se deja de aportar, extraordinarios incluidos
    last_contribution = max((i + 1 for i, a in enumerate(amounts) if a > 0), default=0)
    last_contribution = max(last_contribution, max(lump_by_month, default=0))
    target_year = -(-last_contribution // 12) if last_contribution else 0
    target = next((y for y in yearly if y["year"] == target_year), yearly[-1] if yearly else None)

    first_covered = next(
        (y["year"] for y in yearly if y["coverage"] is not None and y["coverage"] >= 100), None
    )

    # el año en que podrías dejar de aportar y vivir de la rentabilidad para siempre
    fi_year = next(
        (y["year"] for y in yearly
         if y["sustainable_coverage"] is not None and y["sustainable_coverage"] >= 100),
        None,
    ) if sustainable_rate > 0 else None
    fi_row = next((y for y in yearly if y["year"] == fi_year), None) if fi_year else None

    # El capital necesario se mide contra la meta NETA de pensión de ese año.
    ref_row = fi_row or target
    goal_ref = ref_row["goal_from_portfolio"] if ref_row else 0.0
    capital_needed_sustainable = (
        goal_ref * 12 / (sustainable_rate / 100)
        if sustainable_rate > 0 and goal_ref > 0
        else None
    )

    # capital que haría falta para que el yield pague lo que falta ese año
    goal_at_target = target["goal_monthly"] if target else 0.0
    goal_at_target_net = target["goal_from_portfolio"] if target else 0.0
    capital_needed = (
        goal_at_target_net * 12 / (data["dividend_yield"] / 100.0)
        if data["model"] == "dividends" and data["dividend_yield"] > 0 and goal_at_target_net > 0
        else None
    )

    # --- fase de retiro ----------------------------------------------------
    # Desde que se deja de aportar el patrimonio deja de crecer con dinero nuevo y pasa
    # a financiar la meta, con la pensión de la AFP entrando desde la edad de jubilación.
    start_age = data["start_age"]
    retire_to_age = data["retire_to_age"]
    retirement = None
    if start_age > 0 and retire_to_age > start_age and last_contribution:
        fin = int(round((retire_to_age - start_age) * 12))
        inicio = min(last_contribution, fin)
        base = next((mm for mm in months if mm["month"] == inicio), None)
        saldo_inicial = (base["portfolio"] + base["cash"]) if base else 0.0
        comun = dict(
            start_month=inicio, portfolio=saldo_inicial, deflator=deflator,
            monthly_rate=monthly_rate, per_payout=per_payout, payout_months=payout_months,
            pension_today=pension_today, pension_start=pension_start,
        )
        # lo máximo que se puede gastar para llegar justo a cero a la edad objetivo
        max_spend = _max_spend(fin, **comun) if fin > inicio else 0.0
        gasto = max_spend if data["spend_mode"] == "target_age" else goal_monthly_today
        detalle, agotado, saldo_final = _retirement_path(gasto, end_month=fin, rows=True, **comun)
        # Llegar justo a cero en el último mes también es agotarlo: sin esto la tarjeta
        # decía "no se agota" y al lado "quedarían $0", que es la misma cosa dos veces.
        # El umbral es un mes de gasto: menos que eso no financia ni el mes siguiente.
        if agotado is None and saldo_final < gasto * deflator(fin):
            agotado = fin
        retirement = {
            "start_month": inicio,
            "start_age": round(start_age + inicio / 12, 1),
            "end_month": fin,
            "target_age": retire_to_age,
            "spend_mode": data["spend_mode"],
            "spend_monthly_today": round(gasto, 2),
            "max_spend_today": round(max_spend, 2),
            "depletion_month": agotado,
            "depletion_age": round(start_age + agotado / 12, 1) if agotado else None,
            "final_balance": round(saldo_final, 2),
            "final_balance_real": round(saldo_final / deflator(fin), 2) if fin else 0.0,
            "months": detalle,
        }

    # El saldo de la AFP viene en pesos de hoy desde afp.py; al gráfico va en nominales
    # para que se pueda comparar con el patrimonio invertido.
    afp_series = [
        {"month": i + 1, "balance": round(v * deflator(i + 1), 2), "balance_real": round(v, 2)}
        for i, v in enumerate(data["afp_monthly"])
    ]

    # retorno real = (1+nominal)/(1+inflación)-1, no la resta simple
    real_return = ((1 + data["annual_return"] / 100) / (1 + inflation_rate) - 1) * 100

    return {
        "model": data["model"],
        "inflation": data["inflation"],
        "income_goal": goal_monthly_today,
        # La pensión estimada se informa siempre, aunque el escenario elija ignorarla:
        # así la app puede decir "la hay, pero no la estás contando".
        "include_pension": data["include_pension"],
        "pension_monthly": round(data["pension_monthly"], 2),
        "pension_start_month": data["pension_start_month"],
        "pension_start_year": (-(-data["pension_start_month"] // 12)
                               if data["pension_start_month"] else None),
        "real_return_pct": round(real_return, 3),
        "target_year": target_year,
        "goal_monthly_at_target": round(goal_at_target, 2),
        "goal_from_portfolio_at_target": round(goal_at_target_net, 2),
        "pension_at_target": target["pension_monthly"] if target else 0.0,
        "dividend_monthly_at_target": target["dividend_monthly"] if target else 0.0,
        "coverage_at_target": target["coverage"] if target else None,
        "first_year_covered": first_covered,
        "sustainable_rate": round(sustainable_rate, 3) if dividends_on else None,
        "reinvest_share_needed": round(reinvest_share, 1) if reinvest_share is not None else None,
        "fi_year": fi_year,
        "fi_capital": fi_row["portfolio"] if fi_row else None,
        "fi_monthly": fi_row["sustainable_monthly"] if fi_row else None,
        "capital_needed_sustainable": round(capital_needed_sustainable, 2) if capital_needed_sustainable else None,
        "capital_needed_at_target": round(capital_needed, 2) if capital_needed else None,
        "final_real_balance": round((portfolio + cash) / deflator(total_months), 2),
        "reinvest": reinvest,
        "monthly_rate_pct": round(monthly_rate * 100, 6),
        "total_months": total_months,
        "contributing_months": sum(1 for a in amounts if a > 0),
        "lump_sums": lump_rows,
        "total_lump": round(sum(lump_by_month.values()), 2),
        "total_lump_real": round(sum(r["amount"] for r in lump_rows if r["in_range"]), 2),
        "total_invested": round(invested, 2),
        "total_invested_real": round(invested_real, 2),
        "total_reinvested_real": round(reinvested_real, 2),
        "cost_basis_real": round(invested_real + reinvested_real, 2),
        "index_contributions": index_contributions,
        "total_reinvested": round(reinvested, 2),
        "cost_basis": round(invested + reinvested, 2),
        "final_portfolio": round(portfolio, 2),
        "final_cash": round(cash, 2),
        "final_balance": round(balance, 2),
        "total_dividends": round(dividends_total, 2),
        "total_dividends_real": round(dividends_real, 2),
        "total_gain_real": round((portfolio + cash) / deflator(total_months) - invested_real, 2),
        "last_year_dividends": round(last_year_dividends, 2),
        "last_year_dividends_real": round(last_year_dividends / deflator(total_months), 2),
        "total_gain": round(gain, 2),
        "total_capital_gain": round(portfolio - (invested + reinvested), 2),
        "multiple": round(balance / invested, 4) if invested > 0 else None,
        "gain_pct": round(gain / invested * 100, 2) if invested > 0 else None,
        "months": months,
        "yearly": yearly,
        "retirement": retirement,
        "work_until_age": data["work_until_age"],
        "work_until_month": data["work_until_month"],
        "months_trimmed": recortado,
        "afp": data["afp_summary"],
        "afp_series": afp_series,
        "start_age": start_age,
        "life_age": data["life_age"],
        "retire_to_age": retire_to_age,
    }
