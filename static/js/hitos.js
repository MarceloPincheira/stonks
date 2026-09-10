/** Tabla de hitos: dónde está toda la plata en cada momento que importa. */
import { $ } from "./dom.js";
import { fmtMoney } from "./formato.js";

/** Saldo del fondo en un mes cualquiera, sea de la acumulación o de la fase de retiro. */
export function fondoEn(r, mes) {
  const ret = r.retirement;
  if (ret && mes > ret.start_month) {
    const fila = ret.months.find((m) => m.month === mes);
    if (fila) return fila.balance;
  }
  const fila = r.months[mes - 1];
  return fila ? fila.balance : 0;
}

/** Saldo AFP en un mes, o null si ese mes es anterior al inicio de la serie: cuando la
 *  inversión arranca antes de hoy no hay saldo que mostrar, y un 0 se leería como
 *  "no tienes nada" en vez de "no hay dato". */
export function afpEn(r, mes) {
  const fila = (r.afp_series || [])[mes - 1];
  return fila && fila.balance !== null && fila.balance !== undefined ? fila.balance : null;
}

/** Tabla de hitos: dónde está toda la plata en cada momento que importa. Va en pesos
 *  de hoy, que es la única unidad en que las cifras de años distintos son comparables. */
export function renderMilestones(r) {
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
    const afpBruto = afpEn(r, h.mes);
    const afp = afpBruto === null ? null : real(afpBruto, h.mes);
    return `<tr${h.mes === finTrabajo ? ' class="hito-clave"' : ""}>` +
      `<td>${h.hito}</td><td>${edadEn(h.mes)}</td>` +
      `<td class="num">${fmtMoney(fondo)}</td>` +
      `<td class="num">${afp === null ? "—" : fmtMoney(afp)}</td>` +
      `<td class="num"><strong>${fmtMoney(fondo + (afp || 0))}</strong></td>` +
      `<td>${h.nota}</td></tr>`;
  }).join("");
}
