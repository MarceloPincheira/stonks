/** Estado compartido entre módulos.
 *
 *  Va en un objeto y no en variables sueltas porque los módulos ES importan enlaces de
 *  sólo lectura: reasignar un `let` importado no se vería del otro lado. Mutar campos de
 *  un objeto exportado sí. */

export const estado = {
  lastResult: null,       // último cálculo, para las tablas y el gráfico
  lastSensitivity: null,  // rangos del último cálculo (±1 pp de retorno e inflación)
  detailView: "yearly",   // yearly | monthly | purchasing
  chartUnits: "nominal",  // nominal | real (deflactado a pesos de hoy)
  currentId: null,        // id del escenario cargado (null = nuevo)
  profileData: null,      // perfil, plan de aporte y aportes extraordinarios
  afpParams: null,        // constantes legales previsionales
};
