import { useMemo, useState } from "react";
import { ArcElement, Chart as ChartJS, Tooltip } from "chart.js";
import { Doughnut } from "react-chartjs-2";
import { IconLayers } from "../icons.jsx";
import { fmtInt, fmtPct } from "../api.js";

ChartJS.register(ArcElement, Tooltip);

const TYPE_COLORS = {
  TRANSFER: "#f43f5e",
  CASH_OUT: "#fb923c",
  PAYMENT: "#38bdf8",
  CASH_IN: "#818cf8",
  DEBIT: "#64748b",
};
const FALLBACK_COLORS = ["#38bdf8", "#818cf8", "#fb923c", "#f43f5e", "#64748b"];

function colorForType(type, index) {
  return TYPE_COLORS[type] || FALLBACK_COLORS[index % FALLBACK_COLORS.length];
}

export default function TypeBreakdown({ rows = [] }) {
  const [hoveredIndex, setHoveredIndex] = useState(null);

  const total = rows.reduce((sum, row) => sum + (row.total || 0), 0);
  const hasData = total > 0;

  const data = useMemo(
    () => ({
      labels: rows.map((row) => row.type),
      datasets: [
        {
          data: rows.map((row) => row.total),
          backgroundColor: rows.map((row, index) => colorForType(row.type, index)),
          borderRadius: 4,
          borderWidth: 0,
          hoverBorderWidth: 0,
          hoverOffset: 6,
        },
      ],
    }),
    [rows]
  );

  const options = useMemo(
    () => ({
      responsive: true,
      maintainAspectRatio: false,
      cutout: "76%",
      spacing: 2,
      animation: { duration: 300 },
      plugins: {
        legend: { display: false },
        tooltip: { enabled: false }, // Disable floating canvas card to prevent collision with center text
      },
      onHover: (event, elements) => {
        if (elements && elements.length > 0) {
          setHoveredIndex(elements[0].index);
        } else {
          setHoveredIndex(null);
        }
      },
    }),
    []
  );

  const activeItem = hoveredIndex !== null && rows[hoveredIndex] ? rows[hoveredIndex] : null;
  const activePct = activeItem && total > 0 ? (activeItem.total / total) * 100 : 0;

  return (
    <div className="card breakdown-card">
      <div className="card-heading">
        <div>
          <span className="eyebrow">Répartition</span>
          <h2>Types de transaction</h2>
        </div>
        <span className="head-icon">
          <IconLayers size={18} />
        </span>
      </div>

      {!hasData ? (
        <div className="mini-empty">Aucune transaction dans la fenêtre.</div>
      ) : (
        <div className="breakdown-body">
          <div className="donut-wrap">
            <Doughnut data={data} options={options} />
            <div className={`donut-center ${activeItem ? "is-hovered" : ""}`}>
              {activeItem ? (
                <>
                  <strong style={{ color: colorForType(activeItem.type, hoveredIndex) }}>
                    {fmtInt(activeItem.total)}
                  </strong>
                  <span className="donut-hover-badge">
                    {activeItem.type} · {activePct.toFixed(1).replace(".", ",")} %
                  </span>
                </>
              ) : (
                <>
                  <strong>{fmtInt(total)}</strong>
                  <span>transactions</span>
                </>
              )}
            </div>
          </div>
          <ul className="breakdown-list">
            {rows.slice(0, 5).map((row, index) => (
              <li
                key={row.type}
                className={hoveredIndex === index ? "is-hovered" : ""}
                onMouseEnter={() => setHoveredIndex(index)}
                onMouseLeave={() => setHoveredIndex(null)}
              >
                <span className="legend-dot" style={{ background: colorForType(row.type, index) }} />
                <span className="breakdown-type">{row.type}</span>
                <span className="breakdown-count">{fmtInt(row.total)}</span>
                <span className={`breakdown-rate ${row.frauds ? "has-fraud" : ""}`}>
                  {fmtPct(row.fraud_rate, 2)}
                </span>
              </li>
            ))}
          </ul>
        </div>
      )}
      <div className="breakdown-foot-note">
        <span>Domaine PaySim : seules les opérations TRANSFER et CASH_OUT font l'objet de fraudes.</span>
      </div>
    </div>
  );
}

