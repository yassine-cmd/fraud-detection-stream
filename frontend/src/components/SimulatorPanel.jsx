import { useEffect, useRef, useState } from "react";
import { api, fmtInt, fmtPct } from "../api.js";
import { IconAlert, IconPause, IconPlay, IconRadio, IconZap } from "../icons.jsx";

export default function SimulatorPanel({ status, onStatus, onNotify, live = false }) {
  const [rate, setRate] = useState(500);
  const [ratio, setRatio] = useState(2);
  const [busy, setBusy] = useState("");
  const [error, setError] = useState("");
  const [notice, setNotice] = useState("");
  const dirty = useRef(false);

  useEffect(() => {
    if (!status || dirty.current) return;
    if (status.rate_tx_per_sec) setRate(status.rate_tx_per_sec);
    if (status.fraud_ratio !== undefined && status.fraud_ratio !== null) {
      setRatio(Number((status.fraud_ratio * 100).toFixed(2)));
    }
  }, [status?.rate_tx_per_sec, status?.fraud_ratio]);

  const running = Boolean(status?.is_running ?? status?.running);

  function changeRate(value) {
    dirty.current = true;
    setRate(value);
  }

  function changeRatio(value) {
    dirty.current = true;
    setRatio(value);
  }

  function applyPreset(nextRate, nextRatio) {
    dirty.current = true;
    setRate(nextRate);
    setRatio(nextRatio);
  }

  async function control(action) {
    setBusy(action);
    setError("");
    setNotice("");
    try {
      const body = { action };
      if (action === "start") {
        body.rate_tx_per_sec = Math.max(1, Math.min(1000, Number(rate) || 500));
        body.fraud_ratio = Math.max(0, Math.min(1, (Number(ratio) || 0) / 100));
      }
      const response = await api("/stream/control", { method: "POST", body });
      onStatus?.(response);
      dirty.current = false;
      const message =
        action === "start"
          ? running
            ? `Débit appliqué : ${fmtInt(response.rate_tx_per_sec)} tx/s (ratio ${fmtPct(response.fraud_ratio, 2)}).`
            : `Flux démarré à ${fmtInt(response.rate_tx_per_sec)} tx/s (ratio ${fmtPct(response.fraud_ratio, 2)}).`
          : "Flux mis en pause.";
      setNotice(message);
      onNotify?.(message, "success");
    } catch (err) {
      setError(err.message);
      onNotify?.(err.message, "error");
    } finally {
      setBusy("");
    }
  }

  function handleStop() {
    if (!window.confirm("Voulez-vous vraiment arrêter le flux d'ingestion ?")) return;
    control("stop");
  }

  return (
    <section className={`card simulator-card ${live ? "simulator-live" : ""}`}>
      <div className="card-heading">
        <div>
          <span className="eyebrow">Contrôle</span>
          <h2>Simulateur de flux</h2>
        </div>
        <span className={`head-icon ${running ? "is-live" : ""}`}>
          <IconRadio size={18} />
        </span>
      </div>

      <div className={`sim-state ${running ? "is-running" : ""}`}>
        <span className="sim-pulse" />
        <div className="sim-state-copy">
          <strong>{running ? "Flux en cours" : "Flux à l'arrêt"}</strong>
          <span>
            {running
              ? `${fmtInt(status?.rate_tx_per_sec)} tx/s · ratio ${fmtPct(status?.fraud_ratio, 2)}`
              : "Démarrez le producteur Kafka pour alimenter Spark."}
          </span>
        </div>
        <span className={`sim-badge ${running ? "on" : ""}`}>{running ? "LIVE" : "IDLE"}</span>
      </div>

      <div className="control-field">
        <div className="control-label">
          <label htmlFor="sim-rate">Débit cible</label>
          <output htmlFor="sim-rate">{fmtInt(rate)} tx/s</output>
        </div>
        <input
          id="sim-rate"
          type="range"
          min="100"
          max="1000"
          step="50"
          value={rate}
          onChange={(event) => changeRate(event.target.value)}
        />
        <div className="range-scale">
          <span>100</span>
          <span>500</span>
          <span>1 000</span>
        </div>
      </div>

      <div className="control-field">
        <div className="control-label">
          <label htmlFor="sim-ratio">Ratio de fraudes</label>
          <output htmlFor="sim-ratio">{Number(ratio).toFixed(2)} %</output>
        </div>
        <input
          id="sim-ratio"
          type="range"
          min="0"
          max="10"
          step="0.05"
          value={ratio}
          onChange={(event) => changeRatio(event.target.value)}
        />
        <div className="range-scale">
          <span>0 %</span>
          <span>Démo 2 %</span>
          <span>10 %</span>
        </div>
      </div>

      <div className="sim-presets">
        <button type="button" onClick={() => applyPreset(500, 2)}>
          <IconZap size={13} /> Démo 2 %
        </button>
        <button type="button" onClick={() => applyPreset(500, 0.13)}>
          Naturel 0,13 %
        </button>
        <button type="button" onClick={() => applyPreset(1000, 2)}>
          Palier 1 000
        </button>
      </div>

      <div className="sim-actions">
        <button
          type="button"
          className="btn btn-primary"
          onClick={() => control("start")}
          disabled={Boolean(busy)}
        >
          {busy === "start" ? <span className="spinner" /> : running ? <IconZap size={15} /> : <IconPlay size={15} />}
          {running ? "Appliquer" : "Démarrer"}
        </button>
        <button
          type="button"
          className="btn btn-danger-ghost"
          onClick={handleStop}
          disabled={Boolean(busy) || !running}
        >
          {busy === "stop" ? <span className="spinner" /> : <IconPause size={15} />}
          Arrêter
        </button>
      </div>

      <div className="sim-metrics">
        <div>
          <span>Envoyées</span>
          <b>{fmtInt(status?.total_sent ?? status?.sent)}</b>
        </div>
        <div>
          <span>Acquittées</span>
          <b>{fmtInt(status?.total_delivered)}</b>
        </div>
        <div>
          <span>Erreurs</span>
          <b className={(status?.errors_count || 0) > 0 ? "text-rose" : ""}>{fmtInt(status?.errors_count)}</b>
        </div>
        <div>
          <span>Dataset</span>
          <b>{fmtInt(status?.dataset_rows)}</b>
        </div>
      </div>

      {status?.last_error && (
        <p className="inline-alert" role="alert">
          <IconAlert size={14} /> {status.last_error}
        </p>
      )}
      {error && (
        <p className="inline-alert" role="alert">
          <IconAlert size={14} /> {error}
        </p>
      )}
      {notice && !error && <p className="inline-success">{notice}</p>}
    </section>
  );
}
