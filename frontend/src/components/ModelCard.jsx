import { fmtPct } from "../api.js";
import { IconCpu, IconSparkles } from "../icons.jsx";

const METRICS = [
  { key: "recall", label: "Rappel", target: "≥ 85 %" },
  { key: "precision", label: "Précision", target: "—" },
  { key: "f1_score", label: "F1-score", target: "≥ 80 %" },
  { key: "auc_pr", label: "AUC-PR", target: "≥ 85 %" },
];

export default function ModelCard({ model }) {
  const test = model?.test_metrics || {};
  const validation = model?.validation_metrics || {};
  const metrics = Object.keys(test).length ? test : validation;

  return (
    <section className="card model-card">
      <div className="card-heading">
        <div>
          <span className="eyebrow">Machine Learning</span>
          <h2>Performance du modèle</h2>
        </div>
        <span className="head-icon">
          <IconCpu size={18} />
        </span>
      </div>

      <div className="model-banner">
        <span className="model-banner-icon">
          <IconSparkles size={18} />
        </span>
        <div>
          <strong>{model?.model_version || "Modèle non chargé"}</strong>
          <span>
            {model?.model_type || "—"} · seuil {model ? fmtPct(model.threshold, 1) : "—"}
          </span>
        </div>
        <span className={`model-live ${model?.loaded ? "on" : ""}`}>{model?.loaded ? "READY" : "KO"}</span>
      </div>

      <div className="metric-list">
        {METRICS.map((metric) => {
          const value = Number(metrics[metric.key]);
          const valid = Number.isFinite(value) && value > 0;
          return (
            <div className="metric-row" key={metric.key}>
              <div className="metric-label">
                <span>{metric.label}</span>
                <small>{metric.target}</small>
              </div>
              <div className="metric-track">
                <span style={{ width: valid ? `${Math.min(100, value * 100)}%` : "0%" }} />
              </div>
              <b>{valid ? fmtPct(value, 1) : "—"}</b>
            </div>
          );
        })}
      </div>

      <div className="model-foot">
        <span>{metrics === test && Object.keys(test).length ? "Jeu de test temporel" : "Jeu de validation"}</span>
        <span>{model?.features?.length || 0} features</span>
      </div>
    </section>
  );
}
