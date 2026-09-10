/** Formato de montos en convención chilena y nombres de mes. */
import { $ } from "./dom.js";

export const MESES = ["enero", "febrero", "marzo", "abril", "mayo", "junio", "julio", "agosto",
  "septiembre", "octubre", "noviembre", "diciembre"];

const CURRENCY_SYMBOL = { CLP: "$", USD: "US$", EUR: "€", UF: "UF " };

export function fmtMoney(n) {
  const cur = $("#currency").value;
  const decimals = cur === "CLP" ? 0 : 2;
  return (CURRENCY_SYMBOL[cur] || "") + n.toLocaleString("es-CL", {
    minimumFractionDigits: decimals,
    maximumFractionDigits: decimals,
  });
}

/** Los montos se editan como texto con separador de miles: con un input number
 *  crudo es muy fácil escribir 100000 creyendo que son 1.000.000. */
export function parseAmount(raw) {
  const clean = String(raw).replace(/\./g, "").replace(",", ".").replace(/[^\d.-]/g, "");
  return clean === "" ? NaN : parseFloat(clean);
}

export function formatAmount(n) {
  return Number.isFinite(n) ? n.toLocaleString("es-CL", { maximumFractionDigits: 2 }) : "";
}

/** Reformatea mientras se escribe, manteniendo el cursor donde estaba. */
export function reformatAmountInput(input) {
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

export function shortNum(v) {
  const abs = Math.abs(v);
  if (abs >= 1e6) return (v / 1e6).toLocaleString("es-CL", { maximumFractionDigits: abs >= 1e8 ? 0 : 1 }) + "M";
  if (abs >= 1e3) return (v / 1e3).toFixed(0) + "K";
  return v.toFixed(0);
}

/** Lectura rápida para montos largos: "$3.966.106.905" no se lee de un vistazo. */
export function compactHint(n) {
  const abs = Math.abs(n);
  if (abs < 1e6) return "";
  if (abs >= 1e9) return `≈ ${(n / 1e6).toLocaleString("es-CL", { maximumFractionDigits: 0 })} millones`;
  return `≈ ${(n / 1e6).toLocaleString("es-CL", { maximumFractionDigits: 1 })} millones`;
}
