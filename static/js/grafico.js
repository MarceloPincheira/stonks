/** El gráfico: acumulación, consumo del patrimonio y saldo de la AFP en un mismo eje.
 *  Chart.js llega como global desde static/vendor/. */
import { $ } from "./dom.js";
import { fmtMoney, shortNum } from "./formato.js";
import { estado } from "./estado.js";

const THEME = {
  afp: "#38bdf8",
  retirement: "#f472b6",
  balance: "#4ade80",
  invested: "#60a5fa",
  portfolio: "#a78bfa",
  cash: "#fbbf24",
  grid: "#252c36",
  text: "#93a1b3",
  tooltipBg: "#1e242d",
};

let chart = null;

/** El eje va más allá del horizonte cuando hay fase de retiro: hasta la edad objetivo. */
export function chartSpan(r) {
  const ret = r.retirement;
  return Math.max(r.total_months, ret ? ret.end_month : 0, (r.afp_series || []).length);
}

/** Alinea una serie corta al eje completo rellenando con null (Chart.js corta la línea). */
export function padSeries(values, span, from = 0) {
  const out = new Array(span).fill(null);
  values.forEach((v, i) => { if (from + i < span) out[from + i] = v; });
  return out;
}

export function drawChart(r) {
  const showCash = r.model === "dividends" && !r.reinvest;
  const span = chartSpan(r);
  const ret = r.retirement;
  // Cuando hay fase de retiro las dos curvas del fondo son el mismo dinero bajo
  // supuestos opuestos, así que el nombre tiene que decir cuál es cuál.
  const bifurca = !!(ret && ret.months.length && r.total_months > ret.start_month);
  const series = [
    { color: THEME.balance, fill: true, rol: "fondo",
      label: (showCash ? "Valor total (fondo + efectivo)" : "Valor acumulado") +
             (bifurca ? " · sin consumir nada" : ""),
      values: padSeries(r.months.map((m) => m.balance), span) },
    { color: THEME.invested, label: "Aportado por ti", dash: [6, 4],
      values: padSeries(r.months.map((m) => m.invested), span) },
  ];
  if (showCash) {
    series.push({ color: THEME.portfolio, label: "Valor en el fondo",
      values: padSeries(r.months.map((m) => m.portfolio), span) });
    series.push({ color: THEME.cash, label: "Efectivo cobrado",
      values: padSeries(r.months.map((m) => m.cash), span) });
  }
  if (r.afp_series && r.afp_series.length) {
    // Sube mientras cotizas y baja mientras te paga la pensión: se agota justo a la
    // expectativa de vida, que es el supuesto con que la AFP calcula el monto.
    series.push({ color: THEME.afp, label: "Saldo en la AFP", rol: "afp",
      values: padSeries(r.afp_series.map((a) => a.balance), span) });
  }
  if (ret && ret.months.length) {
    // Arranca donde dejas de aportar, así que se ve la bifurcación entre seguir
    // acumulando sin tocar nada y empezar a consumir.
    series.push({ color: THEME.retirement, rol: "consumo",
      label: `Consumiendo tu meta desde los ${ret.start_age}`,
      values: padSeries(ret.months.map((m) => m.balance), span, ret.start_month) });
  }

  const ctx = $("#chart").getContext("2d");
  const gradient = ctx.createLinearGradient(0, 0, 0, 320);
  gradient.addColorStop(0, "rgba(74, 222, 128, 0.28)");
  gradient.addColorStop(1, "rgba(74, 222, 128, 0.01)");

  // Deflactar es dividir por (1+i)^(mes/12): la misma cuenta que usan las tarjetas,
  // aplicada punto a punto para que la curva no arrastre la inflación.
  const infl = (r.inflation || 0) / 100;
  const real = estado.chartUnits === "real" && infl !== 0;
  const aUnidad = (values) => (real
    ? values.map((v, i) => (v === null ? null : v / (1 + infl) ** ((i + 1) / 12)))
    : values);

  const bifurcacion = bifurca
    ? ` Desde los <strong>${ret.start_age}</strong>, cuando dejas de aportar, el fondo se ` +
      `dibuja dos veces: la línea verde es lo que tendrías <strong>si no sacaras nada</strong> ` +
      `y la rosada descuenta mes a mes lo que gastas. Son el mismo dinero bajo supuestos ` +
      `opuestos; la diferencia entre ambas es lo que consumiste más lo que ese dinero ` +
      `habría rentado.`
    : "";

  $("#chart-note").innerHTML = real
    ? `Deflactado a <strong>pesos de hoy</strong>: cada punto dividido por ` +
      `(1 + ${r.inflation}%)^(mes/12), así se ve el poder adquisitivo y no la inflación. ` +
      `Es la misma unidad en que habla el modal del perfil.`
    : `En <strong>pesos nominales</strong> de cada año, como las tarjetas de arriba. ` +
      `El tooltip muestra el equivalente en pesos de hoy, que es la unidad del modal ` +
      `del perfil.`;
  $("#chart-note").innerHTML += bifurcacion;

  const data = {
    labels: Array.from({ length: span }, (_, i) => i + 1),
    datasets: series.map((sr) => ({
      label: sr.label,
      rol: sr.rol || null,
      data: aUnidad(sr.values),
      spanGaps: false,
      borderColor: sr.color,
      backgroundColor: sr.fill ? gradient : sr.color,
      borderWidth: 2,
      borderDash: sr.dash || [],
      fill: sr.fill ? "origin" : false,
      pointRadius: 0,
      pointHoverRadius: 4,
      pointHoverBackgroundColor: sr.color,
      pointHoverBorderColor: "#0f1216",
      pointHoverBorderWidth: 2,
      tension: 0.25,
    })),
  };

  const options = {
    responsive: true,
    maintainAspectRatio: false,
    interaction: { mode: "index", intersect: false },
    plugins: {
      legend: {
        position: "bottom",
        labels: { color: THEME.text, boxWidth: 12, boxHeight: 12, usePointStyle: true,
          pointStyle: "rectRounded", padding: 16, font: { size: 12 } },
      },
      tooltip: {
        backgroundColor: THEME.tooltipBg,
        borderColor: "#333c48",
        borderWidth: 1,
        titleColor: "#e6ebf2",
        bodyColor: "#e6ebf2",
        footerColor: "#4ade80",
        footerFont: { weight: "600" },
        footerMarginTop: 8,
        padding: 10,
        cornerRadius: 8,
        displayColors: true,
        usePointStyle: true,
        callbacks: {
          title: (items) => {
            const m = items[0].parsed.x + 1;
            const años = Math.floor(m / 12);
            const meses = m % 12;
            const edad = estado.lastResult && estado.lastResult.start_age
              ? ` · ${(estado.lastResult.start_age + m / 12).toFixed(1)} años`
              : "";
            return `Mes ${m}` + (años ? ` · año ${años}${meses ? ` y ${meses} m` : ""}` : "") + edad;
          },
          // El gráfico va en pesos nominales, pero el perfil y las tarjetas hablan en
          // pesos de hoy: sin la equivalencia al lado, el mismo saldo parece dos cifras
          // distintas según dónde se mire.
          // El total suma fondo + AFP. Cuando la rama de consumo existe manda ella,
          // porque es el mismo fondo bajo otro supuesto: sumar las dos lo duplicaría.
          footer: (items) => {
            const rol = (n) => items.find((i) => i.dataset.rol === n);
            const fondo = rol("consumo") || rol("fondo");
            const afp = rol("afp");
            if (!fondo && !afp) return "";
            const total = (fondo ? fondo.parsed.y : 0) + (afp ? afp.parsed.y : 0);
            return `Patrimonio total: ${fmtMoney(total)}` +
              (fondo && afp ? ` (fondo + AFP)` : "");
          },
          label: (item) => {
            const m = item.parsed.x + 1;
            const i = (estado.lastResult ? estado.lastResult.inflation : 0) / 100;
            const factor = (1 + i) ** (m / 12);
            const otra = estado.chartUnits === "real" ? item.parsed.y * factor : item.parsed.y / factor;
            const sufijo = estado.chartUnits === "real" ? "nominales" : "de hoy";
            return ` ${item.dataset.label}: ${fmtMoney(item.parsed.y)}` +
              (i ? ` (${fmtMoney(otra)} ${sufijo})` : "");
          },
        },
      },
    },
    scales: {
      x: {
        grid: { color: THEME.grid, drawTicks: false },
        border: { color: THEME.grid },
        ticks: {
          color: THEME.text, maxRotation: 0, autoSkip: false, font: { size: 11 },
          callback: (v, i) => {
            const m = i + 1;
            const stepYears = Math.max(1, Math.ceil(r.total_months / 12 / 10));
            return m % (12 * stepYears) === 0 ? `${m / 12}a` : "";
          },
        },
      },
      y: {
        grid: { color: THEME.grid, drawTicks: false },
        border: { display: false },
        ticks: { color: THEME.text, padding: 8, callback: (v) => shortNum(v) },
      },
    },
  };

  if (chart) {
    chart.data = data;
    chart.options = options;
    chart.update("none");
  } else {
    chart = new Chart(ctx, { type: "line", data, options });
  }
}
