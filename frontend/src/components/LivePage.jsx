import { fmtInt, fmtPct } from "../api.js";
import { fmtLatency } from "../utils/formatters.js";
import {
  IconActivity,
  IconAlert,
  IconDatabase,
  IconRadio,
  IconServer,
  IconWaves,
  IconZap,
} from "../icons.jsx";
import SimulatorPanel from "./SimulatorPanel.jsx";
import TrafficChart from "./TrafficChart.jsx";

export default function LivePage({
  data,
  health,
  healthError,
  model,
  windowRange,
  onWindowRange,
  onNotify,
}) {
  const { points, stream, latency, setStream, streamError, error } = data;

  const reference = points.length > 1 ? points[points.length - 2] : points[0];
  const throughput = reference ? Math.round(reference.tx / 10) : 0;
  const windowTx = points.reduce((sum, point) => sum + point.tx, 0);
  const windowFrauds = points.reduce((sum, point) => sum + point.frauds, 0);
  const deliveryRate = stream?.total_sent ? (stream.total_delivered / stream.total_sent) : 1;

  return (
    <div className="page-stack">
      {(error || streamError) && (
        <div className="global-alert" role="alert">
          <IconAlert size={16} />
          <span>{error || streamError}</span>
        </div>
      )}

      <div className="page-head">
        <div>
          <span className="eyebrow">
            <i className={`live-dot ${stream?.is_running ? "" : "idle"}`} />
            Pipeline distribué
          </span>
          <h2>Flux temps réel & Télémétrie</h2>
          <p>Supervision du cluster Kafka-Spark et régulation du débit d'ingestion.</p>
        </div>
        <div className="live-controls">
          <span className={`live-state ${stream?.is_running ? "on" : ""}`}>
            <IconRadio size={15} /> {stream?.is_running ? "Diffusion en cours" : "Diffusion arrêtée"}
          </span>
          <div className="segmented" role="group" aria-label="Fenêtre temporelle">
            {[
              ["5m", "5 min"],
              ["15m", "15 min"],
              ["1h", "1 h"],
            ].map(([value, label]) => (
              <button
                key={value}
                type="button"
                className={windowRange === value ? "active" : ""}
                onClick={() => onWindowRange(value)}
              >
                {label}
              </button>
            ))}
          </div>
        </div>
      </div>

      {/* 1. Kafka Transport Telemetry Strip */}
      <div className="stat-strip live-strip">
        <div className="stat-tile">
          <span className="stat-icon cyan">
            <IconZap size={18} />
          </span>
          <div>
            <span>Messages envoyés</span>
            <strong>{fmtInt(stream?.total_sent)}</strong>
            <small>topic transactions_stream</small>
          </div>
        </div>
        <div className="stat-tile">
          <span className="stat-icon emerald">
            <IconActivity size={18} />
          </span>
          <div>
            <span>Messages acquittés</span>
            <strong>{fmtInt(stream?.total_delivered)}</strong>
            <small>{fmtPct(deliveryRate, 2)} taux de livraison</small>
          </div>
        </div>
        <div className="stat-tile">
          <span className="stat-icon rose">
            <IconAlert size={18} />
          </span>
          <div>
            <span>Erreurs broker Kafka</span>
            <strong>{fmtInt(stream?.errors_count)}</strong>
            <small>{stream?.errors_count === 0 ? "Transport nominal" : "Anomalies détectées"}</small>
          </div>
        </div>
        <div className="stat-tile">
          <span className="stat-icon violet">
            <IconDatabase size={18} />
          </span>
          <div>
            <span>Dataset source PaySim</span>
            <strong>{fmtInt(stream?.dataset_rows)}</strong>
            <small>transactions prêtes</small>
          </div>
        </div>
      </div>

      {/* 2. Pipeline Processing & Activity Chart */}
      <section className="card chart-card">
        <div className="card-heading chart-heading">
          <div>
            <span className="eyebrow">Throughput & Scoring</span>
            <h2>Activité du cluster Spark</h2>
          </div>
          <span className="live-pill">
            <i /> Live · 3 s
          </span>
        </div>
        <TrafficChart points={points} />
        <div className="chart-stats">
          <div>
            <span>Débit fenêtre</span>
            <strong>{fmtInt(throughput)} tx/s</strong>
          </div>
          <div>
            <span>Transactions traitées</span>
            <strong>{fmtInt(windowTx)}</strong>
          </div>
          <div>
            <span>Fraudes bloquées</span>
            <strong className="text-rose">{fmtInt(windowFrauds)}</strong>
          </div>
          <div>
            <span>Taux de détection</span>
            <strong>{fmtPct(windowTx ? windowFrauds / windowTx : 0, 3)}</strong>
          </div>
          <div className="chart-latency">
            <span>P95 bout-en-bout</span>
            <strong>{latency?.p95_ms != null ? fmtLatency(latency.p95_ms) : "—"}</strong>
          </div>
        </div>
      </section>

      {/* 3. Operational Command & Latency Topology Grid */}
      <div className="live-grid">
        <SimulatorPanel status={stream} onStatus={setStream} onNotify={onNotify} live />
        <LatencyCard latency={latency} />
        <PipelineCard health={health} healthError={healthError} stream={stream} />
      </div>
    </div>
  );
}

function LatencyCard({ latency }) {
  const p95 = Number(latency?.p95_ms) || 0;
  const target = 3000;
  const ratio = Math.min(1, p95 / target);
  const isBacklog = p95 > 60000;
  const p95Display = latency?.p95_ms != null ? fmtLatency(latency.p95_ms) : "—";

  return (
    <section className="card latency-card">
      <div className="card-heading">
        <div>
          <span className="eyebrow">SNF3</span>
          <h2>Latence bout-en-bout</h2>
        </div>
        <span className="head-icon">
          <IconActivity size={18} />
        </span>
      </div>
      <div className="latency-hero">
        <strong>{p95Display}</strong>
        <span>{isBacklog ? "Retard backlog" : "P95"}</span>
        <small>{isBacklog ? "Décalage d'ingestion (file Kafka)" : "objectif < 3 000 ms"}</small>
      </div>
      <div className={`latency-track ${ratio > 0.8 ? "danger" : ratio > 0.5 ? "warn" : ""}`}>
        <span style={{ width: `${Math.max(2, ratio * 100)}%` }} />
      </div>
      <div className="latency-grid">
        <div>
          <span>Moyenne</span>
          <b>{latency?.avg_ms != null ? fmtLatency(latency.avg_ms) : "—"}</b>
        </div>
        <div>
          <span>P50</span>
          <b>{latency?.p50_ms != null ? fmtLatency(latency.p50_ms) : "—"}</b>
        </div>
        <div>
          <span>P99</span>
          <b>{latency?.p99_ms != null ? fmtLatency(latency.p99_ms) : "—"}</b>
        </div>
        <div>
          <span>Échantillons</span>
          <b>{fmtInt(latency?.count)}</b>
        </div>
      </div>
    </section>
  );
}

function PipelineCard({ health, healthError, stream }) {
  const stages = [
    {
      name: "Kafka",
      detail: health?.mode === "mock" ? "mode simulé" : health?.kafka === "up" ? "broker connecté" : "indisponible",
      tone: health?.mode === "mock" ? "mock" : health?.kafka === "up" ? "ok" : "down",
      icon: IconWaves,
    },
    {
      name: "Spark",
      detail: stream?.is_running ? "scoring en continu" : "en attente de flux",
      tone: stream?.is_running ? "ok" : "idle",
      icon: IconZap,
    },
    {
      name: "MongoDB",
      detail: health?.mode === "mock" ? "mode simulé" : health?.mongodb === "up" ? "persistance active" : "indisponible",
      tone: health?.mode === "mock" ? "mock" : health?.mongodb === "up" ? "ok" : "down",
      icon: IconDatabase,
    },
    {
      name: "FastAPI",
      detail: healthError ? "hors ligne" : health?.status || "vérification",
      tone: healthError ? "down" : "ok",
      icon: IconServer,
    },
  ];

  return (
    <section className="card pipeline-card">
      <div className="card-heading">
        <div>
          <span className="eyebrow">Architecture</span>
          <h2>Chaîne de traitement</h2>
        </div>
        <span className="head-icon">
          <IconServer size={18} />
        </span>
      </div>
      <div className="pipeline-flow">
        {stages.map((stage, index) => {
          const Icon = stage.icon;
          return (
            <div className="pipeline-stage" key={stage.name}>
              <span className={`stage-icon ${stage.tone}`}>
                <Icon size={18} />
              </span>
              <div>
                <strong>{stage.name}</strong>
                <small>{stage.detail}</small>
              </div>
              {index < stages.length - 1 && <span className={`stage-link ${stage.tone}`} />}
            </div>
          );
        })}
      </div>
    </section>
  );
}
