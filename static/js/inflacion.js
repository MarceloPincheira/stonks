/** Ventanas históricas del IPC chileno para el selector de inflación. */
import { $ } from "./dom.js";
import { api } from "./api.js";

let inflationPresets = [];

/** Ventanas históricas del IPC chileno. Una ventana corta puede caer entera en un
 *  régimen benigno o en uno de crisis, así que el selector muestra cuántos años de
 *  crisis cubre cada una. */
export async function loadInflationPresets() {
  const data = await api("GET", "/api/inflation");
  inflationPresets = data.presets;
  const sel = $("#inflation-preset");
  sel.innerHTML = inflationPresets
    .map((p) => `<option value="${p.key}"${p.recommended ? " selected" : ""}>` +
      `${p.label}${p.recommended ? " ✓" : ""}</option>`).join("") +
    `<option value="custom">Personalizado</option>`;
  syncInflationDetail();
}

export function syncInflationDetail() {
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

export function applyInflationPreset() {
  const preset = inflationPresets.find((p) => p.key === $("#inflation-preset").value);
  if (preset) $("#inflation").value = preset.value;
  syncInflationDetail();
}
