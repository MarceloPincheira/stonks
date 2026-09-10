/** Orquesta la pantalla de resultado: arma las tarjetas y llama a cada pieza.
 *
 *  Las tarjetas miran hasta tres momentos distintos —cuándo dejas de aportar, el fin del
 *  horizonte y la edad objetivo— así que cada una lleva escrito a cuál se refiere. */
import { $ } from "./dom.js";
import { fmtMoney, compactHint } from "./formato.js";
import { estado } from "./estado.js";
import { refreshLumpMeta } from "./plan.js";
import { renderMilestones } from "./hitos.js";
import { renderRetirement, renderPensionHint, renderGoalBanner, renderFiBanner,
         renderSensitivity } from "./banners.js";
import { drawChart } from "./grafico.js";
import { renderDetail } from "./tablas.js";
import { renderAfpBanner } from "./perfil.js";

export function renderResult(r) {
  $("#results-panel").hidden = false;
  const years = parseInt($("#years").value, 10);
  const withDiv = r.model === "dividends";

  // Cada tarjeta lleva su cifra nominal arriba y su equivalente en pesos de hoy
  // debajo: son el mismo dinero, y separarlas en tarjetas distintas confundía.
  // Los equivalentes reales deflactan cada flujo en el momento en que ocurrió,
  // no la suma completa con un solo factor.
  const par = (nominal, real) => ({
    v: fmtMoney(nominal),
    sub: `≈ ${fmtMoney(real)} en pesos de hoy`,
  });
  const solo = (n) => ({ v: fmtMoney(n), sub: compactHint(n) });

  // En la misma grilla conviven hasta tres momentos: cuándo dejas de aportar, dónde
  // termina el horizonte del escenario y hasta qué edad estira la fase de retiro. Son
  // cifras no comparables entre sí, así que cada tarjeta lleva escrito a cuál se refiere.
  const edadEn = (mes) => (r.start_age ? ` · ${(r.start_age + mes / 12).toFixed(0)} años` : "");
  const finAporte = r.work_until_month && r.work_until_month < r.total_months
    ? r.work_until_month : null;
  const alHorizonte = `al año ${years}${edadEn(r.total_months)}`;
  const alDejarDeAportar = finAporte
    ? `hasta el año ${Math.ceil(finAporte / 12)}${edadEn(finAporte)}`
    : alHorizonte;

  // Orden: lo que pones -> lo que genera -> lo que resulta -> cuándo eres libre.
  const kpis = [
    { k: "Aportado por ti", when: alDejarDeAportar,
      ...par(r.total_invested, r.total_invested_real),
      tip: "La suma de todo lo que saliste a poner de tu bolsillo, en los pesos de cada año " +
           "en que lo aportaste. Abajo, ese mismo esfuerzo llevado a pesos de hoy deflactando " +
           "cada aporte en el momento en que lo hiciste." },
  ];
  if (withDiv && r.reinvest) {
    kpis.push({ k: "Aportado + reinvertido", when: alHorizonte,
      ...par(r.cost_basis, r.cost_basis_real),
      tip: "Tus aportes más los dividendos que volvieron al fondo: el capital total que quedó " +
           "trabajando, medido al final del horizonte. No es dinero que saliera de tu bolsillo, " +
           "así que la ganancia no se calcula sobre esta cifra. Ojo: sigue creciendo después de " +
           "que dejas de aportar, porque los dividendos se reinvierten solos — por eso es mayor " +
           "que la tarjeta de al lado, que se congela cuando paras." });
  }
  if (withDiv) {
    kpis.push({ k: r.dividend_tax ? "Dividendos recibidos (netos)" : "Dividendos recibidos",
      when: `acumulado ${alHorizonte}`,
      ...par(r.total_dividends_net, r.total_dividends_real),
      tip: r.dividend_tax
        ? `Lo que queda de los repartos después del ${r.dividend_tax}% de impuesto: el fondo ` +
          `repartió ${fmtMoney(r.total_dividends)} brutos y ${fmtMoney(r.total_dividends_tax)} ` +
          `se fueron en impuesto. Es lo neto lo que se reinvierte o se cobra.`
        : "Todo lo que el fondo repartió a lo largo del horizonte completo. Si reinviertes, " +
          "este dinero ya está dentro del valor total; no se suma aparte." });
    kpis.push({ k: `Dividendos del año ${years}`, when: `sólo ese año`,
      ...par(r.last_year_dividends, r.last_year_dividends_real), cls: "good",
      tip: `Lo que el fondo repartiría durante ese último año solamente, no el acumulado. ` +
           `Dividido por 12 es el ingreso mensual que tendrías ese año.` });
    if (!r.reinvest) {
      kpis.push({ k: "Valor en el fondo", when: alHorizonte, ...solo(r.final_portfolio),
        tip: "El valor de mercado de tus cuotas, sin contar el efectivo que ya cobraste." });
      kpis.push({ k: "Efectivo cobrado", when: alHorizonte, ...solo(r.final_cash),
        tip: "Los dividendos que retiraste en vez de reinvertir. Quedan guardados sin rentar." });
    }
  }
  kpis.push({ k: `Valor total a ${years} años`, when: `año ${years} · sin tocar nada`,
    ...par(r.final_balance, r.final_real_balance),
    cls: "good", hero: true,
    tip: "Todo lo que tendrías al final del horizonte: el valor de mercado de tus cuotas más " +
         "el efectivo cobrado si elegiste no reinvertir." });
  kpis.push({ k: "Ganancia sobre lo aportado", when: alHorizonte,
    ...par(r.total_gain, r.total_gain_real), cls: "good",
    tip: "Valor total menos lo que pusiste de tu bolsillo. Junta las dos fuentes de retorno: " +
         "los dividendos recibidos y la plusvalía de las cuotas." });
  kpis.push({ k: "Multiplicador", when: alHorizonte,
    v: r.multiple ? `${r.multiple.toFixed(2)}×` : "—",
    sub: r.gain_pct !== null ? `+${r.gain_pct.toFixed(0)}% sobre lo aportado` : "",
    tip: "Cuántas veces se multiplicó tu dinero: valor total dividido por lo que aportaste. " +
         "Está en términos nominales, así que parte del multiplicador es sólo inflación." });
  if (r.income_goal) {
    kpis.push({
      k: "Vives de la rentabilidad desde",
      when: r.fi_year ? `año ${r.fi_year}${edadEn(r.fi_year * 12)}` : `no pasa en el horizonte`,
      v: r.fi_year ? `año ${r.fi_year}` : "—",
      sub: r.fi_year
        ? `con ${fmtMoney(r.fi_monthly)} al mes de ese año, sin tocar el capital`
        : `sin tocar el capital no se alcanza en ${Math.round(r.total_months / 12)} años`,
      cls: r.fi_year ? "good" : "",
      tip: "Primer año en que podrías dejar de aportar y vivir de la rentabilidad para siempre. " +
           "Usa el retiro sostenible: el retorno REAL del instrumento, que es lo que se puede " +
           "consumir dejando el capital constante en pesos de hoy.",
    });
  }
  // La fase de retiro no depende del modelo: sirve igual con una tasa única que con
  // dividendos, porque el gasto se financia vendiendo capital si hace falta.
  if (r.retirement && r.income_goal) {
    const ret = r.retirement;
    kpis.push({
      k: "Patrimonio a cero a los",
      when: `consumiendo desde los ${ret.start_age}`,
      v: ret.depletion_age ? `${ret.depletion_age} años` : "no se agota",
      sub: ret.depletion_age
        ? `gastando ${fmtMoney(ret.spend_monthly_today)} al mes en pesos de hoy`
        : `a los ${ret.target_age} quedarían ${fmtMoney(ret.final_balance_real)} de hoy`,
      cls: ret.depletion_age && ret.depletion_age < ret.target_age ? "bad" : "good",
      tip: "A diferencia de la tarjeta anterior, aquí sí se consume el capital y se cuenta " +
           "la pensión. Desde que dejas de aportar el patrimonio financia tu meta, con la pensión de la " +
           "AFP entrando a la edad de jubilación. Si se agota antes de la edad objetivo, la " +
           "meta no es sostenible con este plan.",
    });
    kpis.push({
      k: `Gasto máximo hasta los ${ret.target_age}`,
      when: `de ${ret.start_age} a ${ret.target_age} años`,
      v: `${fmtMoney(ret.max_spend_today)}/mes`,
      sub: "en pesos de hoy, para llegar justo a cero",
      cls: ret.max_spend_today >= r.income_goal ? "good" : "bad",
      tip: "Lo máximo que podrías gastar al mes para que el patrimonio dure exactamente " +
           "hasta la edad objetivo. Si es menor que tu meta, tu meta no alcanza.",
    });
  }
  if (r.life_age) {
    kpis.push({ k: "Expectativa de vida", v: `${r.life_age} años`,
      sub: "la que usa la AFP para calcular tu pensión",
      tip: "Tablas de mortalidad 2020 de la Superintendencia de Pensiones. Es el horizonte " +
           "con que la AFP divide tu saldo, y la edad objetivo por defecto." });
  }
  if (!withDiv) {
    kpis.push({ k: "Meses con aporte", when: `del horizonte completo`,
      v: `${r.contributing_months} / ${r.total_months}`, sub: "",
      tip: "Cuántos meses del horizonte tienen un tramo de aporte definido. El resto de los " +
           "meses el capital sigue rentando, pero sin dinero nuevo." });
  }

  // El recorte por dejar de trabajar se decide en el backend, así que se avisa aquí
  // mismo, junto a los tramos, y no sólo en el texto de la fase de retiro.
  $("#ranges-trim").innerHTML = r.months_trimmed
    ? `· ${r.months_trimmed} meses no se aportan: dejas de trabajar a los ${r.work_until_age}`
    : "";
  refreshLumpMeta(r);
  renderRetirement(r);
  renderMilestones(r);
  if (r.afp) renderAfpBanner(r.afp);
  renderPensionHint(r);
  renderGoalBanner(r);
  renderFiBanner(r);
  renderSensitivity(r);

  $("#kpis").innerHTML = kpis.map((c) =>
    `<div class="kpi${c.hero ? " hero" : ""}"${c.tip ? ` data-tip="${c.tip.replace(/"/g, "&quot;")}"` : ""}>` +
    `<div class="k">${c.k}</div>` +
    (c.when ? `<div class="when">${c.when}</div>` : "") +
    `<div class="v ${c.cls || ""}">${c.v}</div>` +
    (c.sub ? `<div class="sub">${c.sub}</div>` : "") + `</div>`).join("");

  renderHitosLeyenda(r, years, finAporte);
  drawChart(r);
  renderDetail();
}

/** Las tarjetas no miran todas el mismo momento. Sin decirlo, poner una al lado de otra
 *  invita a compararlas como si fueran del mismo instante, y no lo son. */
export function renderHitosLeyenda(r, years, finAporte) {
  const el = $("#kpi-hitos");
  const edad = (mes) => (r.start_age ? ` (${(r.start_age + mes / 12).toFixed(0)} años)` : "");
  const partes = [];
  if (finAporte) {
    partes.push(`dejas de aportar en el <strong>año ${Math.ceil(finAporte / 12)}</strong>` +
                `${edad(finAporte)}`);
  }
  partes.push(`el horizonte del escenario llega al <strong>año ${years}</strong>` +
              `${edad(r.total_months)}`);
  if (r.retirement) {
    partes.push(`y la fase de retiro estira hasta los <strong>${r.retirement.target_age}</strong>`);
  }
  if (partes.length < 2) { el.innerHTML = ""; return; }
  el.innerHTML = `Cada tarjeta dice a qué momento se refiere: ` + partes.join("; ") +
    `. Son cifras de instantes distintos, así que no se comparan entre sí.`;
}
