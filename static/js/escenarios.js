/** Escenarios guardados: listar, cargar, guardar y empezar de nuevo. */
import { $, escapeHtml } from "./dom.js";
import { formatAmount } from "./formato.js";
import { api } from "./api.js";
import { estado } from "./estado.js";
import { emit } from "./bus.js";
import { rangesBody, addRange, refreshRangeMeta } from "./plan.js";
import { payload, showError, syncIndexUI, syncModelUI } from "./formulario.js";
import { syncInflationDetail } from "./inflacion.js";

export async function loadSaved() {
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
      if (estado.currentId === s.id) estado.currentId = null;
      loadSaved();
    });
    actions.append(load, del);
    li.appendChild(actions);
    list.appendChild(li);
  });
}


export async function loadScenario(id) {
  const s = await api("GET", `/api/scenarios/${id}`);
  estado.currentId = s.id;
  $("#name").value = s.name;
  $("#years").value = s.years;
  $("#currency").value = s.currency;
  $("#annual_return").value = s.annual_return;
  $("#model-dividends").checked = s.model === "dividends";
  $("#appreciation").value = s.appreciation;
  $("#dividend_yield").value = s.dividend_yield;
  $("#dividend_tax").value = s.dividend_tax || 0;
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
  const planPropio = estado.profileData && estado.profileData.ranges && estado.profileData.ranges.length;
  if (!planPropio) {
    rangesBody.innerHTML = "";
    s.ranges.forEach((r) => addRange(r.start_month, r.end_month, r.amount));
    if (!s.ranges.length) refreshRangeMeta();
  }
  emit("recalcular", 0);
}

export async function save() {
  showError("");
  const body = payload();
  try {
    let saved;
    try {
      saved = await api("POST", estado.currentId ? `/api/scenarios/${estado.currentId}` : "/api/scenarios", body);
    } catch (e) {
      // El escenario pudo haber sido eliminado en otra pestaña: guarda uno nuevo.
      if (e.status !== 404) throw e;
      estado.currentId = null;
      saved = await api("POST", "/api/scenarios", body);
    }
    estado.currentId = saved.id;
    $("#name").value = saved.name;
    await loadSaved();
  } catch (e) {
    showError(e.message);
  }
}

export function reset() {
  estado.currentId = null;
  $("#name").value = "";
  rangesBody.innerHTML = "";
  addRange(1, 60, 100);
  showError("");
  emit("recalcular", 0);
}
