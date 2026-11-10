import { useState } from "react";
import { api, fmtInt } from "../api.js";

export default function SimulatorPanel({ status, onStatus }) {
  const [rate, setRate] = useState(500);
  const [ratio, setRatio] = useState(0.02);
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState("");

  async function control(action) {
    const body = { action };
    if (action === "start") { body.rate_tx_per_sec = parseInt(rate, 10); body.fraud_ratio = parseFloat(ratio); }
    setBusy(true); setErr("");
    try { onStatus(await api("/stream/control", { method: "POST", body })); }
    catch (e) { setErr("Contrôle du simulateur : " + e.message); }
    finally { setBusy(false); }
  }

  const running = status?.running;
  return (
    <div className="box">
      <h2>Simulateur</h2>
      <div className={"pill " + (running ? "pill-on" : "pill-off")}>
        {running ? `actif · ${status.rate_tx_per_sec} tx/s · ratio ${status.fraud_ratio}` : "arrêté"}
      </div>
      <div className="row"><label htmlFor="rate">Débit (tx/s)</label>
        <input id="rate" type="number" min="1" max="1000" value={rate} onChange={(e) => setRate(e.target.value)} /></div>
      <div className="row"><label htmlFor="ratio">Ratio de fraudes</label>
        <input id="ratio" type="number" min="0" max="1" step="0.001" value={ratio} onChange={(e) => setRatio(e.target.value)} /></div>
      <div className="btns">
        <button className="primary" disabled={busy} onClick={() => control("start")}>Démarrer</button>
        <button className="danger" disabled={busy} onClick={() => control("stop")}>Arrêter</button>
      </div>
      <p className="hint">Mode démo : 0,02 rend les alertes visibles (naturel : 0,0013).</p>
      {status?.sent != null && <p className="hint">{fmtInt(status.sent)} messages produits</p>}
      {err && <p className="err" role="alert">{err}</p>}
    </div>
  );
}
