/** Los textos que interpretan el resultado: fase de retiro, pensión, meta,
 *  independencia financiera y la banda de sensibilidad. */
import { $ } from "./dom.js";
import { fmtMoney } from "./formato.js";
import { estado } from "./estado.js";
import { fondoEn, afpEn } from "./hitos.js";

/** Fase de retiro: hasta cuándo alcanza el patrimonio y cuánto se puede gastar. */
export function renderRetirement(r) {
  const el = $("#retirement-hint");
  const ret = r.retirement;
  // el campo arranca vacío y se rellena con la expectativa de vida de la AFP
  if (!$("#retire_to_age").value && r.life_age) $("#retire_to_age").placeholder = r.life_age;
  if (!$("#work_until_age").value && r.afp) $("#work_until_age").placeholder = r.afp.edad_pension;
  if (!ret) {
    el.innerHTML = r.life_age
      ? `La AFP asume que vives hasta los <strong>${r.life_age}</strong> años.`
      : "Completa <strong>Mi perfil</strong> para proyectar la fase de retiro.";
    return;
  }
  const vida = r.life_age
    ? `La AFP calcula tu pensión suponiendo que vives hasta los <strong>${r.life_age}</strong> ` +
      `años; por eso es la edad que viene por defecto. `
    : "";
  const seAgota = ret.depletion_age
    ? `Con ese gasto el patrimonio invertido llega a <strong class="short">cero a los ` +
      `${ret.depletion_age}</strong> años.`
    : `Con ese gasto el patrimonio <strong class="ok">no se agota</strong>: a los ` +
      `${ret.target_age} años quedarían ${fmtMoney(ret.final_balance_real)} en pesos de hoy.`;

  const veredicto = ret.max_spend_today < r.income_goal
    ? `<br><strong class="short">Con ${fmtMoney(r.income_goal)} al mes no alcanza</strong>: ` +
      `el máximo sostenible hasta los ${ret.target_age} es ${fmtMoney(ret.max_spend_today)}.`
    : "";

  // Todo en pesos de hoy: mezclar nominales con la meta, que está en pesos de hoy,
  // hacía comparar cifras de años distintos.
  const infl = (r.inflation || 0) / 100;
  const aHoy = (v, m) => v / (1 + infl) ** (m / 12);
  const finTrabajo = r.work_until_month && r.work_until_month < ret.start_month
    ? r.work_until_month : ret.start_month;
  const fondoAlParar = aHoy(fondoEn(r, finTrabajo), finTrabajo);
  const afpAlParar = aHoy(afpEn(r, finTrabajo) || 0, finTrabajo);

  const trabajo = r.work_until_age
    ? `Trabajas hasta los <strong>${r.work_until_age}</strong>: ahí se cortan las ` +
      `cotizaciones a la AFP —llevarías <strong>${fmtMoney(afpAlParar)}</strong> acumulados— ` +
      `y también los aportes al fondo, que salen del mismo sueldo` +
      (r.months_trimmed ? ` (${r.months_trimmed} meses de tramos quedaron fuera)` : "") + `. `
    : "";

  el.innerHTML = vida + trabajo +
    `Dejas de aportar a los <strong>${ret.start_age}</strong> años con ` +
    `<strong>${fmtMoney(fondoAlParar)}</strong> en el fondo más ${fmtMoney(afpAlParar)} en la ` +
    `AFP —<strong>${fmtMoney(fondoAlParar + afpAlParar)}</strong> en total, en pesos de hoy— ` +
    `y desde ahí consumes ${fmtMoney(ret.spend_monthly_today)} al mes. ` +
    seAgota +
    ` Para llegar justo a cero a los <strong>${ret.target_age}</strong> podrías gastar ` +
    `<strong class="ok">${fmtMoney(ret.max_spend_today)}</strong> al mes en pesos de hoy` +
    (r.pension_monthly && r.include_pension
      ? `, pensión de la AFP incluida.` : `, sin contar la pensión de la AFP.`) + veredicto;
}

/** Desde la jubilación parte de la meta la paga la AFP; la inversión sólo cubre el resto. */
export function renderPensionHint(r) {
  const el = $("#pension-hint");
  if (!r.pension_monthly) {
    el.innerHTML = estado.profileData && estado.profileData.profile
      ? "Tu perfil no alcanza a proyectar una pensión."
      : "Completa <strong>Mi perfil</strong> para estimarla.";
    return;
  }
  const dentro = r.pension_start_year <= Math.round(r.total_months / 12);
  el.innerHTML =
    `Desde el año <strong>${r.pension_start_year}</strong> la AFP pagaría ` +
    `<strong>${fmtMoney(r.pension_monthly)}</strong> al mes en pesos de hoy` +
    (r.include_pension
      ? `, así que la inversión sólo cubre la diferencia.`
      : `, pero no se está descontando de la meta.`) +
    (dentro ? "" : ` Tu horizonte llega al año ${Math.round(r.total_months / 12)}: ` +
      `alárgalo para verla entrar.`);
}

/** Los banners de arriba miran sólo hasta el fin del horizonte y sin consumir capital;
 *  la fase de retiro sigue después. Sin este puente las dos lecturas se contradicen a
 *  la vista: "no alcanzas la meta" junto a "el patrimonio no se agota nunca". */
export function puenteRetiro(r) {
  const ret = r.retirement;
  if (!ret) return "";
  const desenlace = ret.depletion_age
    ? `el patrimonio duraría hasta los <strong>${ret.depletion_age}</strong> años`
    : `el patrimonio <strong class="ok">no se agota</strong> hasta los ${ret.target_age}`;
  return ` Ojo: esto mira sólo hasta el año ${Math.round(r.total_months / 12)} y sin tocar el ` +
    `capital. Consumiéndolo, y con la pensión de la AFP, ${desenlace} ` +
    `(ver <em>fase de retiro</em>).`;
}

/** La respuesta a "¿cuánto necesito recibir en el año X para vivir como hoy?" */
export function renderGoalBanner(r) {
  const host = $("#goal-banner");
  if (r.model !== "dividends" || !r.income_goal) {
    host.hidden = true;
    return;
  }
  host.hidden = false;
  const cov = r.coverage_at_target;
  const alcanza = cov !== null && cov >= 100;
  const falta = r.goal_from_portfolio_at_target - r.dividend_monthly_at_target;
  const pension = r.pension_at_target
    ? ` De eso, la AFP pondría <strong>${fmtMoney(r.pension_at_target)}</strong>, así que a la ` +
      `inversión le tocan <strong>${fmtMoney(r.goal_from_portfolio_at_target)}</strong>.`
    : "";

  const cuando = r.first_year_covered
    ? `Alcanzas la meta en el <strong class="ok">año ${r.first_year_covered}</strong>.`
    : `<strong class="short">No alcanzas la meta</strong> dentro del horizonte.`;

  host.innerHTML =
    `Para vivir en el <strong>año ${r.target_year}</strong> como hoy con ` +
    `<strong>${fmtMoney(r.income_goal)}</strong> al mes, necesitarás ` +
    `<strong>${fmtMoney(r.goal_monthly_at_target)}</strong> mensuales ` +
    `(inflación ${r.inflation}% anual).${pension} ` +
    `Tus dividendos ese año rendirían <strong>${fmtMoney(r.dividend_monthly_at_target)}</strong> al mes: ` +
    `<strong class="${alcanza ? "ok" : "short"}">${cov === null ? "—" : cov.toFixed(0) + "% de la meta"}</strong>` +
    (alcanza ? "" : ` (faltan ${fmtMoney(falta)} al mes)`) + `. ${cuando}` +
    (r.pension_monthly && !r.pension_at_target && r.include_pension
      ? ` A esa edad todavía no hay pensión: entra a los ${r.afp ? r.afp.edad_pension : 65}.`
      : "") + puenteRetiro(r);
}

/** ¿Cuándo puedes vivir de la rentabilidad sin que el capital pierda poder adquisitivo? */
export function renderFiBanner(r) {
  const host = $("#fi-banner");
  if (!r.income_goal) {
    host.hidden = true;
    return;
  }
  host.hidden = false;

  if (!r.sustainable_rate || r.sustainable_rate <= 0) {
    host.innerHTML =
      `<strong class="short">Nunca es sostenible con estos supuestos.</strong> ` +
      `El retorno real es ${r.sustainable_rate}% anual: con una inflación de ${r.inflation}% ` +
      `el capital no le gana al alza de precios, así que cualquier retiro lo descapitaliza.`;
    return;
  }

  // El retiro sostenible es el retorno REAL: consumirlo entero deja el capital constante
  // en pesos de hoy. La cifra de "sólo repartos" va como secundaria porque es más
  // exigente -- exige no vender nunca -- y por sí sola pedía casi el doble de capital.
  const soloRepartos = (r.payout_only_rate !== null && r.payout_only_rate !== undefined)
    ? ` De ese total, <strong>${r.payout_only_rate}%</strong> lo ponen los repartos sin vender ` +
      `nada; el resto sale de vender cada año la plusvalía que exceda la inflación.`
    : "";
  const base =
    `<strong>Retiro sostenible: ${r.sustainable_rate}% anual</strong> del capital — el ` +
    `retorno real, o sea lo que puedes consumir dejando el capital constante en pesos de hoy.` +
    soloRepartos + ` `;

  host.innerHTML = base + (r.fi_year
    ? `Podrías dejar de aportar y vivir de la rentabilidad <strong class="ok">desde el año ${r.fi_year}</strong>, ` +
      `con <strong>${fmtMoney(r.fi_capital)}</strong> invertidos que rendirían ` +
      `<strong>${fmtMoney(r.fi_monthly)}</strong> al mes de forma indefinida.`
    : `<strong class="short">No alcanzas ese punto</strong> dentro del horizonte: ` +
      `harían falta <strong>${fmtMoney(r.capital_needed_sustainable)}</strong> invertidos ` +
      `para sostener tu meta en el año ${r.target_year}.`) + puenteRetiro(r);
}

/** La proyección es un escenario, no un pronóstico. Esta franja dice cuánto se mueven
 *  las cifras que la app publica con ±1 punto de retorno y ±1 punto de inflación, que
 *  es menos de una desviación estándar histórica. Sin esto, "se agota a los 71" se lee
 *  como una medición. */
export function renderSensitivity(r) {
  const host = $("#sensitivity-banner");
  const sens = estado.lastSensitivity;
  if (!sens) { host.hidden = true; return; }
  const rg = sens.rangos;
  const partes = [];

  const edad = rg.depletion_age;
  if (edad && edad.central !== null) {
    partes.push(edad.min === edad.max
      ? `el patrimonio se agota a los <strong>${edad.central}</strong>`
      : `el patrimonio se agota entre los <strong>${edad.min}</strong> y los ` +
        `<strong>${edad.max}</strong> años` +
        (edad.indefinido ? " (o no se agota)" : ""));
  } else if (edad && edad.indefinido && edad.min !== null) {
    partes.push(`el patrimonio puede no agotarse, o agotarse a los <strong>${edad.min}</strong>`);
  }

  const gasto = rg.max_spend_today;
  if (gasto && gasto.central !== null && gasto.min !== gasto.max) {
    partes.push(`el gasto máximo va de <strong>${fmtMoney(gasto.min)}</strong> a ` +
                `<strong>${fmtMoney(gasto.max)}</strong> al mes`);
  }

  const saldo = rg.final_real_balance;
  if (saldo && saldo.central !== null && saldo.min !== saldo.max) {
    partes.push(`el patrimonio final en pesos de hoy va de <strong>${fmtMoney(saldo.min)}</strong> ` +
                `a <strong>${fmtMoney(saldo.max)}</strong>`);
  }

  if (!partes.length) { host.hidden = true; return; }
  host.hidden = false;
  host.innerHTML =
    `<strong>Esto es un escenario, no un pronóstico.</strong> Moviendo el retorno ` +
    `±${sens.paso_pp} punto y la inflación ±${sens.paso_pp} punto —menos de una desviación ` +
    `estándar histórica—, ` + partes.join("; ") + `. Las cifras de arriba son el caso ` +
    `central de ese rango, no una medición.`;
}
