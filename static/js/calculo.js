/** Dispara el cálculo contra el backend y entrega el resultado a la pantalla.
 *
 *  Con debounce y descarte de respuestas fuera de orden: mientras se escribe llegan
 *  varias en vuelo y sólo importa la última. */
import { api } from "./api.js";
import { estado } from "./estado.js";
import { payload, isComplete, setStatus, showError } from "./formulario.js";
import { renderResult } from "./render.js";

let calcSeq = 0;
let calcTimer = null;

export function scheduleCalculate(delay = 220) {
  clearTimeout(calcTimer);
  calcTimer = setTimeout(calculate, delay);
}

export async function calculate() {
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
    estado.lastResult = data.result;
    estado.lastSensitivity = data.sensitivity || null;
    renderResult(data.result);
    setStatus("actualizado", "ok");
  } catch (e) {
    if (seq !== calcSeq) return;
    showError(e.message);
    setStatus("sin actualizar", "bad");
  }
}
