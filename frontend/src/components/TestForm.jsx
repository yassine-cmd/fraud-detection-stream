import { useState } from "react";
import { api, fmtPct } from "../api.js";
import {
  IconAlert,
  IconCheck,
  IconClock,
  IconFlask,
  IconShield,
  IconTerminal,
  IconZap,
} from "../icons.jsx";

const TYPES = ["TRANSFER", "CASH_OUT", "PAYMENT", "DEBIT", "CASH_IN"];

const PRESETS = {
  fraud: {
    badge: "TRANSFER",
    label: "Fraude typique",
    hint: "Virement vidant le compte sans créditer le destinataire",
    values: {
      step: 650,
      type: "TRANSFER",
      amount: 300000,
      oldbalanceOrg: 300000,
      newbalanceOrig: 0,
      oldbalanceDest: 0,
      newbalanceDest: 0,
      nameOrig: "C123456789",
      nameDest: "C987654321",
    },
  },
  normal: {
    badge: "PAYMENT",
    label: "Paiement nominal",
    hint: "Transaction marchande légitime avec solde cohérent",
    values: {
      step: 650,
      type: "PAYMENT",
      amount: 85.5,
      oldbalanceOrg: 5000,
      newbalanceOrig: 4914.5,
      oldbalanceDest: 0,
      newbalanceDest: 0,
      nameOrig: "C123456789",
      nameDest: "M987654321",
    },
  },
  cashout: {
    badge: "CASH_OUT",
    label: "Retrait suspect",
    hint: "Retrait massif immédiat vidant intégralement le compte",
    values: {
      step: 651,
      type: "CASH_OUT",
      amount: 450000,
      oldbalanceOrg: 450000,
      newbalanceOrig: 0,
      oldbalanceDest: 12000,
      newbalanceDest: 462000,
      nameOrig: "C555000111",
      nameDest: "C222333444",
    },
  },
};

function toForm(values) {
  return Object.fromEntries(Object.entries(values).map(([key, value]) => [key, String(value)]));
}

export default function TestForm({ onNotify, model }) {
  const [activePreset, setActivePreset] = useState("fraud");
  const [form, setForm] = useState(() => toForm(PRESETS.fraud.values));
  const [result, setResult] = useState(null);
  const [isDirty, setIsDirty] = useState(false);
  const [loading, setLoading] = useState(false);
  const [queueing, setQueueing] = useState(false);
  const [persist, setPersist] = useState(false);
  const [error, setError] = useState("");
  const [queued, setQueued] = useState(null);

  function setField(key, value) {
    setForm((current) => ({ ...current, [key]: value }));
    setActivePreset(null);
    setError("");
    setIsDirty(true);
  }

  function applyPreset(key) {
    setActivePreset(key);
    setForm(toForm(PRESETS[key].values));
    setResult(null);
    setError("");
    setQueued(null);
    setIsDirty(false);
  }

  function buildPayload() {
    return {
      step: Math.max(1, Math.trunc(Number(form.step) || 1)),
      type: form.type,
      amount: Number(form.amount),
      oldbalanceOrg: Number(form.oldbalanceOrg),
      newbalanceOrig: Number(form.newbalanceOrig),
      oldbalanceDest: Number(form.oldbalanceDest),
      newbalanceDest: Number(form.newbalanceDest),
      nameOrig: form.nameOrig || undefined,
      nameDest: form.nameDest || undefined,
    };
  }

  async function submit(event) {
    if (event?.preventDefault) event.preventDefault();
    setError("");
    setQueued(null);
    setLoading(true);
    const started = performance.now();
    try {
      const response = await api(`/predict?persist=${persist}`, {
        method: "POST",
        body: buildPayload(),
      });
      setResult({ ...response, rtt: performance.now() - started });
      setIsDirty(false);
      onNotify?.(
        response.decision === "BLOCKED"
          ? "Transaction bloquée par le modèle."
          : "Transaction autorisée par le modèle.",
        response.decision === "BLOCKED" ? "warning" : "success"
      );
    } catch (err) {
      setError(err.message);
      onNotify?.(err.message, "error");
    } finally {
      setLoading(false);
    }
  }

  async function inject() {
    setError("");
    setQueued(null);
    setQueueing(true);
    try {
      const response = await api("/transactions", { method: "POST", body: buildPayload() });
      setQueued(response.transaction_id);
      onNotify?.("Transaction publiée dans Kafka, en attente de Spark.", "success");
    } catch (err) {
      setError(err.message);
      onNotify?.(err.message, "error");
    } finally {
      setQueueing(false);
    }
  }

  const isOverdraft =
    form.type === "TRANSFER" && Number(form.amount) > Number(form.oldbalanceOrg);

  return (
    <div className="page-stack">
      <div className="test-layout">
        <form
          className="card test-form"
          onSubmit={submit}
          onKeyDown={(e) => {
            if ((e.ctrlKey || e.metaKey) && e.key === "Enter") {
              e.preventDefault();
              submit(e);
            }
          }}
        >
            <div className="card-heading">
              <div>
                <span className="eyebrow">Inférence synchrone</span>
                <h2>Transaction à évaluer</h2>
              </div>
              <span className="head-icon">
                <IconFlask size={18} />
              </span>
            </div>

            <div className="preset-row">
              {Object.entries(PRESETS).map(([key, preset]) => (
                <button
                  key={key}
                  type="button"
                  className={`preset-btn ${key === "fraud" ? "preset-danger" : ""} ${
                    activePreset === key ? "is-active" : ""
                  }`}
                  onClick={() => applyPreset(key)}
                >
                  <div className="preset-head">
                    <span className="preset-tag">{preset.badge}</span>
                    <span className="preset-label">{preset.label}</span>
                  </div>
                  <p className="preset-hint">{preset.hint}</p>
                </button>
              ))}
            </div>

            <div className="form-section">
              <div className="form-section-title">
                <strong>Paramètres de la transaction</strong>
                <small>Type, horodatage PaySim et montant</small>
              </div>
              <div className="field-grid">
                <label className="field" htmlFor="tx-type">
                  <span>Type d'opération</span>
                  <select
                    id="tx-type"
                    name="type"
                    aria-label="Type d'opération"
                    value={form.type}
                    onChange={(event) => setField("type", event.target.value)}
                  >
                    {TYPES.map((type) => (
                      <option key={type} value={type}>
                        {type}
                      </option>
                    ))}
                  </select>
                </label>
                <label className="field" htmlFor="tx-step">
                  <span>Step (heure PaySim)</span>
                  <input
                    id="tx-step"
                    name="step"
                    aria-label="Step (heure PaySim)"
                    type="number"
                    min="1"
                    step="1"
                    required
                    value={form.step}
                    onChange={(event) => setField("step", event.target.value)}
                  />
                </label>
                <label className="field field-span" htmlFor="tx-amount">
                  <span>Montant à transférer</span>
                  <div className="input-with-unit">
                    <input
                      id="tx-amount"
                      name="amount"
                      aria-label="Montant à transférer"
                      type="number"
                      min="0"
                      step="0.01"
                      required
                      value={form.amount}
                      onChange={(event) => setField("amount", event.target.value)}
                    />
                    <i>$</i>
                  </div>
                </label>
              </div>

              {isOverdraft && (
                <div className="validation-warning-pill" role="alert">
                  <IconAlert size={14} />
                  <span>
                    Dépassement du solde émetteur disponible (Solde :{" "}
                    {Number(form.oldbalanceOrg).toLocaleString("fr-FR")} $)
                  </span>
                </div>
              )}
            </div>

            <div className="form-section">
              <div className="form-section-title">
                <strong>Compte émetteur (Origine)</strong>
                <small>
                  {Number(form.newbalanceOrig) - Number(form.oldbalanceOrg) === 0
                    ? "Solde inchangé"
                    : `Variation nette : ${(
                        Number(form.newbalanceOrig) - Number(form.oldbalanceOrg)
                      ).toLocaleString("fr-FR")} $`}
                </small>
              </div>
              <div className="field-grid">
                <label className="field" htmlFor="tx-oldbalanceOrg">
                  <span>Solde initial</span>
                  <div className="input-with-unit">
                    <input
                      id="tx-oldbalanceOrg"
                      name="oldbalanceOrg"
                      aria-label="Solde initial compte émetteur"
                      type="number"
                      min="0"
                      step="0.01"
                      required
                      value={form.oldbalanceOrg}
                      onChange={(event) => setField("oldbalanceOrg", event.target.value)}
                    />
                    <i>$</i>
                  </div>
                </label>
                <label className="field" htmlFor="tx-newbalanceOrig">
                  <span>Solde final</span>
                  <div className="input-with-unit">
                    <input
                      id="tx-newbalanceOrig"
                      name="newbalanceOrig"
                      aria-label="Solde final compte émetteur"
                      type="number"
                      min="0"
                      step="0.01"
                      required
                      value={form.newbalanceOrig}
                      onChange={(event) => setField("newbalanceOrig", event.target.value)}
                    />
                    <i>$</i>
                  </div>
                </label>
              </div>
            </div>

            <div className="form-section">
              <div className="form-section-title">
                <strong>Compte destinataire (Bénéficiaire)</strong>
                <small>
                  {Number(form.newbalanceDest) - Number(form.oldbalanceDest) === 0
                    ? form.type === "PAYMENT"
                      ? "Solde marchand (non suivi)"
                      : "Solde inchangé (suspect sur virement)"
                    : `Variation nette : +${(
                        Number(form.newbalanceDest) - Number(form.oldbalanceDest)
                      ).toLocaleString("fr-FR")} $`}
                </small>
              </div>
              <div className="field-grid">
                <label className="field" htmlFor="tx-oldbalanceDest">
                  <span>Solde initial</span>
                  <div className="input-with-unit">
                    <input
                      id="tx-oldbalanceDest"
                      name="oldbalanceDest"
                      aria-label="Solde initial compte bénéficiaire"
                      type="number"
                      min="0"
                      step="0.01"
                      required
                      value={form.oldbalanceDest}
                      onChange={(event) => setField("oldbalanceDest", event.target.value)}
                    />
                    <i>$</i>
                  </div>
                </label>
                <label className="field" htmlFor="tx-newbalanceDest">
                  <span>Solde final</span>
                  <div className="input-with-unit">
                    <input
                      id="tx-newbalanceDest"
                      name="newbalanceDest"
                      aria-label="Solde final compte bénéficiaire"
                      type="number"
                      min="0"
                      step="0.01"
                      required
                      value={form.newbalanceDest}
                      onChange={(event) => setField("newbalanceDest", event.target.value)}
                    />
                    <i>$</i>
                  </div>
                </label>
              </div>
            </div>

            <details className="advanced-block">
              <summary>Identifiants optionnels (non utilisés par le modèle)</summary>
              <div className="field-grid">
                <label className="field" htmlFor="tx-nameOrig">
                  <span>nameOrig</span>
                  <input
                    id="tx-nameOrig"
                    name="nameOrig"
                    aria-label="Identifiant compte émetteur (nameOrig)"
                    value={form.nameOrig}
                    onChange={(event) => setField("nameOrig", event.target.value)}
                  />
                </label>
                <label className="field" htmlFor="tx-nameDest">
                  <span>nameDest</span>
                  <input
                    id="tx-nameDest"
                    name="nameDest"
                    aria-label="Identifiant compte bénéficiaire (nameDest)"
                    value={form.nameDest}
                    onChange={(event) => setField("nameDest", event.target.value)}
                  />
                </label>
              </div>
            </details>

            <label className="persist-toggle" htmlFor="tx-persist">
              <input
                id="tx-persist"
                name="persist"
                aria-label="Persister le résultat dans MongoDB"
                type="checkbox"
                checked={persist}
                onChange={(event) => setPersist(event.target.checked)}
              />
              <div className="persist-copy">
                <span className="persist-title">Persister le résultat</span>
                <span className="persist-desc">Écrit la prédiction dans MongoDB (source : api)</span>
              </div>
            </label>

            {error && (
              <p className="inline-alert" role="alert">
                <IconAlert size={14} /> {error}
              </p>
            )}
            {queued && (
              <p className="inline-success">
                <IconCheck size={14} /> Publiée dans Kafka : <code>{queued}</code>
              </p>
            )}

            <div className="form-actions">
              <button
                type="submit"
                className="btn btn-primary btn-lg"
                disabled={loading || queueing}
                title="Raccourci : Ctrl + Entrée"
              >
                {loading ? <span className="spinner" /> : <IconZap size={17} />}
                {loading ? "Évaluation…" : "Évaluer maintenant"}
                <span className="shortcut-badge">Ctrl+↵</span>
              </button>
              <button
                type="button"
                className="btn btn-ghost"
                onClick={inject}
                disabled={loading || queueing}
              >
                {queueing ? <span className="spinner" /> : <IconTerminal size={16} />}
                Envoyer dans Kafka
              </button>
            </div>
            <p className="form-foot">
              <IconClock size={13} /> Le modèle {model?.model_version || "—"} répond en mémoire, sans
              passer par Kafka.
            </p>
          </form>

          <div className="test-result-column">
            <ResultPanel result={result} loading={loading} model={model} form={form} isDirty={isDirty} />
          </div>
        </div>
    </div>
  );
}

function ResultPanel({ result, loading, model, form, isDirty }) {
  if (loading) {
    return (
      <section className="card result-panel">
        <div className="result-loading">
          <span className="scanner" />
          <strong>Évaluation en cours…</strong>
          <p>Application du pipeline scikit-learn + inférence XGBoost.</p>
        </div>
      </section>
    );
  }

  if (!result) {
    return (
      <section className="card result-panel result-idle">
        <div className="card-heading">
          <div>
            <span className="eyebrow">Moteur décisionnel</span>
            <h2>Inspecteur de risque</h2>
          </div>
          <span className="head-icon">
            <IconShield size={18} />
          </span>
        </div>
        <p className="idle-instruction">
          Sélectionnez un preset ou modifiez les attributs pour déclencher le scoring en temps réel.
        </p>
        <div className="engine-meta-grid">
          <div className="engine-meta-item">
            <span>Modèle actif</span>
            <strong>{model?.model_version || "v1.0.0-xgb"}</strong>
          </div>
          <div className="engine-meta-item">
            <span>Seuil d'alerte τ*</span>
            <strong>{model ? fmtPct(model.threshold, 1) : "94.5 %"}</strong>
          </div>
          <div className="engine-meta-item">
            <span>Algorithme</span>
            <strong>{model?.model_type || "XGBoost"}</strong>
          </div>
          <div className="engine-meta-item">
            <span>Objectif P95</span>
            <strong>&lt; 200 ms</strong>
          </div>
        </div>
      </section>
    );
  }

  const blocked = result.decision === "BLOCKED";
  const probability = Number(result.probability) || 0;
  const threshold = Number(result.threshold) || 0.5;
  const { rtt, ...payload } = result;

  const origBefore = Number(form?.oldbalanceOrg) || 0;
  const origAfter = Number(form?.newbalanceOrig) || 0;
  const origDelta = origAfter - origBefore;

  const destBefore = Number(form?.oldbalanceDest) || 0;
  const destAfter = Number(form?.newbalanceDest) || 0;
  const destDelta = destAfter - destBefore;
  const isPayment = form?.type === "PAYMENT";
  const isDestSuspect = !isPayment && destDelta === 0;

  return (
    <section
      className={`card result-panel ${blocked ? "is-blocked" : "is-allowed"}`}
      aria-live="polite"
    >
      {isDirty && (
        <div className="stale-notice-banner" role="status">
          <IconAlert size={16} />
          <span>Paramètres modifiés depuis le dernier scoring. Cliquez sur "Évaluer" pour recalculer le verdict.</span>
        </div>
      )}

      <div className="card-heading">
        <div>
          <span className="eyebrow">Résultat d'évaluation</span>
          <h2>Verdict du modèle {isDirty ? "(Obsolète)" : ""}</h2>
        </div>
        <span className={`decision-pill ${blocked ? "blocked" : "allowed"} ${isDirty ? "verdict-stale" : ""}`}>
          {result.decision}
        </span>
      </div>

      <div className={`verdict-banner ${isDirty ? "verdict-stale" : ""}`}>
        <span className="verdict-icon">
          {blocked ? <IconAlert size={22} /> : <IconCheck size={22} />}
        </span>
        <div className="verdict-copy">
          <strong>{blocked ? "Transaction interceptée" : "Transaction autorisée"}</strong>
          <span>
            {blocked
              ? "Score de risque supérieur au seuil critique."
              : "Comportement financier nominal."}
          </span>
        </div>
        <span className="verdict-prob-num">{fmtPct(probability, 2)}</span>
      </div>

      <div className="gauge-block">
        <div className="gauge-head">
          <span>Score de risque calculé</span>
          <b>{fmtPct(probability, 2)}</b>
        </div>
        <div className="probability-gauge">
          <span
            className={`gauge-fill ${blocked ? "danger" : "safe"}`}
            style={{ width: `${Math.min(100, probability * 100)}%` }}
          />
          <i
            className="gauge-threshold"
            style={{ left: `${threshold * 100}%` }}
            title={`Seuil τ* ${fmtPct(threshold, 1)}`}
          />
        </div>
        <div className="gauge-ticks">
          <span>0 %</span>
          <span>Seuil τ* {fmtPct(threshold, 1)}</span>
          <span>100 %</span>
        </div>
      </div>

      <div className="risk-factors">
        <span className="risk-factors-title">Signatures détectées</span>
        <div className="risk-factors-grid">
          <div className="factor-row">
            <span>Δ Compte émetteur</span>
            <strong className={origDelta < 0 && origAfter === 0 ? "text-rose" : ""}>
              {origDelta.toLocaleString("fr-FR")} $
            </strong>
          </div>
          <div className="factor-row">
            <span>Δ Compte bénéficiaire</span>
            <strong className={isDestSuspect ? "text-rose" : ""}>
              {isDestSuspect
                ? "0 $ (Suspect)"
                : destDelta === 0
                ? "0 $"
                : `+${destDelta.toLocaleString("fr-FR")} $`}
            </strong>
          </div>
        </div>
      </div>

      <div className="result-metrics">
        <div>
          <span>Latence API</span>
          <strong>{Number(result.latency_ms).toFixed(1)} ms</strong>
        </div>
        <div>
          <span>Round-trip RTT</span>
          <strong>{Number(result.rtt).toFixed(0)} ms</strong>
        </div>
        <div>
          <span>Seuil appliqué</span>
          <strong>{fmtPct(threshold, 1)}</strong>
        </div>
        <div>
          <span>Version modèle</span>
          <strong>{result.model_version}</strong>
        </div>
      </div>

      <div className="result-id">
        <span>Identifiant transaction</span>
        <code>{result.transaction_id}</code>
      </div>

      <details className="json-block">
        <summary>
          <IconTerminal size={14} /> Réponse brute JSON (Audit API)
        </summary>
        <pre>{JSON.stringify(payload, null, 2)}</pre>
      </details>
    </section>
  );
}
