/** Punto de entrada: conecta los módulos con el DOM y arranca la app.
 *
 *  Todo el cableado de eventos vive aquí a propósito. Los módulos exponen funciones y no
 *  se enganchan solos al DOM, así que se pueden leer —y probar— sin arrastrar la página
 *  entera, y el orden de arranque se ve de un vistazo en un solo lugar. */
import { $ } from "./dom.js";
import { reformatAmountInput } from "./formato.js";
import { estado } from "./estado.js";
import { on } from "./bus.js";
import { addRange, addLump, nextStartMonth, refreshRangeMeta } from "./plan.js";
import { syncIndexUI, syncModelUI } from "./formulario.js";
import { loadInflationPresets, syncInflationDetail, applyInflationPreset } from "./inflacion.js";
import { scheduleCalculate } from "./calculo.js";
import { renderResult } from "./render.js";
import { renderDetail } from "./tablas.js";
import { drawChart } from "./grafico.js";
import { loadSaved, save, reset } from "./escenarios.js";
import { schedulePlanSave, loadAfpParams, loadProfile, saveProfile, openProfile,
         closeProfile, syncProfileUI, scheduleProfilePreview } from "./perfil.js";

// --- el bus une lo que no debe conocerse directamente ---
on("recalcular", (delay = 220) => scheduleCalculate(delay));
on("plan-cambiado", schedulePlanSave);

// --- pantalla principal ---
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
    if (estado.lastResult) renderResult(estado.lastResult);
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
    estado.detailView = t.dataset.view;
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
    estado.chartUnits = t.dataset.units;
    if (estado.lastResult) drawChart(estado.lastResult);
  });
});

// --- perfil ---
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
  if (e.target.id === "p-afp" && estado.afpParams) {
    $("#p-comision").value = estado.afpParams.comisiones[$("#p-afp").value];
  }
  scheduleProfilePreview();
});

// --- arranque ---
syncModelUI();
syncIndexUI();
addRange(1, 60, 100);
addRange(61, 120, 200);
loadInflationPresets().then(() => scheduleCalculate(0));
loadSaved();
loadAfpParams().then(loadProfile).catch(() => {});
