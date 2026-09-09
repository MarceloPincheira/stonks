const $ = (sel) => document.querySelector(sel);
const MESES = ["enero", "febrero", "marzo", "abril", "mayo", "junio", "julio", "agosto",
  "septiembre", "octubre", "noviembre", "diciembre"];

const rangesBody = $("#ranges-body");
const lumpsBody = $("#lumps-body");

let currentId = null;      // id del escenario cargado (null = nuevo)
let lastResult = null;     // último cálculo, para las tablas
let detailView = "yearly";
let chartUnits = "nominal";      // nominal | real (deflactado a pesos de hoy)
let calcSeq = 0;           // descarta respuestas que llegan fuera de orden
let calcTimer = null;
let planTimer = null;

const CURRENCY_SYMBOL = { CLP: "$", USD: "US$", EUR: "€", UF: "UF " };

function fmtMoney(n) {
  const cur = $("#currency").value;
  const decimals = cur === "CLP" ? 0 : 2;
  return (CURRENCY_SYMBOL[cur] || "") + n.toLocaleString("es-CL", {
    minimumFractionDigits: decimals,
    maximumFractionDigits: decimals,
  });
}

/** Los montos se editan como texto con separador de miles: con un input number
 *  crudo es muy fácil escribir 100000 creyendo que son 1.000.000. */
function parseAmount(raw) {
  const clean = String(raw).replace(/\./g, "").replace(",", ".").replace(/[^\d.-]/g, "");
  return clean === "" ? NaN : parseFloat(clean);
}

function formatAmount(n) {
  return Number.isFinite(n) ? n.toLocaleString("es-CL", { maximumFractionDigits: 2 }) : "";
}

/** Reformatea mientras se escribe, manteniendo el cursor donde estaba. */
function reformatAmountInput(input) {
  const raw = input.value;
  const partialDecimals = raw.match(/,\d*$/);   // no pisar una coma a medio escribir
  const posFromEnd = raw.length - input.selectionStart;
  const n = parseAmount(raw);
  if (!Number.isFinite(n)) return;
  input.value = partialDecimals
    ? formatAmount(Math.trunc(n)) + partialDecimals[0]
    : formatAmount(n);
  const pos = Math.max(0, input.value.length - posFromEnd);
  input.setSelectionRange(pos, pos);
}

const dividendsOn = () => $("#model-dividends").checked;

let inflationPresets = [];

/** Ventanas históricas del IPC chileno. Una ventana corta puede caer entera en un
 *  régimen benigno o en uno de crisis, así que el selector muestra cuántos años de
 *  crisis cubre cada una. */
async function loadInflationPresets() {
  const data = await api("GET", "/api/inflation");
  inflationPresets = data.presets;
  const sel = $("#inflation-preset");
  sel.innerHTML = inflationPresets
    .map((p) => `<option value="${p.key}"${p.recommended ? " selected" : ""}>` +
      `${p.label}${p.recommended ? " ✓" : ""}</option>`).join("") +
    `<option value="custom">Personalizado</option>`;
  syncInflationDetail();
}

function syncInflationDetail() {
  const sel = $("#inflation-preset");
  const preset = inflationPresets.find((p) => p.key === sel.value);
  const actual = parseFloat($("#inflation").value);
  // Si el valor escrito ya no corresponde al preset, el selector pasa a Personalizado.
  if (preset && Math.abs(preset.value - actual) > 0.005) {
    sel.value = "custom";
  }
  const chosen = inflationPresets.find((p) => p.key === sel.value);
  $("#inflation-detail").textContent = chosen
    ? chosen.detail
    : "Valor propio: la proyección usa exactamente lo que escribas.";
}

function applyInflationPreset() {
  const preset = inflationPresets.find((p) => p.key === $("#inflation-preset").value);
  if (preset) $("#inflation").value = preset.value;
  syncInflationDetail();
}

function syncIndexUI() {
  const on = $("#index_contributions").checked;
  $("#th-amount").innerHTML = on
    ? 'Aporte mensual <span class="tag">pesos de hoy</span>'
    : "Aporte mensual";
  $("#index-hint").textContent = on
    ? "El monto sube con la inflación cada año, como un reajuste de sueldo."
    : "Aportas siempre el mismo monto nominal, que pierde poder adquisitivo con los años.";
}

function syncModelUI() {
  const on = dividendsOn();
  $("#fields-simple").hidden = on;
  $("#fields-dividends").hidden = !on;
  $("#reinvest-row").hidden = !on;
  $("#reinvest-hint").textContent = $("#reinvest").checked
    ? "Los dividendos vuelven al fondo y componen."
    : "Los dividendos se acumulan en efectivo, sin rentar.";
}

// --- tramos ---------------------------------------------------------

function addRange(start, end, amount) {
  // el monto puede venir como número (de la BD) o como texto ya formateado
  const monto = typeof amount === "number" ? amount : parseAmount(amount);
  const tr = document.createElement("tr");
  tr.innerHTML = `
    <td><input type="number" class="start" min="1" step="1" value="${start}"></td>
    <td><input type="number" class="end" min="1" step="1" value="${end}"></td>
    <td><input type="text" class="amount" inputmode="decimal" value="${formatAmount(monto)}"></td>
    <td class="num months">—</td>
    <td><button type="button" class="icon" title="Eliminar tramo">×</button></td>`;
  tr.querySelector("button").addEventListener("click", () => {
    tr.remove();
    refreshRangeMeta();
    scheduleCalculate();
  });
  rangesBody.appendChild(tr);
  refreshRangeMeta();
}

/** Aportes extraordinarios: un mes de calendario y un monto en pesos de hoy. Van en el
 *  perfil junto al plan de aporte, así que valen para todos los escenarios. */
function addLump(year, month, amount, label = "") {
  const monto = typeof amount === "number" ? amount : parseAmount(amount);
  const tr = document.createElement("tr");
  tr.innerHTML = `
    <td><select class="lump-month">${MESES.map((n, i) =>
      `<option value="${i + 1}"${i + 1 === month ? " selected" : ""}>${n}</option>`).join("")}</select></td>
    <td><input type="number" class="lump-year" step="1" min="1900" max="2200" value="${year}"></td>
    <td><input type="text" class="amount lump-amount" inputmode="decimal" value="${formatAmount(monto)}"></td>
    <td class="num lump-nominal">—</td>
    <td><button type="button" class="icon" title="Eliminar aporte">×</button></td>`;
  tr.dataset.label = label;
  tr.querySelector("button").addEventListener("click", () => {
    tr.remove();
    scheduleCalculate();
    schedulePlanSave();
  });
  lumpsBody.appendChild(tr);
}

function readLumps() {
  return [...lumpsBody.querySelectorAll("tr")].map((tr) => ({
    year: parseInt(tr.querySelector(".lump-year").value, 10),
    month: parseInt(tr.querySelector(".lump-month").value, 10),
    amount: parseAmount(tr.querySelector(".lump-amount").value),
    label: tr.dataset.label || "",
  }));
}

/** Escribe en cada fila el valor nominal que calculó el backend para ese mes. */
function refreshLumpMeta(r) {
  const filas = [...lumpsBody.querySelectorAll("tr")];
  const calculados = (r && r.lump_sums) || [];
  filas.forEach((tr, i) => {
    const l = readLumps()[i];
    const celda = tr.querySelector(".lump-nominal");
    const calc = calculados.find((c) => c.year === l.year && c.month === l.month);
    if (!calc) { celda.textContent = "—"; celda.classList.remove("short"); return; }
    celda.classList.toggle("short", !calc.in_range);
    celda.textContent = calc.in_range
      ? `${fmtMoney(calc.amount_nominal)} · mes ${calc.projection_month}`
      : "fuera del horizonte";
  });
  const total = (r && r.total_lump_real) || 0;
  $("#lumps-summary").textContent = total
    ? `${filas.length} aporte${filas.length === 1 ? "" : "s"} extraordinario` +
      `${filas.length === 1 ? "" : "s"}: ${fmtMoney(total)} en pesos de hoy ` +
      `(${fmtMoney(r.total_lump)} nominales).`
    : "";
}

function nextStartMonth() {
  const ends = readRanges().map((r) => r.end_month).filter((n) => Number.isFinite(n));
  return ends.length ? Math.max(...ends) + 1 : 1;
}

function readRanges() {
  return [...rangesBody.querySelectorAll("tr")].map((tr) => ({
    start_month: parseInt(tr.querySelector(".start").value, 10),
    end_month: parseInt(tr.querySelector(".end").value, 10),
    amount: parseAmount(tr.querySelector(".amount").value),
  }));
}

function refreshRangeMeta() {
  let totalMonths = 0;
  let maxEnd = 0;
  [...rangesBody.querySelectorAll("tr")].forEach((tr) => {
    const s = parseInt(tr.querySelector(".start").value, 10);
    const e = parseInt(tr.querySelector(".end").value, 10);
    const cell = tr.querySelector(".months");
    if (Number.isFinite(s) && Number.isFinite(e) && e >= s) {
      totalMonths += e - s + 1;
      maxEnd = Math.max(maxEnd, e);
      cell.textContent = e - s + 1;
    } else {
      cell.textContent = "—";
    }
  });

  const years = parseInt($("#years").value, 10);
  const el = $("#ranges-summary");
  el.textContent = "";

  const info = document.createElement("span");
  info.textContent = `${totalMonths} meses de aporte definidos`;
  if (Number.isFinite(years)) {
    info.textContent += ` · horizonte ${years * 12} meses (${years} años)`;
  }
  el.appendChild(info);

  if (Number.isFinite(years) && maxEnd > years * 12) {
    const needed = Math.ceil(maxEnd / 12);
    const warn = document.createElement("span");
    warn.className = "warn";
    warn.textContent = ` ⚠️ tus tramos llegan al mes ${maxEnd} (${needed} años): los aportes ` +
      `posteriores al mes ${years * 12} se ignoran.`;
    const fix = document.createElement("button");
    fix.type = "button";
    fix.className = "link";
    fix.textContent = `Extender horizonte a ${needed} años`;
    fix.addEventListener("click", () => {
      $("#years").value = needed;
      refreshRangeMeta();
      scheduleCalculate(0);
    });
    warn.appendChild(fix);
    el.appendChild(warn);
  }
}

// --- payload / errores ----------------------------------------------

function payload() {
  return {
    name: $("#name").value,
    years: parseInt($("#years").value, 10),
    currency: $("#currency").value,
    model: dividendsOn() ? "dividends" : "simple",
    annual_return: parseFloat($("#annual_return").value),
    appreciation: parseFloat($("#appreciation").value),
    dividend_yield: parseFloat($("#dividend_yield").value),
    reinvest: $("#reinvest").checked,
    inflation: parseFloat($("#inflation").value),
    income_goal: parseAmount($("#income_goal").value),
    index_contributions: $("#index_contributions").checked,
    include_pension: $("#include_pension").checked,
    work_until_age: parseFloat($("#work_until_age").value) || 0,
    retire_to_age: parseFloat($("#retire_to_age").value) || 0,
    spend_mode: $("#spend_mode").value,
    payout_months: $("#payout_months").value
      .split(/[,\s]+/).filter(Boolean).map((n) => parseInt(n, 10)),
    ranges: readRanges(),
    lump_sums: readLumps(),
  };
}

function showError(msg) {
  const el = $("#error");
  if (!msg) { el.hidden = true; return; }
  el.textContent = msg;
  el.hidden = false;
}

async function api(method, url, body) {
  const res = await fetch(url, {
    method,
    headers: body ? { "Content-Type": "application/json" } : {},
    body: body ? JSON.stringify(body) : undefined,
  });
  const data = res.status === 204 ? null : await res.json();
  if (!res.ok) {
    const err = new Error((data && data.error) || `Error ${res.status}`);
    err.status = res.status;
    throw err;
  }
  return data;
}

// --- cálculo y render -----------------------------------------------

function setStatus(text, cls = "") {
  const el = $("#status");
  el.textContent = text;
  el.className = "status " + cls;
}

function scheduleCalculate(delay = 220) {
  clearTimeout(calcTimer);
  calcTimer = setTimeout(calculate, delay);
}

/** Mientras se edita un campo quedan valores a medio escribir; no vale la pena
 *  golpear el backend con ellos ni mostrar errores que se corrigen solos. */
function isComplete(p) {
  if (!Number.isFinite(p.years)) return false;
  if (p.model === "simple" && !Number.isFinite(p.annual_return)) return false;
  if (!Number.isFinite(p.inflation) || !Number.isFinite(p.income_goal)) return false;
  if (p.model === "dividends") {
    if (!Number.isFinite(p.appreciation) || !Number.isFinite(p.dividend_yield)) return false;
    if (!p.payout_months.length || p.payout_months.some((m) => !Number.isFinite(m))) return false;
  }
  if (!p.lump_sums.every((l) =>
      Number.isFinite(l.year) && Number.isFinite(l.month) && Number.isFinite(l.amount))) {
    return false;
  }
  return p.ranges.every((r) =>
    Number.isFinite(r.start_month) && Number.isFinite(r.end_month) && Number.isFinite(r.amount));
}

async function calculate() {
  const body = payload();
  if (!isComplete(body)) {
    setStatus("esperando datos…", "muted");
    return;
  }
  const seq = ++calcSeq;
  setStatus("calculando…", "muted");
  try {
    const data = await api("POST", "/api/calculate", body);
    if (seq !== calcSeq) return;      // ya hay un cálculo más nuevo en curso
    showError("");
    lastResult = data.result;
    renderResult(data.result);
    setStatus("actualizado", "ok");
  } catch (e) {
    if (seq !== calcSeq) return;
    showError(e.message);
    setStatus("sin actualizar", "bad");
  }
}

function renderResult(r) {
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

  // Orden: lo que pones -> lo que genera -> lo que resulta -> cuándo eres libre.
  const kpis = [
    { k: "Aportado por ti", ...par(r.total_invested, r.total_invested_real),
      tip: "La suma de todo lo que saliste a poner de tu bolsillo, en los pesos de cada año " +
           "en que lo aportaste. Abajo, ese mismo esfuerzo llevado a pesos de hoy deflactando " +
           "cada aporte en el momento en que lo hiciste." },
  ];
  if (withDiv && r.reinvest) {
    kpis.push({ k: "Aportado + reinvertido", ...par(r.cost_basis, r.cost_basis_real),
      tip: "Tus aportes más los dividendos que volvieron al fondo: el capital total que quedó " +
           "trabajando. No es dinero que saliera de tu bolsillo, así que la ganancia no se " +
           "calcula sobre esta cifra." });
  }
  if (withDiv) {
    kpis.push({ k: "Dividendos recibidos", ...par(r.total_dividends, r.total_dividends_real),
      tip: "Todo lo que el fondo repartió a lo largo del horizonte completo. Si reinviertes, " +
           "este dinero ya está dentro del valor total; no se suma aparte." });
    kpis.push({ k: `Dividendos del año ${years}`,
      ...par(r.last_year_dividends, r.last_year_dividends_real), cls: "good",
      tip: `Lo que el fondo repartiría durante ese último año solamente, no el acumulado. ` +
           `Dividido por 12 es el ingreso mensual que tendrías ese año.` });
    if (!r.reinvest) {
      kpis.push({ k: "Valor en el fondo", ...solo(r.final_portfolio),
        tip: "El valor de mercado de tus cuotas, sin contar el efectivo que ya cobraste." });
      kpis.push({ k: "Efectivo cobrado", ...solo(r.final_cash),
        tip: "Los dividendos que retiraste en vez de reinvertir. Quedan guardados sin rentar." });
    }
  }
  kpis.push({ k: `Valor total a ${years} años`, ...par(r.final_balance, r.final_real_balance),
    cls: "good", hero: true,
    tip: "Todo lo que tendrías al final del horizonte: el valor de mercado de tus cuotas más " +
         "el efectivo cobrado si elegiste no reinvertir." });
  kpis.push({ k: "Ganancia sobre lo aportado", ...par(r.total_gain, r.total_gain_real),
    cls: "good",
    tip: "Valor total menos lo que pusiste de tu bolsillo. Junta las dos fuentes de retorno: " +
         "los dividendos recibidos y la plusvalía de las cuotas." });
  kpis.push({ k: "Multiplicador", v: r.multiple ? `${r.multiple.toFixed(2)}×` : "—",
    sub: r.gain_pct !== null ? `+${r.gain_pct.toFixed(0)}% sobre lo aportado` : "",
    tip: "Cuántas veces se multiplicó tu dinero: valor total dividido por lo que aportaste. " +
         "Está en términos nominales, así que parte del multiplicador es sólo inflación." });
  if (withDiv && r.income_goal) {
    kpis.push({
      k: "Vives de la rentabilidad desde",
      v: r.fi_year ? `año ${r.fi_year}` : "—",
      sub: r.fi_year
        ? `con ${fmtMoney(r.fi_monthly)} al mes de ese año, sin tocar el capital`
        : `sin tocar el capital no se alcanza en ${Math.round(r.total_months / 12)} años`,
      cls: r.fi_year ? "good" : "",
      tip: "Primer año en que podrías dejar de aportar y vivir de la rentabilidad para siempre. " +
           "Usa el retiro sostenible (el yield menos lo que hay que reinvertir para que la " +
           "inflación no carcoma el capital), no el dividendo completo.",
    });
  }
  // La fase de retiro no depende del modelo: sirve igual con una tasa única que con
  // dividendos, porque el gasto se financia vendiendo capital si hace falta.
  if (r.retirement && r.income_goal) {
    const ret = r.retirement;
    kpis.push({
      k: "Patrimonio a cero a los",
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
    kpis.push({ k: "Meses con aporte", v: `${r.contributing_months} / ${r.total_months}`, sub: "",
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

  $("#kpis").innerHTML = kpis.map((c) =>
    `<div class="kpi${c.hero ? " hero" : ""}"${c.tip ? ` data-tip="${c.tip.replace(/"/g, "&quot;")}"` : ""}>` +
    `<div class="k">${c.k}</div>` +
    `<div class="v ${c.cls || ""}">${c.v}</div>` +
    (c.sub ? `<div class="sub">${c.sub}</div>` : "") + `</div>`).join("");

  drawChart(r);
  renderDetail();
}

/** Saldo del fondo en un mes cualquiera, sea de la acumulación o de la fase de retiro. */
function fondoEn(r, mes) {
  const ret = r.retirement;
  if (ret && mes > ret.start_month) {
    const fila = ret.months.find((m) => m.month === mes);
    if (fila) return fila.balance;
  }
  const fila = r.months[mes - 1];
  return fila ? fila.balance : 0;
}

function afpEn(r, mes) {
  const fila = (r.afp_series || [])[mes - 1];
  return fila ? fila.balance : 0;
}

/** Tabla de hitos: dónde está toda la plata en cada momento que importa. Va en pesos
 *  de hoy, que es la única unidad en que las cifras de años distintos son comparables. */
function renderMilestones(r) {
  const wrap = $("#milestones-wrap");
  const ret = r.retirement;
  if (!ret || !r.afp_series || !r.afp_series.length) { wrap.hidden = true; return; }
  wrap.hidden = false;

  const infl = (r.inflation || 0) / 100;
  const real = (v, m) => v / (1 + infl) ** (m / 12);
  const edadEn = (m) => (r.start_age + m / 12).toFixed(1);
  const pensionMes = r.pension_start_month;
  const finTrabajo = r.work_until_month && r.work_until_month < ret.start_month
    ? r.work_until_month : ret.start_month;

  const hitos = [
    { mes: 1, hito: "Empiezas a invertir",
      nota: "El fondo arranca con tu primer aporte; la AFP, con lo que ya tienes acumulado." },
    { mes: finTrabajo, hito: "Dejas de trabajar",
      nota: `Se cortan las cotizaciones y los aportes al fondo. Desde aquí ninguna de las ` +
            `dos recibe plata nueva.` },
    { mes: pensionMes, hito: `Jubilas (${r.afp ? r.afp.edad_pension : 65})`,
      nota: `La AFP empieza a pagarte ${fmtMoney(r.pension_monthly)} al mes` +
            (r.include_pension ? "" : " (no la estás contando)") +
            `, así que el fondo aporta menos.` },
    { mes: ret.end_month, hito: "Edad objetivo",
      nota: `La AFP se agota justo en la expectativa de vida (${r.life_age}); el fondo llega ` +
            `con lo que quede.` },
  ];
  if (ret.depletion_month && ret.depletion_month < ret.end_month) {
    hitos.splice(3, 0, { mes: ret.depletion_month, hito: "Se acaba el fondo",
      nota: `Desde aquí vives sólo de la pensión: te faltarían ` +
            `${fmtMoney(ret.spend_monthly_today - (r.include_pension ? r.pension_monthly : 0))} ` +
            `al mes en pesos de hoy.` });
  }
  // si dejas de trabajar justo al jubilar, no vale la pena repetir la fila
  const vistos = new Set();
  const filas = hitos.filter((h) => h.mes > 0 && !vistos.has(h.mes) && vistos.add(h.mes) !== false);

  $("#milestones tbody").innerHTML = filas.map((h) => {
    const fondo = real(fondoEn(r, h.mes), h.mes);
    const afp = real(afpEn(r, h.mes), h.mes);
    return `<tr${h.mes === finTrabajo ? ' class="hito-clave"' : ""}>` +
      `<td>${h.hito}</td><td>${edadEn(h.mes)}</td>` +
      `<td class="num">${fmtMoney(fondo)}</td><td class="num">${fmtMoney(afp)}</td>` +
      `<td class="num"><strong>${fmtMoney(fondo + afp)}</strong></td>` +
      `<td>${h.nota}</td></tr>`;
  }).join("");
}

/** Fase de retiro: hasta cuándo alcanza el patrimonio y cuánto se puede gastar. */
function renderRetirement(r) {
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
  const afpAlParar = aHoy(afpEn(r, finTrabajo), finTrabajo);

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
function renderPensionHint(r) {
  const el = $("#pension-hint");
  if (!r.pension_monthly) {
    el.innerHTML = profileData && profileData.profile
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
function puenteRetiro(r) {
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
function renderGoalBanner(r) {
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

const THEME = {
  afp: "#38bdf8",
  retirement: "#f472b6",
  balance: "#4ade80",
  invested: "#60a5fa",
  portfolio: "#a78bfa",
  cash: "#fbbf24",
  grid: "#252c36",
  text: "#93a1b3",
  tooltipBg: "#1e242d",
};

let chart = null;

/** ¿Cuándo puedes vivir de la rentabilidad sin que el capital pierda poder adquisitivo? */
function renderFiBanner(r) {
  const host = $("#fi-banner");
  if (r.model !== "dividends" || !r.income_goal) {
    host.hidden = true;
    return;
  }
  host.hidden = false;

  if (!r.sustainable_rate || r.sustainable_rate <= 0) {
    host.innerHTML =
      `<strong class="short">Nunca es sostenible con estos supuestos.</strong> ` +
      `Con una plusvalía de ${$("#appreciation").value}% bajo una inflación de ${r.inflation}%, ` +
      `el yield completo no alcanza ni para reponer lo que el capital pierde cada año. ` +
      `Habría que subir la plusvalía o el yield.`;
    return;
  }

  const brecha = r.reinvest_share_needed;
  const base =
    `<strong>Retiro sostenible: ${r.sustainable_rate}% anual</strong> del capital ` +
    (brecha > 0
      ? `(el yield es ${$("#dividend_yield").value}%, pero hay que reinvertir siempre el ` +
        `<strong>${brecha}%</strong> de los dividendos para que el capital no pierda ` +
        `poder adquisitivo frente a la inflación). `
      : `(la plusvalía ya cubre la inflación, así que puedes consumir todo el dividendo). `);

  host.innerHTML = base + (r.fi_year
    ? `Podrías dejar de aportar y vivir de la rentabilidad <strong class="ok">desde el año ${r.fi_year}</strong>, ` +
      `con <strong>${fmtMoney(r.fi_capital)}</strong> invertidos que rendirían ` +
      `<strong>${fmtMoney(r.fi_monthly)}</strong> al mes de forma indefinida.`
    : `<strong class="short">No alcanzas ese punto</strong> dentro del horizonte: ` +
      `harían falta <strong>${fmtMoney(r.capital_needed_sustainable)}</strong> invertidos ` +
      `para sostener tu meta en el año ${r.target_year}.`) + puenteRetiro(r);
}

/** El eje va más allá del horizonte cuando hay fase de retiro: hasta la edad objetivo. */
function chartSpan(r) {
  const ret = r.retirement;
  return Math.max(r.total_months, ret ? ret.end_month : 0, (r.afp_series || []).length);
}

/** Alinea una serie corta al eje completo rellenando con null (Chart.js corta la línea). */
function padSeries(values, span, from = 0) {
  const out = new Array(span).fill(null);
  values.forEach((v, i) => { if (from + i < span) out[from + i] = v; });
  return out;
}

function drawChart(r) {
  const showCash = r.model === "dividends" && !r.reinvest;
  const span = chartSpan(r);
  const ret = r.retirement;
  // Cuando hay fase de retiro las dos curvas del fondo son el mismo dinero bajo
  // supuestos opuestos, así que el nombre tiene que decir cuál es cuál.
  const bifurca = !!(ret && ret.months.length && r.total_months > ret.start_month);
  const series = [
    { color: THEME.balance, fill: true, rol: "fondo",
      label: (showCash ? "Valor total (fondo + efectivo)" : "Valor acumulado") +
             (bifurca ? " · sin consumir nada" : ""),
      values: padSeries(r.months.map((m) => m.balance), span) },
    { color: THEME.invested, label: "Aportado por ti", dash: [6, 4],
      values: padSeries(r.months.map((m) => m.invested), span) },
  ];
  if (showCash) {
    series.push({ color: THEME.portfolio, label: "Valor en el fondo",
      values: padSeries(r.months.map((m) => m.portfolio), span) });
    series.push({ color: THEME.cash, label: "Efectivo cobrado",
      values: padSeries(r.months.map((m) => m.cash), span) });
  }
  if (r.afp_series && r.afp_series.length) {
    // Sube mientras cotizas y baja mientras te paga la pensión: se agota justo a la
    // expectativa de vida, que es el supuesto con que la AFP calcula el monto.
    series.push({ color: THEME.afp, label: "Saldo en la AFP", rol: "afp",
      values: padSeries(r.afp_series.map((a) => a.balance), span) });
  }
  if (ret && ret.months.length) {
    // Arranca donde dejas de aportar, así que se ve la bifurcación entre seguir
    // acumulando sin tocar nada y empezar a consumir.
    series.push({ color: THEME.retirement, rol: "consumo",
      label: `Consumiendo tu meta desde los ${ret.start_age}`,
      values: padSeries(ret.months.map((m) => m.balance), span, ret.start_month) });
  }

  const ctx = $("#chart").getContext("2d");
  const gradient = ctx.createLinearGradient(0, 0, 0, 320);
  gradient.addColorStop(0, "rgba(74, 222, 128, 0.28)");
  gradient.addColorStop(1, "rgba(74, 222, 128, 0.01)");

  // Deflactar es dividir por (1+i)^(mes/12): la misma cuenta que usan las tarjetas,
  // aplicada punto a punto para que la curva no arrastre la inflación.
  const infl = (r.inflation || 0) / 100;
  const real = chartUnits === "real" && infl !== 0;
  const aUnidad = (values) => (real
    ? values.map((v, i) => (v === null ? null : v / (1 + infl) ** ((i + 1) / 12)))
    : values);

  const bifurcacion = bifurca
    ? ` Desde los <strong>${ret.start_age}</strong>, cuando dejas de aportar, el fondo se ` +
      `dibuja dos veces: la línea verde es lo que tendrías <strong>si no sacaras nada</strong> ` +
      `y la rosada descuenta mes a mes lo que gastas. Son el mismo dinero bajo supuestos ` +
      `opuestos; la diferencia entre ambas es lo que consumiste más lo que ese dinero ` +
      `habría rentado.`
    : "";

  $("#chart-note").innerHTML = real
    ? `Deflactado a <strong>pesos de hoy</strong>: cada punto dividido por ` +
      `(1 + ${r.inflation}%)^(mes/12), así se ve el poder adquisitivo y no la inflación. ` +
      `Es la misma unidad en que habla el modal del perfil.`
    : `En <strong>pesos nominales</strong> de cada año, como las tarjetas de arriba. ` +
      `El tooltip muestra el equivalente en pesos de hoy, que es la unidad del modal ` +
      `del perfil.`;
  $("#chart-note").innerHTML += bifurcacion;

  const data = {
    labels: Array.from({ length: span }, (_, i) => i + 1),
    datasets: series.map((sr) => ({
      label: sr.label,
      rol: sr.rol || null,
      data: aUnidad(sr.values),
      spanGaps: false,
      borderColor: sr.color,
      backgroundColor: sr.fill ? gradient : sr.color,
      borderWidth: 2,
      borderDash: sr.dash || [],
      fill: sr.fill ? "origin" : false,
      pointRadius: 0,
      pointHoverRadius: 4,
      pointHoverBackgroundColor: sr.color,
      pointHoverBorderColor: "#0f1216",
      pointHoverBorderWidth: 2,
      tension: 0.25,
    })),
  };

  const options = {
    responsive: true,
    maintainAspectRatio: false,
    interaction: { mode: "index", intersect: false },
    plugins: {
      legend: {
        position: "bottom",
        labels: { color: THEME.text, boxWidth: 12, boxHeight: 12, usePointStyle: true,
          pointStyle: "rectRounded", padding: 16, font: { size: 12 } },
      },
      tooltip: {
        backgroundColor: THEME.tooltipBg,
        borderColor: "#333c48",
        borderWidth: 1,
        titleColor: "#e6ebf2",
        bodyColor: "#e6ebf2",
        footerColor: "#4ade80",
        footerFont: { weight: "600" },
        footerMarginTop: 8,
        padding: 10,
        cornerRadius: 8,
        displayColors: true,
        usePointStyle: true,
        callbacks: {
          title: (items) => {
            const m = items[0].parsed.x + 1;
            const años = Math.floor(m / 12);
            const meses = m % 12;
            const edad = lastResult && lastResult.start_age
              ? ` · ${(lastResult.start_age + m / 12).toFixed(1)} años`
              : "";
            return `Mes ${m}` + (años ? ` · año ${años}${meses ? ` y ${meses} m` : ""}` : "") + edad;
          },
          // El gráfico va en pesos nominales, pero el perfil y las tarjetas hablan en
          // pesos de hoy: sin la equivalencia al lado, el mismo saldo parece dos cifras
          // distintas según dónde se mire.
          // El total suma fondo + AFP. Cuando la rama de consumo existe manda ella,
          // porque es el mismo fondo bajo otro supuesto: sumar las dos lo duplicaría.
          footer: (items) => {
            const rol = (n) => items.find((i) => i.dataset.rol === n);
            const fondo = rol("consumo") || rol("fondo");
            const afp = rol("afp");
            if (!fondo && !afp) return "";
            const total = (fondo ? fondo.parsed.y : 0) + (afp ? afp.parsed.y : 0);
            return `Patrimonio total: ${fmtMoney(total)}` +
              (fondo && afp ? ` (fondo + AFP)` : "");
          },
          label: (item) => {
            const m = item.parsed.x + 1;
            const i = (lastResult ? lastResult.inflation : 0) / 100;
            const factor = (1 + i) ** (m / 12);
            const otra = chartUnits === "real" ? item.parsed.y * factor : item.parsed.y / factor;
            const sufijo = chartUnits === "real" ? "nominales" : "de hoy";
            return ` ${item.dataset.label}: ${fmtMoney(item.parsed.y)}` +
              (i ? ` (${fmtMoney(otra)} ${sufijo})` : "");
          },
        },
      },
    },
    scales: {
      x: {
        grid: { color: THEME.grid, drawTicks: false },
        border: { color: THEME.grid },
        ticks: {
          color: THEME.text, maxRotation: 0, autoSkip: false, font: { size: 11 },
          callback: (v, i) => {
            const m = i + 1;
            const stepYears = Math.max(1, Math.ceil(r.total_months / 12 / 10));
            return m % (12 * stepYears) === 0 ? `${m / 12}a` : "";
          },
        },
      },
      y: {
        grid: { color: THEME.grid, drawTicks: false },
        border: { display: false },
        ticks: { color: THEME.text, padding: 8, callback: (v) => shortNum(v) },
      },
    },
  };

  if (chart) {
    chart.data = data;
    chart.options = options;
    chart.update("none");
  } else {
    chart = new Chart(ctx, { type: "line", data, options });
  }
}

function shortNum(v) {
  const abs = Math.abs(v);
  if (abs >= 1e6) return (v / 1e6).toLocaleString("es-CL", { maximumFractionDigits: abs >= 1e8 ? 0 : 1 }) + "M";
  if (abs >= 1e3) return (v / 1e3).toFixed(0) + "K";
  return v.toFixed(0);
}

/** Lectura rápida para montos largos: "$3.966.106.905" no se lee de un vistazo. */
function compactHint(n) {
  const abs = Math.abs(n);
  if (abs < 1e6) return "";
  if (abs >= 1e9) return `≈ ${(n / 1e6).toLocaleString("es-CL", { maximumFractionDigits: 0 })} millones`;
  return `≈ ${(n / 1e6).toLocaleString("es-CL", { maximumFractionDigits: 1 })} millones`;
}

/** Las columnas dependen del modo: nunca se muestran dos que valgan lo mismo.
 *  Con reinversión, "en el fondo" y "valor total" son idénticas, así que sobra una;
 *  sin reinversión, "aportado + reinvertido" es igual a "aportado", y sobra esa. */
function yearlyColumns() {
  const withDiv = lastResult.model === "dividends";
  const reinv = lastResult.reinvest;
  const cols = [
    { th: "Año", cls: "", get: (r) => r.year },
    { th: "Aportado por ti", tip: "Sólo el dinero que saliste a poner de tu bolsillo.",
      get: (r) => fmtMoney(r.invested) },
  ];
  cols.push({ th: "Aportado en pesos de hoy",
    tip: "Cada aporte llevado a pesos de hoy: el esfuerzo real que hiciste.",
    get: (r) => fmtMoney(r.invested_real) });
  if (withDiv && reinv) {
    cols.push({ th: "Aportado + reinvertido",
      tip: "Tus aportes más los dividendos que volvieron al fondo: el capital total trabajando.",
      get: (r) => fmtMoney(r.cost_basis) });
    cols.push({ th: "Aportado + reinvertido en pesos de hoy",
      tip: "Ese mismo capital, con cada flujo deflactado en el momento en que entró.",
      get: (r) => fmtMoney(r.cost_basis_real) });
  }
  if (withDiv) {
    cols.push({ th: "Dividendos del año",
      tip: "Lo que el fondo te repartió durante ese año (la suma de sus pagos).",
      get: (r) => fmtMoney(r.dividends_year) });
    cols.push({ th: "Dividendos acum.", tip: "Todo lo repartido por el fondo hasta ese año.",
      get: (r) => fmtMoney(r.dividends_total) });
    cols.push({ th: "Plusvalía acum.",
      tip: "Cuánto subió el valor de las cuotas por sobre el capital puesto en el fondo.",
      get: (r) => fmtMoney(r.capital_gain) });
  }
  if (withDiv && !reinv) {
    cols.push({ th: "En el fondo", tip: "Valor de mercado de tus cuotas.",
      get: (r) => fmtMoney(r.portfolio) });
    cols.push({ th: "Efectivo cobrado", tip: "Dividendos que retiraste y no rentan.",
      get: (r) => fmtMoney(r.cash) });
  }
  cols.push({ th: "Valor total", tip: "Lo que tendrías en total ese año.",
    get: (r) => fmtMoney(r.balance) });
  cols.push({ th: "Ganancia",
    tip: withDiv
      ? "Dividendos acum. + plusvalía acum. Es lo mismo que valor total − aportado por ti."
      : "Valor total menos lo que aportaste de tu bolsillo.",
    get: (r) => fmtMoney(r.gain) });
  return cols;
}

function monthlyColumns() {
  const withDiv = lastResult.model === "dividends";
  const cols = [
    { th: "Mes", cls: "", get: (r) => r.month },
    { th: "Aporte", html: true,
      tip: "El aporte del tramo más el extraordinario que caiga ese mes.",
      get: (r) => (r.lump
        ? `${fmtMoney(r.contribution)} <span class="tag">extra ${fmtMoney(r.lump)}</span>`
        : fmtMoney(r.contribution)) },
    { th: "Aportado por ti", get: (r) => fmtMoney(r.invested) },
    { th: withDiv ? "Plusvalía del mes" : "Interés del mes", get: (r) => fmtMoney(r.interest) },
  ];
  if (withDiv) {
    cols.push({ th: "Dividendo", get: (r) => (r.dividend ? fmtMoney(r.dividend) : "—") });
    if (lastResult.reinvest) {
      cols.push({ th: "Aportado + reinvertido", get: (r) => fmtMoney(r.cost_basis) });
    }
  }
  cols.push({ th: "Valor total", get: (r) => fmtMoney(r.balance) });
  return cols;
}

let grid = null;

/** ¿Hay pensión de la AFP en juego en el resultado en pantalla? */
function conPension() {
  return !!(lastResult && lastResult.include_pension && lastResult.pension_monthly > 0
            && lastResult.pension_start_year);
}

function purchasingColumns() {
  return [
    { th: "Año", cls: "", get: (r) => r.year },
    { th: "Dividendo mensual", tip: "Lo que recibirías al mes ese año, en pesos de ese año.",
      get: (r) => fmtMoney(r.dividend_monthly) },
    { th: "Meta del mes", tip: "Lo que costará ese año vivir como hoy con tu monto objetivo.",
      get: (r) => fmtMoney(r.goal_monthly) },
    ...(conPension() ? [
      { th: "Pensión AFP",
        tip: "Lo que pagaría tu AFP ese año, en pesos de ese año. Parte desde la edad de " +
             "jubilación; el primer año va prorrateado por los meses que alcanza a pagar.",
        get: (r) => (r.pension_monthly ? fmtMoney(r.pension_monthly) : "—") },
      { th: "Falta cubrir",
        tip: "La meta menos la pensión: lo que tiene que poner la inversión.",
        get: (r) => fmtMoney(r.goal_from_portfolio) },
    ] : []),
    { th: "Cobertura", tip: "Qué porcentaje de lo que falta cubren tus dividendos.", html: true,
      get: (r) => {
        if (r.coverage === null) return "—";
        const pct = Math.min(100, r.coverage);
        return `<span class="bar${r.coverage >= 100 ? "" : " short"}" style="width:${pct * 0.5}px"></span>` +
          `${r.coverage.toFixed(0)}%`;
      } },
    { th: "Retiro sostenible",
      tip: "Lo que podrías sacar al mes ese año sin que el capital pierda poder adquisitivo.",
      get: (r) => fmtMoney(r.sustainable_monthly) },
    { th: "Cobertura sostenible",
      tip: "Qué porcentaje de la meta cubre ese retiro sostenible. Al llegar a 100% eres independiente.",
      html: true,
      get: (r) => {
        if (r.sustainable_coverage === null) return "—";
        const pct = Math.min(100, r.sustainable_coverage);
        return `<span class="bar${r.sustainable_coverage >= 100 ? "" : " short"}" ` +
          `style="width:${pct * 0.5}px"></span>${r.sustainable_coverage.toFixed(0)}%`;
      } },
    { th: "Dividendo en pesos de hoy",
      tip: "El mismo dividendo mensual descontada la inflación: su poder adquisitivo real.",
      get: (r) => fmtMoney(r.dividend_monthly_real) },
    { th: "Valor total en pesos de hoy",
      tip: "Tu patrimonio deflactado, o sea lo que compraría a precios de hoy.",
      get: (r) => fmtMoney(r.real_balance) },
  ];
}

function renderDetail() {
  if (!lastResult) return;
  const byView = {
    yearly: [yearlyColumns, () => lastResult.yearly],
    monthly: [monthlyColumns, () => lastResult.months],
    purchasing: [purchasingColumns, () => lastResult.yearly],
  };
  const [colsFn, rowsFn] = byView[detailView];
  const cols = colsFn();
  const rows = rowsFn();

  const config = {
    columns: cols.map((c, i) => ({
      name: c.th,
      ...(c.html ? { formatter: (cell) => gridjs.html(String(cell)) } : {}),
      // La primera columna (año/mes) es un entero; el resto son montos alineados a la derecha.
      sort: { compare: i === 0 ? undefined : compareMoney },
      attributes: (cell) => (cell === null ? {} : { class: i === 0 ? "gridjs-td" : "gridjs-td num" }),
    })),
    data: rows.map((r) => cols.map((c) => String(c.get(r)))),
    sort: true,
    pagination: false,
    // Todas las filas de una vez, con scroll interno y encabezado fijo:
    // así el largo de la página no crece con el horizonte.
    fixedHeader: true,
    height: "460px",
    className: { table: "detail-table" },
  };

  const host = $("#detail-grid");
  if (grid) {
    grid.updateConfig(config).forceRender();
  } else {
    grid = new gridjs.Grid(config).render(host);
    enableCrossHighlight(host);
  }
  applyHeaderTips(host, cols);
  $(".grid-tip").innerHTML = detailView === "purchasing"
    ? "Cada columna dice en qué pesos está: las de <em>pesos de hoy</em> vienen deflactadas, " +
      "el resto son pesos de cada año. Haz clic en una celda para resaltar su fila y su columna."
    : "Los montos están en <strong>pesos de cada año</strong> (nominales), salvo las columnas " +
      "que digan lo contrario. Haz clic en una celda para resaltar su fila y su columna.";
}

/** Ordena montos formateados ("$1.234.567") por su valor numérico. */
function compareMoney(a, b) {
  const clean = (v) => String(v).replace(/<[^>]*>/g, "");   // descarta el markup de la barra
  const n = (v) => parseFloat(clean(v).replace(/[^\d,.-]/g, "").replace(/\./g, "").replace(",", ".")) || 0;
  return n(a) - n(b);
}

function applyHeaderTips(host, cols) {
  host.querySelectorAll("th.gridjs-th").forEach((th, i) => {
    if (cols[i] && cols[i].tip) th.title = cols[i].tip;
  });
}

/** Clic en una celda: resalta su fila y su columna completas. */
function enableCrossHighlight(host) {
  host.addEventListener("click", (e) => {
    const td = e.target.closest("td.gridjs-td");
    const table = host.querySelector("table");
    if (!table) return;
    if (!td) return;

    const col = td.cellIndex;
    const active = td.classList.contains("cross-cell");
    table.querySelectorAll(".cross-row, .cross-col, .cross-cell")
      .forEach((el) => el.classList.remove("cross-row", "cross-col", "cross-cell"));
    if (active) return;                       // segundo clic en la misma celda: apagar

    td.parentElement.classList.add("cross-row");
    td.classList.add("cross-cell");
    table.querySelectorAll("tr").forEach((tr) => {
      const cell = tr.children[col];
      if (cell && cell !== td) cell.classList.add("cross-col");
    });
  });
}

// --- persistencia ----------------------------------------------------

async function loadSaved() {
  const items = await api("GET", "/api/scenarios");
  const list = $("#saved-list");
  if (!items.length) {
    list.innerHTML = `<li class="empty">Aún no hay escenarios guardados.</li>`;
    return;
  }
  list.innerHTML = "";
  items.forEach((s) => {
    const detail = s.model === "dividends"
      ? `${s.appreciation}% plusvalía + ${s.dividend_yield}% dividendos`
      : `${s.annual_return}% anual`;
    const li = document.createElement("li");
    li.innerHTML = `<div><div>${escapeHtml(s.name)}</div>
      <div class="meta">${detail} · ${s.years} años · ${s.currency}</div></div>`;
    const actions = document.createElement("div");
    const load = document.createElement("button");
    load.textContent = "Cargar";
    load.className = "secondary";
    load.addEventListener("click", () => loadScenario(s.id));
    const del = document.createElement("button");
    del.textContent = "×";
    del.className = "icon";
    del.title = "Eliminar";
    del.addEventListener("click", async () => {
      if (!confirm(`¿Eliminar "${s.name}"?`)) return;
      await api("DELETE", `/api/scenarios/${s.id}`);
      if (currentId === s.id) currentId = null;
      loadSaved();
    });
    actions.append(load, del);
    li.appendChild(actions);
    list.appendChild(li);
  });
}

function escapeHtml(s) {
  return s.replace(/[&<>"]/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;" }[c]));
}

async function loadScenario(id) {
  const s = await api("GET", `/api/scenarios/${id}`);
  currentId = s.id;
  $("#name").value = s.name;
  $("#years").value = s.years;
  $("#currency").value = s.currency;
  $("#annual_return").value = s.annual_return;
  $("#model-dividends").checked = s.model === "dividends";
  $("#appreciation").value = s.appreciation;
  $("#dividend_yield").value = s.dividend_yield;
  $("#payout_months").value = s.payout_months;
  $("#reinvest").checked = s.reinvest;
  $("#inflation").value = s.inflation;
  $("#income_goal").value = formatAmount(s.income_goal);
  $("#index_contributions").checked = s.index_contributions;
  $("#include_pension").checked = s.include_pension !== false;
  $("#work_until_age").value = s.work_until_age ? s.work_until_age : "";
  $("#retire_to_age").value = s.retire_to_age ? s.retire_to_age : "";
  $("#spend_mode").value = s.spend_mode || "goal";
  syncIndexUI();
  syncInflationDetail();
  syncModelUI();
  // Los tramos son tu plan de ahorro, no del instrumento: si ya tienes uno
  // guardado en el perfil, cambiar de escenario no lo pisa.
  const planPropio = profileData && profileData.ranges && profileData.ranges.length;
  if (!planPropio) {
    rangesBody.innerHTML = "";
    s.ranges.forEach((r) => addRange(r.start_month, r.end_month, r.amount));
    if (!s.ranges.length) refreshRangeMeta();
  }
  scheduleCalculate(0);
}

async function save() {
  showError("");
  const body = payload();
  try {
    let saved;
    try {
      saved = await api("POST", currentId ? `/api/scenarios/${currentId}` : "/api/scenarios", body);
    } catch (e) {
      // El escenario pudo haber sido eliminado en otra pestaña: guarda uno nuevo.
      if (e.status !== 404) throw e;
      currentId = null;
      saved = await api("POST", "/api/scenarios", body);
    }
    currentId = saved.id;
    $("#name").value = saved.name;
    await loadSaved();
  } catch (e) {
    showError(e.message);
  }
}

function reset() {
  currentId = null;
  $("#name").value = "";
  rangesBody.innerHTML = "";
  addRange(1, 60, 100);
  showError("");
  scheduleCalculate(0);
}

// --- init ------------------------------------------------------------

$("#add-range").addEventListener("click", () => {
  const start = nextStartMonth();
  addRange(start, start + 59, 100);
  scheduleCalculate();
});
$("#add-lump").addEventListener("click", () => {
  const hoy = new Date();
  addLump(hoy.getFullYear() + 1, hoy.getMonth() + 1, 0);
  scheduleCalculate();
});
$("#save").addEventListener("click", save);
$("#reset").addEventListener("click", reset);

function onFormChange(e) {
  const id = e.target.id;
  if (e.type === "input" && e.target.classList.contains("amount")) {
    reformatAmountInput(e.target);
  }
  if (id === "model-dividends" || id === "reinvest") syncModelUI();
  if (e.target.closest("#ranges") || id === "years") refreshRangeMeta();
  if (e.target.closest("#ranges") || e.target.closest("#lumps")) schedulePlanSave();
  if (id === "currency") {
    // Sólo cambia el formato: se re-dibuja al instante, sin ir al servidor.
    if (lastResult) renderResult(lastResult);
    return;
  }
  if (id === "inflation") syncInflationDetail();
  if (id === "index_contributions") syncIndexUI();
  if (id === "inflation-preset") return;   // lo maneja su propio listener
  if (id === "name") return;          // el nombre no altera la proyección
  scheduleCalculate();
}
$("#inflation-preset").addEventListener("change", () => { applyInflationPreset(); scheduleCalculate(); });
$("#form-panel").addEventListener("input", onFormChange);
$("#form-panel").addEventListener("change", onFormChange);

document.querySelectorAll("#detail-tabs .tab").forEach((t) => {
  t.addEventListener("click", () => {
    document.querySelectorAll("#detail-tabs .tab").forEach((x) => x.classList.remove("active"));
    t.classList.add("active");
    detailView = t.dataset.view;
    renderDetail();
  });
});

// El gráfico se lee en pesos nominales o deflactado a pesos de hoy: es el mismo dato,
// pero la curva nominal incluye la inflación y no se puede comparar de frente con el
// perfil, que siempre habla en pesos de hoy.
document.querySelectorAll("#chart-units .tab").forEach((t) => {
  t.addEventListener("click", () => {
    document.querySelectorAll("#chart-units .tab").forEach((x) => x.classList.remove("active"));
    t.classList.add("active");
    chartUnits = t.dataset.units;
    if (lastResult) drawChart(lastResult);
  });
});

syncModelUI();
syncIndexUI();
addRange(1, 60, 100);
addRange(61, 120, 200);
loadInflationPresets().then(() => scheduleCalculate(0));
loadSaved();

/** Guarda el plan de aporte en el perfil sin que haya que abrir el modal. */
function schedulePlanSave() {
  if (!profileData || !profileData.profile) return;   // sin perfil no hay dónde guardarlo
  clearTimeout(planTimer);
  planTimer = setTimeout(async () => {
    const ranges = readRanges();
    if (!ranges.every((r) => Number.isFinite(r.start_month) && Number.isFinite(r.end_month)
        && Number.isFinite(r.amount))) return;
    if (!readLumps().every((l) => Number.isFinite(l.year) && Number.isFinite(l.month)
        && Number.isFinite(l.amount))) return;
    try {
      profileData = await api("POST", "/api/profile",
                              { ...profileFromForm(), ranges, lumps: readLumps() });
    } catch (e) { /* el error ya se ve en el panel de cálculo */ }
  }, 1500);
}

// --- perfil ----------------------------------------------------------
// Vive en un modal para no cargar la pantalla principal. El plan de aporte se
// guarda aquí y no en cada escenario, así cambiar de instrumento no obliga a
// reescribir los tramos.

let afpParams = null;
let profileData = null;
let previewTimer = null;
let previewSeq = 0;        // descarta respuestas que llegan fuera de orden

async function loadAfpParams() {
  afpParams = await api("GET", "/api/afp/params");
  $("#p-inicio-mes").innerHTML = MESES
    .map((m, i) => `<option value="${i + 1}">${m}</option>`).join("");
  $("#p-afp").innerHTML = Object.keys(afpParams.comisiones)
    .map((a) => `<option value="${a}">${a}</option>`).join("");
  $("#p-fondo").innerHTML = Object.entries(afpParams.rentabilidad_real)
    .map(([f, r]) => `<option value="${f}">Fondo ${f} · ${r}% real anual</option>`).join("");
}

function profileFromForm() {
  return {
    nacimiento: $("#p-nacimiento").value,
    sexo: $("#p-sexo").value,
    inicio_mes: parseInt($("#p-inicio-mes").value, 10),
    inicio_anio: parseInt($("#p-inicio-anio").value, 10),
    sueldo_imponible: parseAmount($("#p-sueldo").value),
    no_imponible: parseAmount($("#p-no-imponible").value) || 0,
    afp: $("#p-afp").value,
    comision_afp: parseFloat($("#p-comision").value),
    fondo: $("#p-fondo").value,
    saldo_afp: parseAmount($("#p-saldo").value),
    salud: $("#p-salud").value,
    salud_extra: parseAmount($("#p-salud-extra").value) || 0,
    contrato_indefinido: $("#p-indefinido").checked,
    aporte_empleador: parseFloat($("#p-empleador").value),
    trayectoria: $("#p-trayectoria").value,
    destino_salida_a: $("#p-salida-a").value,
    uf: parseAmount($("#p-uf").value),
    utm: parseAmount($("#p-utm").value),
    ranges: readRanges(),      // el plan de aporte que está en pantalla
  };
}

function fillProfileForm(p) {
  const hoy = new Date();
  const d = p || {
    nacimiento: "1990-01-01", sexo: "hombre", inicio_mes: hoy.getMonth() + 1, inicio_anio: hoy.getFullYear(),
    sueldo_imponible: 0, no_imponible: 0,
    afp: "Habitat", comision_afp: 1.27, fondo: "B", saldo_afp: 0,
    salud: "fonasa", salud_extra: 0, contrato_indefinido: true,
    aporte_empleador: afpParams ? afpParams.aporte_empleador_cuenta : 0.1,
    uf: afpParams ? afpParams.uf_referencia : 40884.32,
    utm: afpParams ? afpParams.utm_referencia : 71721,
    trayectoria: "fijo", destino_salida_a: "B",
  };
  $("#p-nacimiento").value = d.nacimiento || "1990-01-01";
  $("#p-sexo").value = d.sexo;
  $("#p-inicio-mes").value = d.inicio_mes;
  $("#p-inicio-anio").value = d.inicio_anio;
  $("#p-sueldo").value = formatAmount(d.sueldo_imponible);
  $("#p-no-imponible").value = formatAmount(d.no_imponible);
  $("#p-afp").value = d.afp;
  $("#p-comision").value = d.comision_afp;
  $("#p-fondo").value = d.fondo;
  $("#p-saldo").value = formatAmount(d.saldo_afp);
  $("#p-salud").value = d.salud;
  $("#p-salud-extra").value = formatAmount(d.salud_extra);
  $("#p-indefinido").checked = d.contrato_indefinido;
  $("#p-empleador").value = d.aporte_empleador;
  $("#p-trayectoria").value = d.trayectoria || "fijo";
  $("#p-salida-a").value = d.destino_salida_a || "B";
  $("#p-uf").value = formatAmount(d.uf);
  $("#p-utm").value = formatAmount(d.utm || (afpParams ? afpParams.utm_referencia : 71721));
  syncProfileUI();
}

function edadDesde(iso) {
  if (!iso) return NaN;
  const [y, m, d] = iso.split("-").map(Number);
  const hoy = new Date();
  const nace = new Date(y, m - 1, d);
  let años = hoy.getFullYear() - y - (hoy < new Date(hoy.getFullYear(), m - 1, d) ? 1 : 0);
  const ultimo = new Date(hoy.getFullYear() - (hoy < new Date(hoy.getFullYear(), m - 1, d) ? 1 : 0), m - 1, d);
  const siguiente = new Date(ultimo.getFullYear() + 1, m - 1, d);
  return Number.isNaN(nace.getTime()) ? NaN
    : Math.round((años + (hoy - ultimo) / (siguiente - ultimo)) * 100) / 100;
}

function syncProfileUI() {
  $("#p-salud-extra-wrap").hidden = $("#p-salud").value !== "isapre";
  if (!afpParams) return;
  const edad = edadDesde($("#p-nacimiento").value);
  const pensionAños = afpParams.edad_pension[$("#p-sexo").value];
  $("#p-edad-calc").innerHTML = Number.isFinite(edad)
    ? `Tienes <strong>${Math.floor(edad)}</strong> años: te quedan ` +
      `<strong>${(pensionAños - edad).toFixed(1)}</strong> años de cotización hasta los ${pensionAños}.`
    : "Ingresa tu fecha de nacimiento para calcular la edad.";
  const sexo = $("#p-sexo").value;
  const t = afpParams.tramos[sexo];
  const pension = afpParams.edad_pension[sexo];
  if (!Number.isFinite(edad)) return;
  const porDefecto = edad <= t.b_hasta ? "B" : edad <= t.c_hasta ? "C" : "D";
  const modo = $("#p-trayectoria").value;
  const fondo = $("#p-fondo").value;
  $("#p-salida-a-wrap").hidden = !(modo === "fijo" && fondo === "A");

  const gradual = "El traspaso no es de golpe: se mueve <strong>20% del saldo al cumplir la " +
    "edad y 20% más cada año</strong>, completándose a los cuatro años. Las cotizaciones " +
    "nuevas van de inmediato al fondo que corresponde.";

  const porTramo =
    `Si nunca hubieras elegido fondo, la ley te asignaría por defecto: <strong>B hasta los ` +
    `35</strong>, <strong>C desde los 36 hasta los ${t.c_hasta}</strong> y ` +
    `<strong>D desde los ${t.traspaso_desde}</strong>.`;

  const salidaA = `La salida corre dentro de 90 días desde el cumpleaños y no es a un fondo ` +
    `determinado: puedes moverte a B, C, D o E, y por eso el destino se elige aquí.`;

  // Cuando la nota de arriba ya explicó la salida del A no se repite la edad.
  const sobreAyB = (fondo === "A" && modo === "fijo"
    ? `<br>${salidaA} `
    : `<br><strong>Fondo A</strong>: la ley te obliga a sacar de ahí el saldo por ` +
      `cotizaciones obligatorias al cumplir <strong>${t.traspaso_desde}</strong> años. ` +
      `${salidaA} `) +
    `<strong>Fondo B</strong>, en cambio, no tiene ninguna restricción de edad: puedes ` +
    `permanecer en él hasta jubilar.`;

  // "Fijo" no es fijo del todo: del fondo A la ley te expulsa, y ése es el único
  // fondo con tope de edad. La nota lo dice según el fondo elegido para no
  // prometer "hasta jubilar" a quien está en A.
  const fijoTexto = fondo === "A"
    ? `Te mantienes en el <strong>fondo A</strong> hasta los ` +
      `<strong>${t.traspaso_desde}</strong>, cuando la ley te obliga a salir: de ahí en ` +
      `adelante la proyección te deja en el <strong>fondo ${$("#p-salida-a").value}</strong>. ` +
      `${porTramo}`
    : `Te mantienes en el <strong>fondo ${fondo}</strong> hasta jubilar: fuera del A ningún ` +
      `fondo tiene restricción de edad, así que la ley nunca te obliga a moverte. ${porTramo}`;

  const modos = {
    fijo: fijoTexto,
    basico: `Esquema de traspasos por edad que se <em>contrata</em> con la AFP (no es ` +
      `automático). Contrato básico: hitos a los <strong>36</strong> y los ` +
      `<strong>${t.traspaso_desde}</strong> años, terminando en el <strong>fondo D</strong>. ` +
      gradual,
    ampliado: `Contrato ampliado: hitos a los <strong>31, 36, ${t.traspaso_desde} y ` +
      `${sexo === "hombre" ? 61 : 56}</strong> años, terminando en el <strong>fondo E</strong>. ` +
      gradual,
  };
  const [gAño, gMes] = (afpParams.generacionales_desde || "2027-04").split("-");
  $("#p-fondo-nota").innerHTML = modos[modo] + sobreAyB +
    `<br>Ojo: en <strong>${MESES[Number(gMes) - 1]} de ${gAño}</strong> los multifondos ` +
    `se reemplazan por fondos ` +
    `generacionales asignados por año de nacimiento, sin opción de elegir en el ahorro ` +
    `obligatorio; la proyección usa la trayectoria de los multifondos porque los nuevos ` +
    `todavía no tienen rentabilidad observada.`;
}

async function loadProfile() {
  const data = await api("GET", "/api/profile");
  profileData = data;
  fillProfileForm(data.profile);
  if (data.ranges && data.ranges.length) {
    rangesBody.innerHTML = "";
    data.ranges.forEach((r) => addRange(r.start_month, r.end_month, r.amount));
  }
  lumpsBody.innerHTML = "";
  (data.lumps || []).forEach((l) => addLump(l.year, l.month, l.amount, l.label));
  // El plan de aporte llega después del primer cálculo, así que hay que rehacerlo.
  if ((data.ranges && data.ranges.length) || (data.lumps && data.lumps.length)) {
    scheduleCalculate(0);
  }
  renderAfp(data.afp);
  return data;
}

async function saveProfile() {
  $("#profile-error").hidden = true;
  try {
    const data = await api("POST", "/api/profile", profileFromForm());
    profileData = data;
    setLiquido(data.afp);
    renderAfp(data.afp);
    $("#profile-status").textContent = "Perfil guardado ✓";
    setTimeout(() => ($("#profile-status").textContent = ""), 2500);
  } catch (e) {
    const el = $("#profile-error");
    el.textContent = e.message;
    el.hidden = false;
  }
}

/** El modal recalcula solo mientras escribes, igual que el panel principal: el líquido
 *  y la proyección los devuelve el backend (las fórmulas legales viven en afp.py, no se
 *  duplican aquí) y las respuestas que llegan fuera de orden se descartan. Es una vista
 *  previa: no guarda nada, para eso sigue estando el botón. */
function scheduleProfilePreview(delay = 220) {
  clearTimeout(previewTimer);
  previewTimer = setTimeout(previewProfile, delay);
}

async function previewProfile() {
  const body = profileFromForm();
  if (!body.nacimiento || !Number.isFinite(body.sueldo_imponible) || body.sueldo_imponible <= 0) {
    return setLiquido(null, "Ingresa tu sueldo imponible y verás aquí el bruto y el líquido.");
  }
  const seq = ++previewSeq;
  try {
    const data = await api("POST", "/api/afp/preview", body);
    if (seq !== previewSeq) return;     // ya hay una vista previa más nueva en curso
    $("#profile-error").hidden = true;
    setLiquido(data.afp);
    renderAfp(data.afp);
  } catch (e) {
    if (seq !== previewSeq) return;
    setLiquido(null, e.message);
  }
}

/** Bruto percibido = imponible + asignaciones no imponibles. El líquido descuenta
 *  del bruto lo previsional y la salud, que sólo se calculan sobre el imponible. */
function setLiquido(a, aviso) {
  const el = $("#p-liquido");
  if (!a) { el.textContent = aviso || ""; return; }
  const d = a.descuentos;
  el.innerHTML =
    `Bruto percibido: <strong>${fmtMoney(a.bruto_total)}</strong> = imponible ` +
    `${fmtMoney(a.bruto_total - a.no_imponible)} + no imponible ${fmtMoney(a.no_imponible)}.` +
    `<br>Líquido aproximado: <strong class="ok">${fmtMoney(a.liquido_aprox)}</strong> ` +
    `— descuentos ${fmtMoney(d.total)}: AFP ${fmtMoney(d.cotizacion)} · comisión ` +
    `${fmtMoney(d.comision)} · salud ${fmtMoney(d.salud)}` +
    (d.cesantia ? ` · cesantía ${fmtMoney(d.cesantia)}` : "") +
    (d.impuesto ? ` · impuesto único ${fmtMoney(d.impuesto)}` : " · sin impuesto único") +
    `.<br>El impuesto de segunda categoría sale de la tabla del SII en UTM sobre una base ` +
    `de ${fmtMoney(a.base_tributable)} (imponible menos cotizaciones obligatorias); las ` +
    `asignaciones no imponibles razonables no son renta afecta.` +
    (a.topado ? `<br>Tu imponible pasa el tope de ${fmtMoney(a.tope_imponible)}: las ` +
      `cotizaciones y la salud se calculan sólo hasta ahí.` : "");
}

function renderAfp(a) {
  const banner = $("#afp-banner");
  const box = $("#afp-result");
  if (!a || !a.meses_hasta_pension) {
    banner.hidden = true;
    box.hidden = true;
    return;
  }
  box.hidden = false;

  const kpis = [
    { k: "Saldo hoy", v: fmtMoney(a.saldo_actual) },
    { k: `Saldo al jubilar (${a.edad_pension})`, v: fmtMoney(a.saldo_al_jubilar), cls: "good",
      sub: "en pesos de hoy" },
    { k: "Cotizado hasta entonces", v: fmtMoney(a.total_cotizado) },
    { k: "Rentabilidad ganada", v: fmtMoney(a.rentabilidad_ganada), cls: "good" },
    { k: "Pensión estimada", v: fmtMoney(a.pension_mensual), cls: "good",
      sub: `saldo / (12 × CNU ${a.cnu}) · ${a.expectativa_vida} años de expectativa · ` +
           `tasa técnica ${a.tasa_tecnica}%` },
    { k: "Descuentos del sueldo", v: fmtMoney(a.descuentos.total),
      sub: `AFP ${fmtMoney(a.descuentos.cotizacion)} · salud ${fmtMoney(a.descuentos.salud)} · ` +
           `impuesto ${fmtMoney(a.descuentos.impuesto)}` },
    { k: "Líquido aproximado", v: fmtMoney(a.liquido_aprox),
      sub: `de ${fmtMoney(a.bruto_total)} brutos` },
  ];
  $("#afp-kpis").innerHTML = kpis.map((c) =>
    `<div class="kpi"><div class="k">${c.k}</div><div class="v ${c.cls || ""}">${c.v}</div>` +
    (c.sub ? `<div class="sub">${c.sub}</div>` : "") + "</div>").join("");

  $("#afp-trayectoria tbody").innerHTML = a.detalle.map((f) =>
    `<tr><td>${f.edad}</td><td>Fondo ${f.fondo}</td>` +
    `<td class="num">${f.tasa_real}%</td><td class="num">${fmtMoney(f.saldo)}</td></tr>`).join("");

  renderAfpBanner(a);
}

/** El banner refleja los supuestos del escenario en pantalla (hasta qué edad trabajas),
 *  no sólo los del perfil, que asume cotizar hasta jubilar. */
function renderAfpBanner(a) {
  const banner = $("#afp-banner");
  if (!a || !a.saldo_al_jubilar) { banner.hidden = true; return; }
  banner.hidden = false;
  const paraDe = a.trabajo_hasta && a.trabajo_hasta < a.edad_pension
    ? ` Dejas de cotizar a los <strong>${a.trabajo_hasta}</strong>, así que el saldo ` +
      `sigue rentando hasta jubilar pero sin plata nueva.`
    : "";
  banner.innerHTML =
    `<strong>Tu AFP</strong>: partiendo de ${fmtMoney(a.saldo_actual)} y cotizando ` +
    `${fmtMoney(a.descuentos.cotizacion)} al mes, llegarías a los ${a.edad_pension} con ` +
    `<strong class="ok">${fmtMoney(a.saldo_al_jubilar)}</strong> en pesos de hoy ` +
    `(fondo ${a.fondo_inicial} → ${a.fondo_final})` +
    (a.topado ? `. Tu sueldo supera el tope imponible de ${fmtMoney(a.tope_imponible)}, ` +
      `así que cotizas sólo hasta ahí.` : ".") + paraDe +
    ` Ese saldo financia una pensión de <strong class="ok">${fmtMoney(a.pension_mensual)}</strong> ` +
    `al mes en pesos de hoy, que la proyección descuenta de tu meta desde esa edad.`;
}

function openProfile() {
  $("#profile-modal").hidden = false;
  document.body.style.overflow = "hidden";
  fillProfileForm(profileData && profileData.profile);
  scheduleProfilePreview(0);
  $("#p-nacimiento").focus();
}

function closeProfile() {
  $("#profile-modal").hidden = true;
  document.body.style.overflow = "";
  // La vista previa no guarda: al salir sin guardar, el banner vuelve a lo persistido.
  clearTimeout(previewTimer);
  previewSeq++;
  renderAfp(profileData && profileData.afp);
}

$("#open-profile").addEventListener("click", openProfile);
$("#close-profile").addEventListener("click", closeProfile);
$("#cancel-profile").addEventListener("click", closeProfile);
$("#save-profile").addEventListener("click", saveProfile);
$("#profile-modal").addEventListener("click", (e) => {
  if (e.target === $("#profile-modal")) closeProfile();
});
document.addEventListener("keydown", (e) => {
  if (e.key === "Escape" && !$("#profile-modal").hidden) closeProfile();
});
// Campos cuyo valor cambia los textos explicativos del modal.
const CAMPOS_SYNC = ["p-nacimiento", "p-sexo", "p-salud", "p-trayectoria", "p-fondo",
                     "p-salida-a"];

$("#profile-modal").addEventListener("input", (e) => {
  if (e.target.classList.contains("amount")) reformatAmountInput(e.target);
  if (CAMPOS_SYNC.includes(e.target.id)) syncProfileUI();
  scheduleProfilePreview();
});
$("#profile-modal").addEventListener("change", (e) => {
  if (CAMPOS_SYNC.includes(e.target.id)) syncProfileUI();
  if (e.target.id === "p-afp" && afpParams) {
    $("#p-comision").value = afpParams.comisiones[$("#p-afp").value];
  }
  scheduleProfilePreview();
});

loadAfpParams().then(loadProfile).catch(() => {});
