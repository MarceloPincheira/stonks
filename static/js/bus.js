/** Bus de eventos mínimo.
 *
 *  Existe para cortar ciclos: el plan de aporte necesita disparar un recálculo y un
 *  guardado del perfil, pero el cálculo lee el plan y el perfil escribe en él. Con
 *  imports directos los tres se referencian en círculo; con el bus cada uno sólo
 *  conoce el nombre del evento. */

const oyentes = new Map();

export function on(evento, fn) {
  if (!oyentes.has(evento)) oyentes.set(evento, []);
  oyentes.get(evento).push(fn);
}

export function emit(evento, ...args) {
  (oyentes.get(evento) || []).forEach((fn) => fn(...args));
}
