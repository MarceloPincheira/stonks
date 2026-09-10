/** Página de documentación: sirve los .md del repositorio desde la propia app. */
const $ = (sel) => document.querySelector(sel);

let docs = [];
let actual = null;

/** Dos formas de hash conviven y hay que distinguirlas: `#/slug` elige documento,
 *  `#seccion` es un ancla dentro del que ya está abierto. Sin separarlas, hacer clic
 *  en el índice recargaba el documento entero y perdía la posición. */
function slugDesdeUrl() {
  const h = location.hash || "";
  return h.startsWith("#/") ? (h.slice(2).split("/")[0] || null) : null;
}

/** Este 404 tiene una causa concreta y repetible: la página es un archivo estático que
 *  el servidor lee del disco en cada request, pero las rutas viven en el módulo que
 *  Python cargó al arrancar. Tras tocar un .py, la página nueva aparece y la ruta que
 *  necesita todavía no existe. Decirlo ahorra el rato de buscar el error en otra parte. */
const SERVIDOR_DESACTUALIZADO =
  "El servidor no conoce la ruta /api/docs. Si acabas de actualizar el código, " +
  "reinícialo con  make restart : Python mantiene los módulos cargados en memoria, " +
  "así que los archivos de static/ se ven al instante pero las rutas nuevas no.";

async function cargarIndice() {
  const res = await fetch("/api/docs");
  if (!res.ok) {
    throw new Error(res.status === 404 ? SERVIDOR_DESACTUALIZADO
                                       : `No pude leer el índice de documentos (${res.status}).`);
  }
  docs = await res.json();
  $("#doc-list").innerHTML = docs.map((d) =>
    `<li><a href="#/${d.slug}" data-slug="${d.slug}">${d.titulo}</a>` +
    `<span class="doc-detalle">${d.detalle}</span></li>`).join("");
}

async function cargarDoc(slug) {
  const meta = docs.find((d) => d.slug === slug) || docs[0];
  if (!meta) return;
  actual = meta.slug;
  $("#doc-status").hidden = false;
  $("#doc-status").textContent = "Cargando…";
  try {
    const res = await fetch(`/api/docs/${meta.slug}`);
    if (!res.ok) {
      throw new Error(res.status === 404 ? SERVIDOR_DESACTUALIZADO
                                         : `No se pudo leer el documento (${res.status}).`);
    }
    const md = await res.text();
    const { html, toc } = renderMarkdown(md);
    $("#doc-content").innerHTML = html;
    $("#toc-title").hidden = !toc.length;
    $("#doc-toc").innerHTML = toc.map((t) =>
      `<li class="n${t.nivel}"><a href="#${t.id}">${t.texto}</a></li>`).join("");
    $("#doc-status").hidden = true;
    document.title = `Stonks · ${meta.titulo}`;
  } catch (e) {
    $("#doc-status").textContent = e.message;
    $("#doc-content").innerHTML = "";
  }
  document.querySelectorAll("#doc-list a").forEach((a) =>
    a.classList.toggle("activo", a.dataset.slug === actual));

  // Un enlace directo a una sección (docs.html#7-2-impuesto-...) llega antes de que el
  // documento exista: el navegador intenta saltar, no encuentra el ancla y se queda
  // arriba. Con el contenido ya montado, el salto se hace aquí.
  //
  // Va diferido a propósito: recién asignado el innerHTML el navegador todavía no
  // terminó de maquetar las ~18.000 px del documento, así que scrollIntoView() calcula
  // sobre un layout a medias y no se mueve. Un tick basta. Se usa setTimeout y no
  // requestAnimationFrame porque este último no dispara en una pestaña de fondo, que es
  // justo el caso de abrir el enlace en una pestaña nueva.
  const h = location.hash || "";
  const idAncla = !h.startsWith("#/") && h.length > 1 ? h.slice(1) : null;
  setTimeout(() => {
    const ancla = idAncla && document.getElementById(idAncla);
    if (ancla) ancla.scrollIntoView();
    else window.scrollTo(0, 0);
  }, 0);
}

window.addEventListener("hashchange", () => {
  const s = slugDesdeUrl();
  if (s && s !== actual) cargarDoc(s);   // un ancla de sección la resuelve el navegador
});

cargarIndice().then(() => cargarDoc(slugDesdeUrl() || "modelo")).catch((e) => {
  $("#doc-status").hidden = false;
  $("#doc-status").textContent = e.message || "No pude cargar la documentación.";
});
