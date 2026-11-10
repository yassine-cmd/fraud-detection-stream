import { Chart as ChartJS, CategoryScale, LinearScale, LineElement, PointElement, Filler, Legend, Tooltip } from "chart.js";
import { Line } from "react-chartjs-2";

ChartJS.register(CategoryScale, LinearScale, LineElement, PointElement, Filler, Legend, Tooltip);

const options = {
  animation: false, responsive: true, maintainAspectRatio: false,
  interaction: { mode: "index", intersect: false },
  scales: {
    y: { beginAtZero: true, title: { display: true, text: "tx / intervalle" } },
    y2: { beginAtZero: true, position: "right", grid: { drawOnChartArea: false },
          title: { display: true, text: "fraudes" }, ticks: { precision: 0 } },
  },
};

export default function TrafficChart({ points }) {
  const data = {
    labels: points.map((p) => p.t.slice(11, 19)),
    datasets: [
      { label: "Transactions", data: points.map((p) => p.tx), borderColor: "#1f5fd6", backgroundColor: "#1f5fd622",
        fill: true, tension: 0.25, pointRadius: 0, yAxisID: "y" },
      { label: "Fraudes", data: points.map((p) => p.frauds), borderColor: "#c62828", backgroundColor: "#c62828",
        tension: 0.25, pointRadius: 2, yAxisID: "y2" },
    ],
  };
  return <div className="chart-wrap"><Line data={data} options={options} /></div>;
}
