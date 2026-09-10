/** Lectura del formulario principal: qué se le manda al motor y si está completo. */
import { $ } from "./dom.js";
import { parseAmount } from "./formato.js";
import { readRanges, readLumps } from "./plan.js";

export const dividendsOn = () => $("#model-dividends").checked;

export function syncIndexUI() {
  const on = $("#index_contributions").checked;
  $("#th-amount").innerHTML = on
    ? 'Aporte mensual <span class="tag">pesos de hoy</span>'
    : "Aporte mensual";
  $("#index-hint").textContent = on
    ? "El monto sube con la inflación cada año, como un reajuste de sueldo."
    : "Aportas siempre el mismo monto nominal, que pierde poder adquisitivo con los años.";
}

export function syncModelUI() {
  const on = dividendsOn();
  $("#fields-simple").hidden = on;
  $("#fields-dividends").hidden = !on;
  $("#reinvest-row").hidden = !on;
  $("#dividend-tax-hint").hidden = !on;
  // Los repartos son renta afecta: el art. 107 de la LIR exime el mayor valor de la
  // venta, pero no las distribuciones. Reinvertir el bruto sobrestima el resultado.
  const t = parseFloat($("#dividend_tax").value) || 0;
  $("#dividend-tax-hint").innerHTML = t > 0
    ? `Cada reparto se descuenta un <strong>${t}%</strong> antes de reinvertirse o cobrarse.`
    : "<strong>En 0% la proyección reinvierte el reparto bruto</strong>, o sea libre de " +
      "impuesto. Los repartos son renta afecta al global complementario (el art. 107 de " +
      "la LIR exime la ganancia de capital de la venta, no las distribuciones): pon aquí " +
      "tu tasa efectiva para no sobrestimar el resultado.";
  $("#reinvest-hint").textContent = $("#reinvest").checked
    ? "Los dividendos vuelven al fondo y componen."
    : "Los dividendos se acumulan en efectivo, sin rentar.";
}

export function payload() {
  return {
    name: $("#name").value,
    years: parseInt($("#years").value, 10),
    currency: $("#currency").value,
    model: dividendsOn() ? "dividends" : "simple",
    annual_return: parseFloat($("#annual_return").value),
    appreciation: parseFloat($("#appreciation").value),
    dividend_yield: parseFloat($("#dividend_yield").value),
    dividend_tax: parseFloat($("#dividend_tax").value) || 0,
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

export function showError(msg) {
  const el = $("#error");
  if (!msg) { el.hidden = true; return; }
  el.textContent = msg;
  el.hidden = false;
}

export function setStatus(text, cls = "") {
  const el = $("#status");
  el.textContent = text;
  el.className = "status " + cls;
}

/** Mientras se edita un campo quedan valores a medio escribir; no vale la pena
 *  golpear el backend con ellos ni mostrar errores que se corrigen solos. */
export function isComplete(p) {
  if (!Number.isFinite(p.years)) return false;
  if (p.model === "simple" && !Number.isFinite(p.annual_return)) return false;
  if (!Number.isFinite(p.inflation) || !Number.isFinite(p.income_goal)) return false;
  if (p.model === "dividends") {
    if (!Number.isFinite(p.appreciation) || !Number.isFinite(p.dividend_yield)) return false;
    if (!Number.isFinite(p.dividend_tax)) return false;
    if (!p.payout_months.length || p.payout_months.some((m) => !Number.isFinite(m))) return false;
  }
  if (!p.lump_sums.every((l) =>
      Number.isFinite(l.year) && Number.isFinite(l.month) && Number.isFinite(l.amount))) {
    return false;
  }
  return p.ranges.every((r) =>
    Number.isFinite(r.start_month) && Number.isFinite(r.end_month) && Number.isFinite(r.amount));
}
