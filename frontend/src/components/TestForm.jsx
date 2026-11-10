import { useState } from "react";
import { api } from "../api.js";

const PRESETS = {
  fraud: { step: 650, type: "TRANSFER", amount: 300000, oldbalanceOrg: 300000, newbalanceOrig: 0, oldbalanceDest: 0, newbalanceDest: 300000 },
  ok: { step: 650, type: "PAYMENT", amount: 85.5, oldbalanceOrg: 5000, newbalanceOrig: 4914.5, oldbalanceDest: 0, newbalanceDest: 0 },
};
const FIELDS = [
  ["step", "Step (heure)", 1, 1], ["amount", "Montant", 0, "any"], ["oldbalanceOrg", "Solde émetteur avant", 0, "any"],
  ["newbalanceOrig", "Solde émetteur après", 0, "any"], ["oldbalanceDest", "Solde destinataire avant", 0, "any"],
  ["newbalanceDest", "Solde destinataire après", 0, "any"],
];
const TYPES = ["TRANSFER", "CASH_OUT", "PAYMENT", "DEBIT", "CASH_IN"];

export default function TestForm() {
  const [f, setF] = useState(PRESETS.fraud);
  const [res, setRes] = useState(null);
  const [msg, setMsg] = useState({ text: "", ok: false });
  const set = (k, v) => { setF({ ...f, [k]: v }); setMsg({ text: "", ok: false }); };

  const payload = () => {
    const o = { type: f.type };
    for (const [k] of FIELDS) o[k] = Number(f[k]);
    o.step = Math.trunc(o.step);
    return o;
  };

  async function submit(e) {
    e.preventDefault(); setMsg({ text: "", ok: false });
    const t0 = performance.now();
    try { setRes({ ...(await api("/predict", { method: "POST", body: payload() })), rtt: performance.now() - t0 }); }
    catch (err) { setMsg({ text: (err.status === 422 ? "Données invalides — " : "") + err.message, ok: false }); }
  }
  async function queue() {
    const form = document.getElementById("form");
    if (!form.reportValidity()) return;
    try {
      const r = await api("/transactions", { method: "POST", body: payload() });
      setMsg({ text: `Transaction ${r.transaction_id} publiée dans Kafka (traitée par Spark, visible dans le tableau de bord).`, ok: true });
    } catch (err) { setMsg({ text: err.message, ok: false }); }
  }

  return (
    <section className="panel">
      <div className="grid2 even">
        <form id="form" className="box" onSubmit={submit}>
          <h2>Transaction à évaluer</h2>
          <div className="presets">
            <button type="button" onClick={() => setF(PRESETS.fraud)}>Exemple : fraude (vide le compte)</button>
            <button type="button" onClick={() => setF(PRESETS.ok)}>Exemple : paiement normal</button>
          </div>
          <div className="row"><label htmlFor="f-type">Type</label>
            <select id="f-type" value={f.type} onChange={(e) => set("type", e.target.value)}>
              {TYPES.map((t) => <option key={t}>{t}</option>)}
            </select></div>
          {FIELDS.map(([k, label, min, step]) => (
            <div className="row" key={k}><label htmlFor={"f-" + k}>{label}</label>
              <input id={"f-" + k} type="number" required min={min} step={step} value={f[k]} onChange={(e) => set(k, e.target.value)} /></div>
          ))}
          <div className="btns">
            <button type="submit" className="primary">Évaluer (sync)</button>
            <button type="button" onClick={queue}>Envoyer dans Kafka (async)</button>
          </div>
          <p className="err" role="alert" style={msg.ok ? { color: "var(--ok)" } : undefined}>{msg.text}</p>
        </form>
        <Result r={res} />
      </div>
    </section>
  );
}

function Result({ r }) {
  return (
    <div className="box" aria-live="polite">
      <h2>Résultat</h2>
      {!r ? <div className="empty">Soumettez une transaction.</div> : (
        <>
          <div className={"decision " + r.decision}>{r.decision}</div>
          <div className="gauge">
            <div id="gauge-fill" style={{ left: `calc(${(r.probability * 100).toFixed(1)}% - 2px)` }} />
            <div id="gauge-thr" style={{ left: r.threshold * 100 + "%" }} />
          </div>
          <div className="gauge-labels"><span>0</span><span>{r.probability.toFixed(3)}</span><span>1</span></div>
          <dl>
            <dt>Probabilité</dt><dd>{(r.probability * 100).toFixed(2)} %</dd>
            <dt>Seuil</dt><dd>{r.threshold}</dd>
            <dt>Latence API</dt><dd>{r.latency_ms.toFixed(1)} ms</dd>
            <dt>Latence aller-retour</dt><dd>{r.rtt.toFixed(0)} ms</dd>
            <dt>Version du modèle</dt><dd>{r.model_version}</dd>
            <dt>Transaction</dt><dd>{r.transaction_id}</dd>
          </dl>
        </>
      )}
    </div>
  );
}
