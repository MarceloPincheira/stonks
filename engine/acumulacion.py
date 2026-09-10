"""Motor de acumulación: aportes por tramos y capitalización mensual compuesta.

Dos modelos:
  * 'simple'    -> una sola tasa de retorno total anual, reinvertida siempre.
  * 'dividends' -> plusvalía de la cuota + repartos periódicos, con la opción de
                   reinvertirlos o cobrarlos en efectivo.
"""
from .retiro import _max_spend, _retirement_path

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
    # El reparto se DEVENGA mes a mes (yield/12 del valor del fondo) y se paga acumulado
    # en los meses indicados. Repartir en cambio una fracción fija del valor en la fecha
    # de pago hace que el dinero que entra ese mes cobre un trimestre completo de
    # dividendo -- o, al revés, que llegar un mes tarde cueste el reparto entero. El
    # devengo elimina el salto: lo repartido en el año es siempre ≈ valor × yield.
    accrual_rate = (data["dividend_yield"] / 100.0) / 12 if dividends_on else 0.0

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

    # Con aportes indexados, el monto escrito es "pesos de hoy": tiene que valer lo
    # mismo en poder adquisitivo TODOS los meses. Con un escalón anual no lo hacía --
    # se descolgaba hasta 3,4% dentro de cada año con inflación de 3,83% --, así que
    # el factor es EXACTAMENTE el deflactor del mes, igual que los aportes
    # extraordinarios: así el monto escrito vale lo escrito, y los dos campos que la
    # UI etiqueta "pesos de hoy" significan por fin lo mismo.
    index_contributions = data["index_contributions"]
    def contribution_factor(m):
        return (1 + inflation_rate) ** (m / 12) if index_contributions else 1.0

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

    # Los repartos son renta afecta: el art. 107 de la LIR exime el mayor valor en la
    # enajenación, pero no las distribuciones periódicas. Se descuentan antes de
    # reinvertirlos o cobrarlos, que es donde realmente duele: reinvertir el bruto
    # infla el resultado a 30 años en decenas de puntos porcentuales.
    tax_rate = data["dividend_tax"] / 100.0 if dividends_on else 0.0

    portfolio = 0.0      # valor de mercado dentro del fondo
    cash = 0.0           # dividendos cobrados y no reinvertidos
    invested = 0.0       # aportes de tu bolsillo, sin reinversión
    reinvested = 0.0     # dividendos que volvieron al fondo
    dividend_accrual = 0.0       # reparto devengado y aún no pagado
    accrual_by_month = {}
    dividends_total = 0.0        # bruto repartido por el fondo
    dividends_net_total = 0.0    # lo que queda después de impuesto
    dividends_tax_total = 0.0
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

        # devengo del mes sobre el valor del fondo ya capitalizado
        dividend_accrual += portfolio * accrual_rate
        accrual_by_month[m] = dividend_accrual
        dividend = 0.0
        dividend_net = 0.0
        dividend_tax_m = 0.0
        if dividends_on and ((m - 1) % 12) + 1 in payout_months:
            dividend, dividend_accrual = dividend_accrual, 0.0
            accrual_by_month[m] = 0.0
            dividend_tax_m = dividend * tax_rate
            dividend_net = dividend - dividend_tax_m
            dividends_total += dividend
            dividends_tax_total += dividend_tax_m
            dividends_net_total += dividend_net
            dividends_real += dividend_net / deflator(m)
            if reinvest:
                portfolio += dividend_net
                reinvested += dividend_net
                reinvested_real += dividend_net / deflator(m)
            else:
                cash += dividend_net

        months.append(
            {
                "month": m,
                "contribution": round(contribution, 2),
                "lump": round(lump, 2),
                "invested": round(invested, 2),
                "interest": round(growth, 2),
                "dividend": round(dividend, 2),
                "dividend_net": round(dividend_net, 2),
                "dividend_tax": round(dividend_tax_m, 2),
                "dividends_total": round(dividends_total, 2),
                "dividends_net_total": round(dividends_net_total, 2),
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
    prev_net = 0.0
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
                # lo que queda en el bolsillo ese año: es la cifra con que se mide la
                # cobertura de la meta, porque el impuesto no se puede gastar
                "dividends_year_net": round(m["dividends_net_total"] - prev_net, 2),
                "dividends_total": m["dividends_total"],
                "dividends_net_total": m["dividends_net_total"],
                "dividends_real": m["dividends_real"],
                "balance": m["balance"],
                "gain": round(m["balance"] - m["invested"], 2),
            }
        )
        prev_dividends = m["dividends_total"]
        prev_net = m["dividends_net_total"]

    # --- retiro sostenible -------------------------------------------------
    # Para que el capital NO pierda poder adquisitivo debe crecer al menos como la
    # inflación. La plusvalía aporta g; el resto tiene que salir de reinvertir parte
    # de los dividendos. Lo que queda libre para vivir es:
    #     tasa sostenible = yield - max(0, inflación - plusvalía)
    # Si la plusvalía ya iguala a la inflación, puedes consumir todo el dividendo.
    #
    # En el modelo simple no hay reparto que consumir, pero sí hay retiro sostenible:
    # es el retorno REAL (Fisher, no la resta), porque vendiendo esa fracción cada año
    # el capital se mantiene constante en poder adquisitivo. Dejarlo en 0 hacía que la
    # pestaña de poder adquisitivo dijera que de un patrimonio que rinde no se puede
    # sacar nada.
    growth_gap = max(0.0, data["inflation"] - growth_pct)
    net_yield = data["dividend_yield"] * (1 - tax_rate)

    # Retorno total NETO del instrumento: la plusvalía compone con el reparto neto.
    total_net = ((1 + growth_pct / 100) * (1 + net_yield / 100) - 1) if dividends_on \
        else data["annual_return"] / 100
    # Lo máximo que se puede retirar a perpetuidad sin perder poder adquisitivo es el
    # retorno REAL: consumirlo entero deja el capital constante en pesos de hoy.
    sustainable_rate = ((1 + total_net) / (1 + inflation_rate) - 1) * 100

    # Cifra secundaria: cuánto de eso sale SÓLO de los repartos, sin vender una cuota.
    # Es más exigente y era lo único que se informaba antes; con plusvalía por sobre la
    # inflación pedía casi el doble de capital y declaraba inalcanzable una meta que sí
    # se alcanza, porque se negaba a contar la plusvalía real como consumible.
    payout_only_rate = (net_yield - growth_gap) if dividends_on else 0.0
    reinvest_share = (growth_gap / net_yield * 100) if dividends_on and net_yield > 0 else None

    # Desde la edad de jubilación la AFP paga una pensión y la meta que debe cubrir la
    # inversión baja en esa cantidad. La pensión se toma constante en pesos de hoy
    # (las rentas vitalicias y el retiro programado se pagan en UF), o sea que en
    # nominal crece con la inflación igual que la meta.
    pension_today = data["pension_monthly"] if data["include_pension"] else 0.0
    pension_start = data["pension_start_month"] if pension_today > 0 else None

    for y in yearly:
        d = deflator(y["month"])
        div_year = y["dividends_year_net"]
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
    last_year_dividends = dividends_net_total - (
        yearly[-2]["dividends_net_total"] if len(yearly) > 1 else 0.0
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
        goal_at_target_net * 12 / (net_yield / 100.0)
        if data["model"] == "dividends" and net_yield > 0 and goal_at_target_net > 0
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
            monthly_rate=monthly_rate, accrual_rate=accrual_rate * (1 - tax_rate),
            payout_months=payout_months,
            accrual0=accrual_by_month.get(inicio, 0.0) * (1 - tax_rate),
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
            # En años enteros a propósito: con ±1 pp de retorno esta edad se mueve
            # varios años, así que un decimal prometía una precisión que el modelo
            # no tiene. El rango real va en el bloque `sensitivity`.
            "depletion_age": int(round(start_age + agotado / 12)) if agotado else None,
            "final_balance": round(saldo_final, 2),
            "final_balance_real": round(saldo_final / deflator(fin), 2) if fin else 0.0,
            "months": detalle,
        }

    # El saldo de la AFP viene en pesos de hoy desde afp.py; al gráfico va en nominales
    # para que se pueda comparar con el patrimonio invertido.
    afp_series = [
        {"month": i + 1,
         "balance": None if v is None else round(v * deflator(i + 1), 2),
         "balance_real": None if v is None else round(v, 2)}
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
        "sustainable_rate": round(sustainable_rate, 3),
        "payout_only_rate": round(payout_only_rate, 3) if dividends_on else None,
        "total_net_return_pct": round(total_net * 100, 3),
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
        "total_dividends_net": round(dividends_net_total, 2),
        "total_dividends_tax": round(dividends_tax_total, 2),
        "dividend_tax": data["dividend_tax"],
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
