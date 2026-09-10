/** El plan de aporte: tramos mensuales y aportes extraordinarios.
 *
 *  Vive en el perfil y no en cada escenario, así cambiar de instrumento no obliga a
 *  reescribirlo. Avisa por el bus en vez de llamar al cálculo o al perfil, que lo leen. */
import { $ } from "./dom.js";
import { MESES, fmtMoney, parseAmount, formatAmount } from "./formato.js";
import { emit } from "./bus.js";

export const rangesBody = $("#ranges-body");
export const lumpsBody = $("#lumps-body");

export function addRange(start, end, amount) {
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
    emit("recalcular");
  });
  rangesBody.appendChild(tr);
  refreshRangeMeta();
}

/** Aportes extraordinarios: un mes de calendario y un monto en pesos de hoy. Van en el
 *  perfil junto al plan de aporte, así que valen para todos los escenarios. */
export function addLump(year, month, amount, label = "") {
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
    emit("recalcular");
    emit("plan-cambiado");
  });
  lumpsBody.appendChild(tr);
}

export function readLumps() {
  return [...lumpsBody.querySelectorAll("tr")].map((tr) => ({
    year: parseInt(tr.querySelector(".lump-year").value, 10),
    month: parseInt(tr.querySelector(".lump-month").value, 10),
    amount: parseAmount(tr.querySelector(".lump-amount").value),
    label: tr.dataset.label || "",
  }));
}

/** Escribe en cada fila el valor nominal que calculó el backend para ese mes. */
export function refreshLumpMeta(r) {
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

export function nextStartMonth() {
  const ends = readRanges().map((r) => r.end_month).filter((n) => Number.isFinite(n));
  return ends.length ? Math.max(...ends) + 1 : 1;
}

export function readRanges() {
  return [...rangesBody.querySelectorAll("tr")].map((tr) => ({
    start_month: parseInt(tr.querySelector(".start").value, 10),
    end_month: parseInt(tr.querySelector(".end").value, 10),
    amount: parseAmount(tr.querySelector(".amount").value),
  }));
}

export function refreshRangeMeta() {
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
      emit("recalcular", 0);
    });
    warn.appendChild(fix);
    el.appendChild(warn);
  }
}
