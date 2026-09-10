/** Render de Markdown acotado a lo que usan los documentos del proyecto: encabezados,
 *  tablas, bloques de código, citas, listas, énfasis y enlaces. No pretende cubrir
 *  Markdown completo — cubre este corpus, que está en el repositorio y es estable.
 *
 *  Se escribe a mano en vez de traer una librería porque la app no tiene dependencias:
 *  el resto del frontend son dos archivos vendorizados y nada más. */
const esc = (t) => t.replace(/[&<>]/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;" }[c]));

/** Sólo se aceptan enlaces http(s) o anclas: cualquier otro esquema se degrada a texto,
 *  para que un `javascript:` en un documento no se convierta en un enlace ejecutable. */
function enlaceSeguro(texto, url) {
  if (/^https?:\/\//i.test(url)) {
    return `<a href="${esc(url)}" target="_blank" rel="noopener noreferrer">${texto}</a>`;
  }
  if (/^#/.test(url)) return `<a href="${esc(url)}">${texto}</a>`;
  return texto;
}

function inline(t) {
  // Los caracteres escapados en el origen (\$, \*, \_) se apartan antes de aplicar
  // el formato y se reponen al final: si se desescaparan primero, un \* se leería
  // como marca de énfasis; si no se desescaparan nunca, la barra quedaría a la vista.
  const apartados = [];
  let x = esc(t).replace(/\\([\\`*_{}\[\]()#+\-.!$|])/g, (_, c) => {
    apartados.push(c);
    return `\u0000${apartados.length - 1}\u0000`;
  });
  x = x
    .replace(/`([^`]+)`/g, (_, c) => `<code>${c}</code>`)
    .replace(/\[([^\]]+)\]\(([^)\s]+)\)/g, (_, txt, url) => enlaceSeguro(txt, url))
    .replace(/\*\*([^*]+)\*\*/g, "<strong>$1</strong>")
    .replace(/(^|[^*\w])\*([^*\n]+)\*/g, "$1<em>$2</em>");
  return x.replace(/\u0000(\d+)\u0000/g, (_, i) => apartados[Number(i)]);
}

const slug = (t) => t.toLowerCase().normalize("NFD").replace(/[̀-ͯ]/g, "")
  .replace(/[^a-z0-9]+/g, "-").replace(/^-|-$/g, "");

function celdas(linea) {
  return linea.replace(/^\||\|$/g, "").split("|").map((c) => c.trim());
}

export function render(src) {
  const lineas = src.replace(/\r\n/g, "\n").split("\n");
  const html = [];
  const toc = [];
  let i = 0;

  while (i < lineas.length) {
    const L = lineas[i];

    // bloque de código: se copia literal, sin tocar nada de lo que hay dentro
    if (/^```/.test(L)) {
      const cuerpo = [];
      i++;
      while (i < lineas.length && !/^```/.test(lineas[i])) cuerpo.push(lineas[i++]);
      i++;
      html.push(`<pre><code>${esc(cuerpo.join("\n"))}</code></pre>`);
      continue;
    }

    // tabla: una fila de encabezado seguida de la fila de guiones
    if (/^\s*\|/.test(L) && /^\s*\|[\s:|-]+\|\s*$/.test(lineas[i + 1] || "")) {
      const head = celdas(L);
      i += 2;
      const filas = [];
      while (i < lineas.length && /^\s*\|/.test(lineas[i])) filas.push(celdas(lineas[i++]));
      html.push(
        `<div class="doc-tabla"><table><thead><tr>` +
        head.map((c) => `<th>${inline(c)}</th>`).join("") +
        `</tr></thead><tbody>` +
        filas.map((f) => `<tr>${f.map((c) => `<td>${inline(c)}</td>`).join("")}</tr>`).join("") +
        `</tbody></table></div>`);
      continue;
    }

    const h = L.match(/^(#{1,6})\s+(.*)$/);
    if (h) {
      const n = h[1].length;
      const texto = h[2].replace(/\s*#+\s*$/, "");
      const id = slug(texto);
      if (n === 2 || n === 3) toc.push({ nivel: n, texto, id });
      html.push(`<h${n} id="${id}">${inline(texto)}</h${n}>`);
      i++;
      continue;
    }

    if (/^\s*(---+|\*\*\*+)\s*$/.test(L)) { html.push("<hr>"); i++; continue; }

    if (/^>\s?/.test(L)) {
      const cuerpo = [];
      while (i < lineas.length && /^>\s?/.test(lineas[i])) {
        cuerpo.push(lineas[i++].replace(/^>\s?/, ""));
      }
      html.push(`<blockquote>${render(cuerpo.join("\n")).html}</blockquote>`);
      continue;
    }

    const lista = /^(\s*)([-*]|\d+\.)\s+/.exec(L);
    if (lista) {
      const ordenada = /\d/.test(lista[2]);
      const items = [];
      while (i < lineas.length) {
        const m = /^(\s*)([-*]|\d+\.)\s+(.*)$/.exec(lineas[i]);
        if (!m) {
          // continuación indentada del ítem anterior
          if (items.length && /^\s{2,}\S/.test(lineas[i])) {
            items[items.length - 1] += " " + lineas[i].trim();
            i++;
            continue;
          }
          break;
        }
        items.push(m[3]);
        i++;
      }
      const tag = ordenada ? "ol" : "ul";
      html.push(`<${tag}>` + items.map((t) => `<li>${inline(t)}</li>`).join("") + `</${tag}>`);
      continue;
    }

    if (L.trim() === "") { i++; continue; }

    const parrafo = [];
    while (i < lineas.length && lineas[i].trim() !== ""
           && !/^(```|>|#{1,6}\s|\s*\||\s*(---+|\*\*\*+)\s*$)/.test(lineas[i])
           && !/^(\s*)([-*]|\d+\.)\s+/.test(lineas[i])) {
      parrafo.push(lineas[i++]);
    }
    if (parrafo.length) html.push(`<p>${inline(parrafo.join("\n"))}</p>`);
    else i++;
  }

  return { html: html.join("\n"), toc };
}
