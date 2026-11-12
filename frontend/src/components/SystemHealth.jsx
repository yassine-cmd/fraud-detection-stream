import { fmtDuration, fmtPct } from "../api.js";
import { IconAlert, IconCheck, IconServer } from "../icons.jsx";

function toneFor(value) {
  if (value === true || value === "up") return "ok";
  if (value === "mock") return "mock";
  if (value === false || value === "down") return "down";
  return "idle";
}

export default function SystemHealth({ health, healthError, stream, streamError }) {
  const apiTone = healthError ? "down" : health ? (health.status === "healthy" ? "ok" : "warn") : "idle";
  const modelTone = healthError ? "idle" : health?.model_loaded ? "ok" : "down";
  const streamTone = streamError ? "down" : stream?.is_running ? "ok" : "idle";

  const rows = [
    {
      label: "FastAPI",
      detail: healthError
        ? "Injoignable"
        : health
          ? `Uptime ${fmtDuration(health.uptime_s)}`
          : "Vérification…",
      tone: apiTone,
      value: healthError ? "DOWN" : health ? "UP" : "…",
    },
    {
      label: "Apache Kafka",
      detail: health?.mode === "mock" ? "Mode simulé" : health ? `Broker ${health.kafka}` : "—",
      tone: toneFor(health?.kafka ?? (healthError ? "down" : undefined)),
      value: health?.mode === "mock" ? "MOCK" : (health?.kafka || "—").toUpperCase(),
    },
    {
      label: "MongoDB",
      detail: health?.mode === "mock" ? "Mode simulé" : health ? `Base ${health.mongodb}` : "—",
      tone: toneFor(health?.mongodb ?? (healthError ? "down" : undefined)),
      value: health?.mode === "mock" ? "MOCK" : (health?.mongodb || "—").toUpperCase(),
    },
    {
      label: "Modèle ML",
      detail: health?.model_loaded
        ? `${health.model_version} · τ* ${fmtPct(health.threshold, 1)}`
        : "Non chargé",
      tone: modelTone,
      value: health?.model_loaded ? "READY" : "KO",
    },
    {
      label: "Simulateur",
      detail: streamError || (stream?.is_running ? `${stream.rate_tx_per_sec || 500} tx/s actif` : "En attente"),
      tone: streamTone,
      value: stream?.is_running ? "LIVE" : "IDLE",
    },
  ];

  const isDegraded = health?.status === "degraded" || healthError || streamError;

  return (
    <section className="card telemetry-strip" aria-label="Observabilité infrastructure">
      <div className="telemetry-lead">
        <span className="telemetry-lead-icon">
          <IconServer size={15} />
        </span>
        <div className="telemetry-lead-copy">
          <strong>Observabilité système</strong>
          <span>{isDegraded ? "Services dégradés" : "5 services opérationnels"}</span>
        </div>
      </div>

      <div className="telemetry-pills">
        {rows.map((row) => (
          <div key={row.label} className={`telemetry-pill tone-${row.tone}`}>
            <span className={`health-dot ${row.tone}`} />
            <div className="telemetry-pill-info">
              <span className="telemetry-pill-title">{row.label}</span>
              <span className="telemetry-pill-meta">{row.detail}</span>
            </div>
            <span className={`telemetry-pill-badge ${row.tone}`}>{row.value}</span>
          </div>
        ))}
      </div>
    </section>
  );
}

