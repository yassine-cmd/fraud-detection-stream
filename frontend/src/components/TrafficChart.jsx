import {
  BarElement,
  CategoryScale,
  Chart as ChartJS,
  Filler,
  Legend,
  LinearScale,
  LineElement,
  PointElement,
  Tooltip,
} from "chart.js";
import { Chart } from "react-chartjs-2";
import { IconRadio } from "../icons.jsx";

ChartJS.register(CategoryScale, LinearScale, PointElement, LineElement, BarElement, Filler, Legend, Tooltip);

const GRID = "rgba(148, 163, 184, 0.08)";
const TICK = "#64748b";
const TOOLTIP = {
  backgroundColor: "rgba(8, 13, 24, 0.96)",
  borderColor: "rgba(148, 163, 184, 0.18)",
  borderWidth: 1,
  padding: 12,
  titleColor: "#e2e8f0",
  bodyColor: "#a8b6c8",
  displayColors: true,
  boxPadding: 4,
  usePointStyle: true,
  titleFont: { size: 12, weight: "600" },
  bodyFont: { size: 12 },
};

const OPTIONS = {
  responsive: true,
  maintainAspectRatio: false,
  animation: false,
  interaction: { mode: "index", intersect: false },
  plugins: {
    legend: { display: false },
    tooltip: {
      ...TOOLTIP,
      callbacks: {
        title: (items) => (items.length ? `${items[0].label} UTC` : ""),
        label: (context) =>
          context.dataset.yAxisID === "y1"
            ? `Fraudes bloquées : ${context.parsed.y}`
            : `Transactions : ${Number(context.parsed.y).toLocaleString("fr-FR")}`,
      },
    },
  },
  scales: {
    x: {
      grid: { display: false },
      border: { display: false },
      ticks: { color: TICK, maxTicksLimit: 8, maxRotation: 0, font: { size: 10.5 } },
    },
    y: {
      beginAtZero: true,
      border: { display: false },
      grid: { color: GRID, drawTicks: false },
      ticks: {
        color: TICK,
        precision: 0,
        maxTicksLimit: 5,
        padding: 10,
        font: { size: 10.5 },
        callback: (value) => Number(value).toLocaleString("fr-FR"),
      },
    },
    y1: {
      beginAtZero: true,
      position: "right",
      border: { display: false },
      grid: { display: false },
      ticks: { color: "#fda4af", precision: 0, maxTicksLimit: 4, font: { size: 10.5 } },
    },
  },
};

export default function TrafficChart({ points = [] }) {
  const hasData = points.some((point) => point.tx > 0);
  const labels = points.map((point) => (point.t || "").slice(11, 19));
  const maxFrauds = Math.max(1, ...points.map((point) => point.frauds || 0));
  const data = {
    labels,
    datasets: [
      {
        type: "line",
        label: "Transactions",
        data: points.map((point) => point.tx),
        yAxisID: "y",
        borderColor: "#38bdf8",
        borderWidth: 2,
        pointRadius: 0,
        pointHoverRadius: 4,
        pointHoverBackgroundColor: "#38bdf8",
        pointHoverBorderColor: "#0b101c",
        pointHoverBorderWidth: 2,
        tension: 0.38,
        fill: true,
        backgroundColor: (context) => {
          const { chart } = context;
          const { ctx, chartArea } = chart;
          if (!chartArea) return "rgba(56, 189, 248, 0.08)";
          const gradient = ctx.createLinearGradient(0, chartArea.top, 0, chartArea.bottom);
          gradient.addColorStop(0, "rgba(56, 189, 248, 0.14)");
          gradient.addColorStop(0.6, "rgba(56, 189, 248, 0.02)");
          gradient.addColorStop(1, "rgba(56, 189, 248, 0)");
          return gradient;
        },
      },
      {
        type: "bar",
        label: "Fraudes",
        data: points.map((point) => point.frauds),
        yAxisID: "y1",
        backgroundColor: "rgba(244, 63, 94, 0.55)",
        hoverBackgroundColor: "#f43f5e",
        borderColor: "transparent",
        borderWidth: 0,
        borderRadius: 2,
        maxBarThickness: 4,
        categoryPercentage: 0.6,
        barPercentage: 0.6,
      },
    ],
  };

  const options = {
    ...OPTIONS,
    scales: {
      ...OPTIONS.scales,
      y1: { ...OPTIONS.scales.y1, suggestedMax: Math.max(4, Math.ceil(maxFrauds * 2)) },
    },
  };

  return (
    <div className="chart-block">
      <div className="chart-legend">
        <span>
          <i className="legend-dot cyan" /> Transactions
        </span>
        <span>
          <i className="legend-dot rose" /> Fraudes bloquées
        </span>
      </div>
      <div className="chart-shell">
        {hasData ? (
          <Chart type="line" data={data} options={options} />
        ) : (
          <div className="chart-empty">
            <span className="chart-empty-icon">
              <IconRadio size={28} />
            </span>
            <strong>En attente du flux</strong>
            <p>Démarrez le simulateur ou injectez une transaction pour alimenter la courbe.</p>
          </div>
        )}
      </div>
    </div>
  );
}
