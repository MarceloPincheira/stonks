/** La tabla de detalle: columnas por vista y render con Grid.js, que llega como global
 *  desde static/vendor/. */
import { $ } from "./dom.js";
import { fmtMoney } from "./formato.js";
import { estado } from "./estado.js";

/** Las columnas dependen del modo: nunca se muestran dos que valgan lo mismo.
 *  Con reinversión, "en el fondo" y "valor total" son idénticas, así que sobra una;
 *  sin reinversión, "aportado + reinvertido" es igual a "aportado", y sobra esa. */
export function yearlyColumns() {
  const withDiv = estado.lastResult.model === "dividends";
  const reinv = estado.lastResult.reinvest;
  const cols = [
    { th: "Año", cls: "", get: (r) => r.year },
    { th: "Aportado por ti", tip: "Sólo el dinero que saliste a poner de tu bolsillo.",
      get: (r) => fmtMoney(r.invested) },
  ];
  cols.push({ th: "Aportado en pesos de hoy",
    tip: "Cada aporte llevado a pesos de hoy: el esfuerzo real que hiciste.",
    get: (r) => fmtMoney(r.invested_real) });
  if (withDiv && reinv) {
    cols.push({ th: "Aportado + reinvertido",
      tip: "Tus aportes más los dividendos que volvieron al fondo: el capital total trabajando.",
      get: (r) => fmtMoney(r.cost_basis) });
    cols.push({ th: "Aportado + reinvertido en pesos de hoy",
      tip: "Ese mismo capital, con cada flujo deflactado en el momento en que entró.",
      get: (r) => fmtMoney(r.cost_basis_real) });
  }
  if (withDiv) {
    cols.push({ th: "Dividendos del año",
      tip: estado.lastResult.dividend_tax
        ? "Lo que el fondo repartió durante ese año, en bruto. La columna neta de al lado es la "
          + "que se reinvierte y con la que se mide la cobertura de tu meta."
        : "Lo que el fondo te repartió durante ese año (la suma de sus pagos).",
      get: (r) => fmtMoney(r.dividends_year) });
    cols.push({ th: "Dividendos acum.", tip: "Todo lo repartido por el fondo hasta ese año, en bruto.",
      get: (r) => fmtMoney(r.dividends_total) });
    if (estado.lastResult.dividend_tax) {
      cols.push({ th: "Dividendos acum. netos",
        tip: `Lo repartido menos el ${estado.lastResult.dividend_tax}% de impuesto: lo que de verdad ` +
             `se reinvirtió o se cobró.`,
        get: (r) => fmtMoney(r.dividends_net_total) });
    }
    cols.push({ th: "Plusvalía acum.",
      tip: "Cuánto subió el valor de las cuotas por sobre el capital puesto en el fondo.",
      get: (r) => fmtMoney(r.capital_gain) });
  }
  if (withDiv && !reinv) {
    cols.push({ th: "En el fondo", tip: "Valor de mercado de tus cuotas.",
      get: (r) => fmtMoney(r.portfolio) });
    cols.push({ th: "Efectivo cobrado", tip: "Dividendos que retiraste y no rentan.",
      get: (r) => fmtMoney(r.cash) });
  }
  cols.push({ th: "Valor total", tip: "Lo que tendrías en total ese año.",
    get: (r) => fmtMoney(r.balance) });
  cols.push({ th: "Ganancia",
    tip: withDiv
      ? "Dividendos acum. + plusvalía acum. Es lo mismo que valor total − aportado por ti."
      : "Valor total menos lo que aportaste de tu bolsillo.",
    get: (r) => fmtMoney(r.gain) });
  return cols;
}

export function monthlyColumns() {
  const withDiv = estado.lastResult.model === "dividends";
  const cols = [
    { th: "Mes", cls: "", get: (r) => r.month },
    { th: "Aporte", html: true,
      tip: "El aporte del tramo más el extraordinario que caiga ese mes.",
      get: (r) => (r.lump
        ? `${fmtMoney(r.contribution)} <span class="tag">extra ${fmtMoney(r.lump)}</span>`
        : fmtMoney(r.contribution)) },
    { th: "Aportado por ti", get: (r) => fmtMoney(r.invested) },
    { th: withDiv ? "Plusvalía del mes" : "Interés del mes", get: (r) => fmtMoney(r.interest) },
  ];
  if (withDiv) {
    cols.push({ th: "Dividendo", get: (r) => (r.dividend ? fmtMoney(r.dividend) : "—") });
    if (estado.lastResult.reinvest) {
      cols.push({ th: "Aportado + reinvertido", get: (r) => fmtMoney(r.cost_basis) });
    }
  }
  cols.push({ th: "Valor total", get: (r) => fmtMoney(r.balance) });
  return cols;
}

let grid = null;

/** ¿Hay pensión de la AFP en juego en el resultado en pantalla? */
export function conPension() {
  return !!(estado.lastResult && estado.lastResult.include_pension && estado.lastResult.pension_monthly > 0
            && estado.lastResult.pension_start_year);
}

export function purchasingColumns() {
  // Sin dividendos no hay reparto que mostrar: en el modelo simple esas columnas
  // marcaban $0 y 0% en todos los años. El retiro sostenible sí aplica —es el
  // retorno real—, así que ése se queda.
  const withDiv = estado.lastResult.model === "dividends";
  return [
    { th: "Año", cls: "", get: (r) => r.year },
    ...(withDiv ? [
      { th: "Dividendo mensual", tip: "Lo que recibirías al mes ese año, neto de impuesto y en pesos de ese año.",
        get: (r) => fmtMoney(r.dividend_monthly) },
    ] : []),
    { th: "Meta del mes", tip: "Lo que costará ese año vivir como hoy con tu monto objetivo.",
      get: (r) => fmtMoney(r.goal_monthly) },
    ...(conPension() ? [
      { th: "Pensión AFP",
        tip: "Lo que pagaría tu AFP ese año, en pesos de ese año. Parte desde la edad de " +
             "jubilación; el primer año va prorrateado por los meses que alcanza a pagar.",
        get: (r) => (r.pension_monthly ? fmtMoney(r.pension_monthly) : "—") },
      { th: "Falta cubrir",
        tip: "La meta menos la pensión: lo que tiene que poner la inversión.",
        get: (r) => fmtMoney(r.goal_from_portfolio) },
    ] : []),
    ...(withDiv ? [
      { th: "Cobertura", tip: "Qué porcentaje de lo que falta cubren tus dividendos.", html: true,
        get: (r) => {
          if (r.coverage === null) return "—";
          const pct = Math.min(100, r.coverage);
          return `<span class="bar${r.coverage >= 100 ? "" : " short"}" style="width:${pct * 0.5}px"></span>` +
            `${r.coverage.toFixed(0)}%`;
        } },
    ] : []),
    { th: "Retiro sostenible",
      tip: "Lo que podrías sacar al mes ese año sin que el capital pierda poder adquisitivo: "
         + "el retorno real del instrumento. Consumirlo entero deja el capital constante en "
         + "pesos de hoy; parte llega como reparto y el resto exige vender.",
      get: (r) => fmtMoney(r.sustainable_monthly) },
    { th: "Cobertura sostenible",
      tip: "Qué porcentaje de la meta cubre ese retiro sostenible. Al llegar a 100% eres independiente.",
      html: true,
      get: (r) => {
        if (r.sustainable_coverage === null) return "—";
        const pct = Math.min(100, r.sustainable_coverage);
        return `<span class="bar${r.sustainable_coverage >= 100 ? "" : " short"}" ` +
          `style="width:${pct * 0.5}px"></span>${r.sustainable_coverage.toFixed(0)}%`;
      } },
    ...(withDiv ? [
      { th: "Dividendo en pesos de hoy",
        tip: "El mismo dividendo mensual descontada la inflación: su poder adquisitivo real.",
        get: (r) => fmtMoney(r.dividend_monthly_real) },
    ] : []),
    { th: "Valor total en pesos de hoy",
      tip: "Tu patrimonio deflactado, o sea lo que compraría a precios de hoy.",
      get: (r) => fmtMoney(r.real_balance) },
  ];
}

export function renderDetail() {
  if (!estado.lastResult) return;
  const byView = {
    yearly: [yearlyColumns, () => estado.lastResult.yearly],
    monthly: [monthlyColumns, () => estado.lastResult.months],
    purchasing: [purchasingColumns, () => estado.lastResult.yearly],
  };
  const [colsFn, rowsFn] = byView[estado.detailView];
  const cols = colsFn();
  const rows = rowsFn();

  const config = {
    columns: cols.map((c, i) => ({
      name: c.th,
      ...(c.html ? { formatter: (cell) => gridjs.html(String(cell)) } : {}),
      // La primera columna (año/mes) es un entero; el resto son montos alineados a la derecha.
      sort: { compare: i === 0 ? undefined : compareMoney },
      attributes: (cell) => (cell === null ? {} : { class: i === 0 ? "gridjs-td" : "gridjs-td num" }),
    })),
    data: rows.map((r) => cols.map((c) => String(c.get(r)))),
    sort: true,
    pagination: false,
    // Todas las filas de una vez, con scroll interno y encabezado fijo:
    // así el largo de la página no crece con el horizonte.
    fixedHeader: true,
    height: "460px",
    className: { table: "detail-table" },
  };

  const host = $("#detail-grid");
  if (grid) {
    grid.updateConfig(config).forceRender();
  } else {
    grid = new gridjs.Grid(config).render(host);
    enableCrossHighlight(host);
  }
  applyHeaderTips(host, cols);
  $(".grid-tip").innerHTML = estado.detailView === "purchasing"
    ? "Cada columna dice en qué pesos está: las de <em>pesos de hoy</em> vienen deflactadas, " +
      "el resto son pesos de cada año. Haz clic en una celda para resaltar su fila y su columna."
    : "Los montos están en <strong>pesos de cada año</strong> (nominales), salvo las columnas " +
      "que digan lo contrario. Haz clic en una celda para resaltar su fila y su columna.";
}

/** Ordena montos formateados ("$1.234.567") por su valor numérico. */
export function compareMoney(a, b) {
  const clean = (v) => String(v).replace(/<[^>]*>/g, "");   // descarta el markup de la barra
  const n = (v) => parseFloat(clean(v).replace(/[^\d,.-]/g, "").replace(/\./g, "").replace(",", ".")) || 0;
  return n(a) - n(b);
}

export function applyHeaderTips(host, cols) {
  host.querySelectorAll("th.gridjs-th").forEach((th, i) => {
    if (cols[i] && cols[i].tip) th.title = cols[i].tip;
  });
}

/** Clic en una celda: resalta su fila y su columna completas. */
export function enableCrossHighlight(host) {
  host.addEventListener("click", (e) => {
    const td = e.target.closest("td.gridjs-td");
    const table = host.querySelector("table");
    if (!table) return;
    if (!td) return;

    const col = td.cellIndex;
    const active = td.classList.contains("cross-cell");
    table.querySelectorAll(".cross-row, .cross-col, .cross-cell")
      .forEach((el) => el.classList.remove("cross-row", "cross-col", "cross-cell"));
    if (active) return;                       // segundo clic en la misma celda: apagar

    td.parentElement.classList.add("cross-row");
    td.classList.add("cross-cell");
    table.querySelectorAll("tr").forEach((tr) => {
      const cell = tr.children[col];
      if (cell && cell !== td) cell.classList.add("cross-col");
    });
  });
}
