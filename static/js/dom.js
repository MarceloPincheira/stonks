/** Acceso al DOM y escape de texto. Sin dependencias: es la hoja del árbol. */

export const $ = (sel) => document.querySelector(sel);

/** Texto del usuario que entra al DOM vía innerHTML: nombres de escenario, etiquetas. */
export function escapeHtml(s) {
  return s.replace(/[&<>"]/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;" }[c]));
}
