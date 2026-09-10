/** El perfil: sueldo, AFP y proyección previsional, en un modal para no cargar la
 *  pantalla principal. Guarda también el plan de aporte, que es del ahorrante y no del
 *  instrumento. */
import { $ } from "./dom.js";
import { MESES, fmtMoney, parseAmount, formatAmount } from "./formato.js";
import { api } from "./api.js";
import { estado } from "./estado.js";
import { emit } from "./bus.js";
import { rangesBody, lumpsBody, addRange, addLump, readRanges, readLumps } from "./plan.js";

/** Guarda el plan de aporte en el perfil sin que haya que abrir el modal. */
export function schedulePlanSave() {
  if (!estado.profileData || !estado.profileData.profile) return;   // sin perfil no hay dónde guardarlo
  clearTimeout(planTimer);
  planTimer = setTimeout(async () => {
    const ranges = readRanges();
    if (!ranges.every((r) => Number.isFinite(r.start_month) && Number.isFinite(r.end_month)
        && Number.isFinite(r.amount))) return;
    if (!readLumps().every((l) => Number.isFinite(l.year) && Number.isFinite(l.month)
        && Number.isFinite(l.amount))) return;
    try {
      estado.profileData = await api("POST", "/api/profile",
                              { ...profileFromForm(), ranges, lumps: readLumps() });
    } catch (e) { /* el error ya se ve en el panel de cálculo */ }
  }, 1500);
}

// --- perfil ----------------------------------------------------------
// Vive en un modal para no cargar la pantalla principal. El plan de aporte se
// guarda aquí y no en cada escenario, así cambiar de instrumento no obliga a
// reescribir los tramos.

let previewTimer = null;
let previewSeq = 0;        // descarta respuestas que llegan fuera de orden

export async function loadAfpParams() {
  estado.afpParams = await api("GET", "/api/afp/params");
  $("#p-inicio-mes").innerHTML = MESES
    .map((m, i) => `<option value="${i + 1}">${m}</option>`).join("");
  $("#p-afp").innerHTML = Object.keys(estado.afpParams.comisiones)
    .map((a) => `<option value="${a}">${a}</option>`).join("");
  $("#p-fondo").innerHTML = Object.entries(estado.afpParams.rentabilidad_real)
    .map(([f, r]) => `<option value="${f}">Fondo ${f} · ${r}% real anual</option>`).join("");
}

export function profileFromForm() {
  return {
    nacimiento: $("#p-nacimiento").value,
    sexo: $("#p-sexo").value,
    inicio_mes: parseInt($("#p-inicio-mes").value, 10),
    inicio_anio: parseInt($("#p-inicio-anio").value, 10),
    sueldo_imponible: parseAmount($("#p-sueldo").value),
    no_imponible: parseAmount($("#p-no-imponible").value) || 0,
    afp: $("#p-afp").value,
    comision_afp: parseFloat($("#p-comision").value),
    fondo: $("#p-fondo").value,
    saldo_afp: parseAmount($("#p-saldo").value),
    salud: $("#p-salud").value,
    salud_extra: parseAmount($("#p-salud-extra").value) || 0,
    contrato_indefinido: $("#p-indefinido").checked,
    aporte_empleador: parseFloat($("#p-empleador").value),
    trayectoria: $("#p-trayectoria").value,
    destino_salida_a: $("#p-salida-a").value,
    uf: parseAmount($("#p-uf").value),
    utm: parseAmount($("#p-utm").value),
    ranges: readRanges(),      // el plan de aporte que está en pantalla
  };
}

export function fillProfileForm(p) {
  const hoy = new Date();
  const d = p || {
    nacimiento: "1990-01-01", sexo: "hombre", inicio_mes: hoy.getMonth() + 1, inicio_anio: hoy.getFullYear(),
    sueldo_imponible: 0, no_imponible: 0,
    afp: "Habitat", comision_afp: 1.27, fondo: "B", saldo_afp: 0,
    salud: "fonasa", salud_extra: 0, contrato_indefinido: true,
    aporte_empleador: estado.afpParams ? estado.afpParams.aporte_empleador_cuenta : 0.1,
    uf: estado.afpParams ? estado.afpParams.uf_referencia : 40884.32,
    utm: estado.afpParams ? estado.afpParams.utm_referencia : 71721,
    trayectoria: "fijo", destino_salida_a: "B",
  };
  $("#p-nacimiento").value = d.nacimiento || "1990-01-01";
  $("#p-sexo").value = d.sexo;
  $("#p-inicio-mes").value = d.inicio_mes;
  $("#p-inicio-anio").value = d.inicio_anio;
  $("#p-sueldo").value = formatAmount(d.sueldo_imponible);
  $("#p-no-imponible").value = formatAmount(d.no_imponible);
  $("#p-afp").value = d.afp;
  $("#p-comision").value = d.comision_afp;
  $("#p-fondo").value = d.fondo;
  $("#p-saldo").value = formatAmount(d.saldo_afp);
  $("#p-salud").value = d.salud;
  $("#p-salud-extra").value = formatAmount(d.salud_extra);
  $("#p-indefinido").checked = d.contrato_indefinido;
  $("#p-empleador").value = d.aporte_empleador;
  $("#p-trayectoria").value = d.trayectoria || "fijo";
  $("#p-salida-a").value = d.destino_salida_a || "B";
  $("#p-uf").value = formatAmount(d.uf);
  $("#p-utm").value = formatAmount(d.utm || (estado.afpParams ? estado.afpParams.utm_referencia : 71721));
  syncProfileUI();
}

export function edadDesde(iso) {
  if (!iso) return NaN;
  const [y, m, d] = iso.split("-").map(Number);
  const hoy = new Date();
  const nace = new Date(y, m - 1, d);
  let años = hoy.getFullYear() - y - (hoy < new Date(hoy.getFullYear(), m - 1, d) ? 1 : 0);
  const ultimo = new Date(hoy.getFullYear() - (hoy < new Date(hoy.getFullYear(), m - 1, d) ? 1 : 0), m - 1, d);
  const siguiente = new Date(ultimo.getFullYear() + 1, m - 1, d);
  return Number.isNaN(nace.getTime()) ? NaN
    : Math.round((años + (hoy - ultimo) / (siguiente - ultimo)) * 100) / 100;
}

export function syncProfileUI() {
  $("#p-salud-extra-wrap").hidden = $("#p-salud").value !== "isapre";
  if (!estado.afpParams) return;
  const edad = edadDesde($("#p-nacimiento").value);
  const pensionAños = estado.afpParams.edad_pension[$("#p-sexo").value];
  $("#p-edad-calc").innerHTML = Number.isFinite(edad)
    ? `Tienes <strong>${Math.floor(edad)}</strong> años: te quedan ` +
      `<strong>${(pensionAños - edad).toFixed(1)}</strong> años de cotización hasta los ${pensionAños}.`
    : "Ingresa tu fecha de nacimiento para calcular la edad.";
  const sexo = $("#p-sexo").value;
  const t = estado.afpParams.tramos[sexo];
  const pension = estado.afpParams.edad_pension[sexo];
  if (!Number.isFinite(edad)) return;
  const porDefecto = edad <= t.b_hasta ? "B" : edad <= t.c_hasta ? "C" : "D";
  const modo = $("#p-trayectoria").value;
  const fondo = $("#p-fondo").value;
  $("#p-salida-a-wrap").hidden = !(modo === "fijo" && fondo === "A");
  // El esquema de traspasos asigna el fondo por edad, así que la elección de fondo
  // no se aplica. Antes el selector seguía activo y el resultado era el mismo eligiera
  // lo que eligiera: ahora se deshabilita y se dice por qué.
  const fondoSel = $("#p-fondo");
  fondoSel.disabled = modo !== "fijo";
  fondoSel.title = modo !== "fijo"
    ? "Con un esquema de traspasos por edad el fondo lo asigna el esquema, no tú."
    : "";

  const gradual = "El traspaso no es de golpe: se mueve <strong>20% del saldo al cumplir la " +
    "edad y 20% más cada año</strong>, completándose a los cuatro años. Las cotizaciones " +
    "nuevas van de inmediato al fondo que corresponde.";

  const porTramo =
    `Si nunca hubieras elegido fondo, la ley te asignaría por defecto: <strong>B hasta los ` +
    `35</strong>, <strong>C desde los 36 hasta los ${t.c_hasta}</strong> y ` +
    `<strong>D desde los ${t.traspaso_desde}</strong>.`;

  const salidaA = `La salida corre dentro de 90 días desde el cumpleaños y no es a un fondo ` +
    `determinado: puedes moverte a B, C, D o E, y por eso el destino se elige aquí.`;

  // Cuando la nota de arriba ya explicó la salida del A no se repite la edad.
  const sobreAyB = (fondo === "A" && modo === "fijo"
    ? `<br>${salidaA} `
    : `<br><strong>Fondo A</strong>: la ley te obliga a sacar de ahí el saldo por ` +
      `cotizaciones obligatorias al cumplir <strong>${t.traspaso_desde}</strong> años. ` +
      `${salidaA} `) +
    `<strong>Fondo B</strong>, en cambio, no tiene ninguna restricción de edad: puedes ` +
    `permanecer en él hasta jubilar.`;

  // "Fijo" no es fijo del todo: del fondo A la ley te expulsa, y ése es el único
  // fondo con tope de edad. La nota lo dice según el fondo elegido para no
  // prometer "hasta jubilar" a quien está en A.
  const fijoTexto = fondo === "A"
    ? `Te mantienes en el <strong>fondo A</strong> hasta los ` +
      `<strong>${t.traspaso_desde}</strong>, cuando la ley te obliga a salir: de ahí en ` +
      `adelante la proyección te deja en el <strong>fondo ${$("#p-salida-a").value}</strong>. ` +
      `${porTramo}`
    : `Te mantienes en el <strong>fondo ${fondo}</strong> hasta jubilar: fuera del A ningún ` +
      `fondo tiene restricción de edad, así que la ley nunca te obliga a moverte. ${porTramo}`;

  const modos = {
    fijo: fijoTexto,
    basico: `Esquema de traspasos por edad que se <em>contrata</em> con la AFP (no es ` +
      `automático). Contrato básico: hitos a los <strong>36</strong> y los ` +
      `<strong>${t.traspaso_desde}</strong> años, terminando en el <strong>fondo D</strong>. ` +
      gradual,
    ampliado: `Contrato ampliado: hitos a los <strong>31, 36, ${t.traspaso_desde} y ` +
      `${sexo === "hombre" ? 61 : 56}</strong> años, terminando en el <strong>fondo E</strong>. ` +
      gradual,
  };
  const [gAño, gMes] = (estado.afpParams.generacionales_desde || "2027-04").split("-");
  const fondoIgnorado = modo !== "fijo"
    ? `<br><strong>Tu fondo actual no entra en esta proyección</strong>: el esquema de ` +
      `traspasos asigna el fondo por edad, así que la proyección parte del que le ` +
      `corresponde al esquema y no del que tengas hoy. Elige <em>“Me quedo en mi fondo”</em> ` +
      `si quieres proyectar con el tuyo. `
    : "";
  $("#p-fondo-nota").innerHTML = modos[modo] + fondoIgnorado + sobreAyB +
    `<br>Ojo: en <strong>${MESES[Number(gMes) - 1]} de ${gAño}</strong> los multifondos ` +
    `se reemplazan por fondos ` +
    `generacionales asignados por año de nacimiento, sin opción de elegir en el ahorro ` +
    `obligatorio; la proyección usa la trayectoria de los multifondos porque los nuevos ` +
    `todavía no tienen rentabilidad observada.`;
}

export async function loadProfile() {
  const data = await api("GET", "/api/profile");
  estado.profileData = data;
  fillProfileForm(data.profile);
  if (data.ranges && data.ranges.length) {
    rangesBody.innerHTML = "";
    data.ranges.forEach((r) => addRange(r.start_month, r.end_month, r.amount));
  }
  lumpsBody.innerHTML = "";
  (data.lumps || []).forEach((l) => addLump(l.year, l.month, l.amount, l.label));
  // El plan de aporte llega después del primer cálculo, así que hay que rehacerlo.
  if ((data.ranges && data.ranges.length) || (data.lumps && data.lumps.length)) {
    emit("recalcular", 0);
  }
  renderAfp(data.afp);
  return data;
}

export async function saveProfile() {
  $("#profile-error").hidden = true;
  try {
    const data = await api("POST", "/api/profile", profileFromForm());
    estado.profileData = data;
    setLiquido(data.afp);
    renderAfp(data.afp);
    $("#profile-status").textContent = "Perfil guardado ✓";
    setTimeout(() => ($("#profile-status").textContent = ""), 2500);
  } catch (e) {
    const el = $("#profile-error");
    el.textContent = e.message;
    el.hidden = false;
  }
}

/** El modal recalcula solo mientras escribes, igual que el panel principal: el líquido
 *  y la proyección los devuelve el backend (las fórmulas legales viven en afp.py, no se
 *  duplican aquí) y las respuestas que llegan fuera de orden se descartan. Es una vista
 *  previa: no guarda nada, para eso sigue estando el botón. */
export function scheduleProfilePreview(delay = 220) {
  clearTimeout(previewTimer);
  previewTimer = setTimeout(previewProfile, delay);
}

export async function previewProfile() {
  const body = profileFromForm();
  if (!body.nacimiento || !Number.isFinite(body.sueldo_imponible) || body.sueldo_imponible <= 0) {
    return setLiquido(null, "Ingresa tu sueldo imponible y verás aquí el bruto y el líquido.");
  }
  const seq = ++previewSeq;
  try {
    const data = await api("POST", "/api/afp/preview", body);
    if (seq !== previewSeq) return;     // ya hay una vista previa más nueva en curso
    $("#profile-error").hidden = true;
    setLiquido(data.afp);
    renderAfp(data.afp);
  } catch (e) {
    if (seq !== previewSeq) return;
    setLiquido(null, e.message);
  }
}

/** Bruto percibido = imponible + asignaciones no imponibles. El líquido descuenta
 *  del bruto lo previsional y la salud, que sólo se calculan sobre el imponible. */
export function setLiquido(a, aviso) {
  const el = $("#p-liquido");
  if (!a) { el.textContent = aviso || ""; return; }
  const d = a.descuentos;
  el.innerHTML =
    `Bruto percibido: <strong>${fmtMoney(a.bruto_total)}</strong> = imponible ` +
    `${fmtMoney(a.bruto_total - a.no_imponible)} + no imponible ${fmtMoney(a.no_imponible)}.` +
    `<br>Líquido aproximado: <strong class="ok">${fmtMoney(a.liquido_aprox)}</strong> ` +
    `— descuentos ${fmtMoney(d.total)}: AFP ${fmtMoney(d.cotizacion)} · comisión ` +
    `${fmtMoney(d.comision)} · salud ${fmtMoney(d.salud)}` +
    (d.cesantia ? ` · cesantía ${fmtMoney(d.cesantia)}` : "") +
    (d.impuesto ? ` · impuesto único ${fmtMoney(d.impuesto)}` : " · sin impuesto único") +
    `.<br>El impuesto de segunda categoría sale de la tabla del SII en UTM sobre una base ` +
    `de ${fmtMoney(a.base_tributable)} (imponible menos cotizaciones obligatorias); las ` +
    `asignaciones no imponibles razonables no son renta afecta.` +
    (a.topado ? `<br>Tu imponible pasa el tope de ${fmtMoney(a.tope_imponible)}: las ` +
      `cotizaciones y la salud se calculan sólo hasta ahí.` : "");
}

export function renderAfp(a) {
  const banner = $("#afp-banner");
  const box = $("#afp-result");
  if (!a || !a.meses_hasta_pension) {
    banner.hidden = true;
    box.hidden = true;
    return;
  }
  box.hidden = false;

  const kpis = [
    { k: "Saldo hoy", v: fmtMoney(a.saldo_actual) },
    { k: `Saldo al jubilar (${a.edad_pension})`, v: fmtMoney(a.saldo_al_jubilar), cls: "good",
      sub: "en pesos de hoy" },
    { k: "Cotizado hasta entonces", v: fmtMoney(a.total_cotizado) },
    { k: "Rentabilidad ganada", v: fmtMoney(a.rentabilidad_ganada), cls: "good" },
    { k: "Pensión estimada", v: fmtMoney(a.pension_mensual), cls: "good",
      sub: `saldo / (12 × CNU ${a.cnu}) · ${a.expectativa_vida} años de expectativa · ` +
           `tasa técnica ${a.tasa_tecnica}%` },
    { k: "Descuentos del sueldo", v: fmtMoney(a.descuentos.total),
      sub: `AFP ${fmtMoney(a.descuentos.cotizacion)} · salud ${fmtMoney(a.descuentos.salud)} · ` +
           `impuesto ${fmtMoney(a.descuentos.impuesto)}` },
    { k: "Líquido aproximado", v: fmtMoney(a.liquido_aprox),
      sub: `de ${fmtMoney(a.bruto_total)} brutos` },
  ];
  $("#afp-kpis").innerHTML = kpis.map((c) =>
    `<div class="kpi"><div class="k">${c.k}</div><div class="v ${c.cls || ""}">${c.v}</div>` +
    (c.sub ? `<div class="sub">${c.sub}</div>` : "") + "</div>").join("");

  $("#afp-trayectoria tbody").innerHTML = a.detalle.map((f) =>
    `<tr><td>${f.edad}</td><td>Fondo ${f.fondo}</td>` +
    `<td class="num">${f.tasa_real}%</td><td class="num">${fmtMoney(f.saldo)}</td></tr>`).join("");

  renderAfpBanner(a);
}

/** El banner refleja los supuestos del escenario en pantalla (hasta qué edad trabajas),
 *  no sólo los del perfil, que asume cotizar hasta jubilar. */
export function renderAfpBanner(a) {
  const banner = $("#afp-banner");
  if (!a || !a.saldo_al_jubilar) { banner.hidden = true; return; }
  banner.hidden = false;
  const paraDe = a.trabajo_hasta && a.trabajo_hasta < a.edad_pension
    ? ` Dejas de cotizar a los <strong>${a.trabajo_hasta}</strong>, así que el saldo ` +
      `sigue rentando hasta jubilar pero sin plata nueva.`
    : "";
  banner.innerHTML =
    `<strong>Tu AFP</strong>: partiendo de ${fmtMoney(a.saldo_actual)} y cotizando ` +
    `${fmtMoney(a.descuentos.cotizacion)} al mes, llegarías a los ${a.edad_pension} con ` +
    `<strong class="ok">${fmtMoney(a.saldo_al_jubilar)}</strong> en pesos de hoy ` +
    `(fondo ${a.fondo_inicial} → ${a.fondo_final})` +
    (a.topado ? `. Tu sueldo supera el tope imponible de ${fmtMoney(a.tope_imponible)}, ` +
      `así que cotizas sólo hasta ahí.` : ".") + paraDe +
    ` Ese saldo financia una pensión de <strong class="ok">${fmtMoney(a.pension_mensual)}</strong> ` +
    `al mes en pesos de hoy, que la proyección descuenta de tu meta desde esa edad.`;
}

export function openProfile() {
  $("#profile-modal").hidden = false;
  document.body.style.overflow = "hidden";
  fillProfileForm(estado.profileData && estado.profileData.profile);
  scheduleProfilePreview(0);
  $("#p-nacimiento").focus();
}

export function closeProfile() {
  $("#profile-modal").hidden = true;
  document.body.style.overflow = "";
  // La vista previa no guarda: al salir sin guardar, el banner vuelve a lo persistido.
  clearTimeout(previewTimer);
  previewSeq++;
  renderAfp(estado.profileData && estado.profileData.afp);
}
