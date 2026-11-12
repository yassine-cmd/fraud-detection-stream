import { useEffect, useRef, useState } from "react";
import { fmtDateUTC, fmtMoney, fmtPct, getSeverity, pctWidth, shortId } from "../api.js";
import {
  IconCheck,
  IconClock,
  IconCopy,
  IconShield,
  IconTerminal,
  IconX,
  IconZap,
} from "../icons.jsx";

const ACTION_TONES = {
  danger: { bg: "rgba(244, 63, 94, 0.15)", border: "rgba(244, 63, 94, 0.35)", text: "#fda4af" },
  success: { bg: "rgba(16, 185, 129, 0.15)", border: "rgba(16, 185, 129, 0.35)", text: "#6ee7b7" },
  warning: { bg: "rgba(245, 158, 11, 0.15)", border: "rgba(245, 158, 11, 0.35)", text: "#fcd34d" },
};

export default function AlertDrawer({ alert, onClose, model, onNotify }) {
  const [copiedId, setCopiedId] = useState(false);
  const [copiedJson, setCopiedJson] = useState(false);
  const [caseStatus, setCaseStatus] = useState(
    alert?.status ? (typeof alert.status === "string" ? { label: alert.status, tone: "info" } : alert.status) : null
  );
  const [note, setNote] = useState(alert?.note || "");
  const panelRef = useRef(null);

  useEffect(() => {
    setCaseStatus(
      alert?.status ? (typeof alert.status === "string" ? { label: alert.status, tone: "info" } : alert.status) : null
    );
    setNote(alert?.note || "");
  }, [alert]);

  // Focus trap, touche Echap et verrouillage du défilement
  useEffect(() => {
    if (!alert) return;

    const previousFocusedElement = document.activeElement;
    document.body.style.overflow = "hidden";

    // Focus sur le panneau
    const focusTimer = setTimeout(() => {
      const focusable = panelRef.current?.querySelectorAll(
        'button, [href], input, select, textarea, [tabindex]:not([tabindex="-1"])'
      );
      if (focusable && focusable.length > 0) {
        focusable[0].focus();
      }
    }, 50);

    function handleKeyDown(event) {
      if (event.key === "Escape") {
        event.preventDefault();
        onClose();
        return;
      }

      if (event.key === "Tab" && panelRef.current) {
        const focusable = Array.from(
          panelRef.current.querySelectorAll(
            'button, [href], input, select, textarea, [tabindex]:not([tabindex="-1"])'
          )
        ).filter((el) => !el.disabled && el.offsetParent !== null);

        if (focusable.length === 0) return;

        const firstElement = focusable[0];
        const lastElement = focusable[focusable.length - 1];

        if (event.shiftKey) {
          if (document.activeElement === firstElement) {
            lastElement.focus();
            event.preventDefault();
          }
        } else {
          if (document.activeElement === lastElement) {
            firstElement.focus();
            event.preventDefault();
          }
        }
      }
    }

    window.addEventListener("keydown", handleKeyDown);

    return () => {
      clearTimeout(focusTimer);
      document.body.style.overflow = "";
      window.removeEventListener("keydown", handleKeyDown);
      if (previousFocusedElement && typeof previousFocusedElement.focus === "function") {
        previousFocusedElement.focus();
      }
    };
  }, [alert, onClose]);

  if (!alert) return null;

  const severity = getSeverity(alert.probability);
  const probability = Number(alert.probability) || 0;
  const threshold = model?.threshold ?? 0.9447;
  const decision = alert.decision || "BLOCKED";
  const blocked = decision === "BLOCKED";

  const origBefore = alert.oldbalanceOrg !== undefined && alert.oldbalanceOrg !== null ? Number(alert.oldbalanceOrg) : null;
  const origAfter = alert.newbalanceOrig !== undefined && alert.newbalanceOrig !== null ? Number(alert.newbalanceOrig) : null;
  const origDelta = origBefore !== null && origAfter !== null ? origAfter - origBefore : null;

  const destBefore = alert.oldbalanceDest !== undefined && alert.oldbalanceDest !== null ? Number(alert.oldbalanceDest) : null;
  const destAfter = alert.newbalanceDest !== undefined && alert.newbalanceDest !== null ? Number(alert.newbalanceDest) : null;
  const destDelta = destBefore !== null && destAfter !== null ? destAfter - destBefore : null;

  async function copyText(text, isJson = false) {
    let success = false;
    try {
      if (navigator?.clipboard?.writeText) {
        await navigator.clipboard.writeText(text);
        success = true;
      }
    } catch {
      /* fallback */
    }
    if (!success) {
      try {
        const textarea = document.createElement("textarea");
        textarea.value = text;
        textarea.style.position = "fixed";
        textarea.style.opacity = "0";
        document.body.appendChild(textarea);
        textarea.select();
        document.execCommand("copy");
        document.body.removeChild(textarea);
        success = true;
      } catch {
        /* non supporté */
      }
    }
    if (success) {
      if (isJson) {
        setCopiedJson(true);
        setTimeout(() => setCopiedJson(false), 1500);
        onNotify?.("JSON de l'alerte copié dans le presse-papier.", "success");
      } else {
        setCopiedId(true);
        setTimeout(() => setCopiedId(false), 1500);
        onNotify?.("Identifiant de transaction copié.", "success");
      }
    }
  }

  // Signaux d'anomalie métier constatés sur les attributs
  const signals = [];
  if (alert.type === "TRANSFER" || alert.type === "CASH_OUT") {
    signals.push({ label: `Canal à haut risque (${alert.type})`, tone: "danger" });
  }
  if (Number(alert.amount) >= 200000) {
    signals.push({ label: "Montant atypique (≥ 200 000 $)", tone: "danger" });
  }
  if (origAfter === 0 && origBefore > 0) {
    signals.push({ label: "Compte émetteur entièrement vidé", tone: "danger" });
  }
  if (destDelta === 0 && Number(alert.amount) > 0) {
    signals.push({ label: "Bénéficiaire non crédité (détournement)", tone: "warning" });
  }
  if (signals.length === 0) {
    signals.push({ label: "Déviation statistique détectée par le modèle", tone: "info" });
  }

  function handleCaseAction(label, tone, message) {
    const nextStatus = { label, tone };
    setCaseStatus(nextStatus);
    if (alert) alert.status = nextStatus;
    onNotify?.(`Dossier mis à jour: ${message}`, tone === "danger" ? "warning" : "success");
  }

  function handleSaveNote() {
    if (alert) alert.note = note;
    onNotify?.("Dossier mis à jour: Note d'audit enregistrée.", "success");
  }

  return (
    <>
      <div className="drawer-backdrop" onClick={onClose} aria-hidden="true" />
      <aside
        ref={panelRef}
        className="drawer-panel"
        role="dialog"
        aria-modal="true"
        aria-labelledby="drawer-alert-title"
      >
        <div className="drawer-header">
          <div className="drawer-head-info">
            <span className="eyebrow">Détail d'audit fraude</span>
            <div className="drawer-id-row">
              <strong id="drawer-alert-title" className="drawer-id" title={alert.transaction_id}>
                {shortId(alert.transaction_id, 20)}
              </strong>
              <button
                type="button"
                className="drawer-copy-btn"
                onClick={() => copyText(alert.transaction_id, false)}
                title={copiedId ? "Copié !" : "Copier l'identifiant complet"}
                aria-label="Copier l'identifiant de la transaction"
              >
                {copiedId ? <IconCheck size={13} /> : <IconCopy size={13} />}
                <span>{copiedId ? "Copié !" : "Copier ID"}</span>
              </button>
            </div>
            {caseStatus && (
              <span
                style={{
                  alignSelf: "flex-start",
                  marginTop: "4px",
                  padding: "2px 7px",
                  fontSize: "10.5px",
                  fontWeight: 700,
                  letterSpacing: "0.03em",
                  textTransform: "uppercase",
                  borderRadius: "var(--radius-xs)",
                  background: ACTION_TONES[caseStatus.tone]?.bg,
                  border: `1px solid ${ACTION_TONES[caseStatus.tone]?.border}`,
                  color: ACTION_TONES[caseStatus.tone]?.text,
                }}
              >
                Statut: {caseStatus.label}
              </span>
            )}
          </div>
          <div className="drawer-head-actions">
            <span className={`severity-badge severity-${severity.tone}`}>
              {severity.label}
            </span>
            <span className={`decision-badge ${blocked ? "badge-danger" : "badge-success"}`}>
              {decision}
            </span>
            <button
              type="button"
              className="drawer-close-btn"
              onClick={onClose}
              aria-label="Fermer le panneau d'inspection"
            >
              <IconX size={16} />
            </button>
          </div>
        </div>

        <div className="drawer-body">
          {/* 1. Résumé financier */}
          <div className="drawer-hero">
            <div className="drawer-hero-left">
              <span className="drawer-hero-amount">{fmtMoney(alert.amount)}</span>
              <span className="drawer-hero-date">
                <IconClock size={13} /> {fmtDateUTC(alert.timestamp)}
              </span>
            </div>
            <div className="drawer-hero-right">
              <span className={`type-badge type-${String(alert.type).toLowerCase()}`}>
                {alert.type}
              </span>
              {alert.step && (
                <span className="step-pill" title="Heure PaySim simulée">
                  Step {alert.step}
                </span>
              )}
            </div>
          </div>

          {/* 1b. Traitement Dossier & Décision Analyste */}
          <section className="drawer-section">
            <div className="drawer-section-title-row">
              <span className="drawer-section-title">Traitement Dossier & Décision Analyste</span>
              {caseStatus && (
                <span
                  style={{
                    fontSize: "11px",
                    fontWeight: 700,
                    color: ACTION_TONES[caseStatus.tone]?.text,
                  }}
                >
                  Statut: {caseStatus.label}
                </span>
              )}
            </div>
            <div style={{ display: "flex", gap: "8px", flexWrap: "wrap" }}>
              <button
                type="button"
                onClick={() =>
                  handleCaseAction("Confirmé par analyste", "danger", "Fraude confirmée par analyste")
                }
                style={{
                  flex: "1 1 120px",
                  padding: "7px 10px",
                  fontSize: "11.5px",
                  fontWeight: 600,
                  borderRadius: "var(--radius-xs)",
                  cursor: "pointer",
                  background:
                    caseStatus?.label === "Confirmé par analyste"
                      ? "rgba(244, 63, 94, 0.25)"
                      : "rgba(244, 63, 94, 0.1)",
                  border: "1px solid rgba(244, 63, 94, 0.4)",
                  color: "#fda4af",
                  transition: "all 0.12s",
                }}
              >
                Confirmer fraude
              </button>
              <button
                type="button"
                onClick={() =>
                  handleCaseAction("Faux positif classé", "success", "Faux positif classé")
                }
                style={{
                  flex: "1 1 120px",
                  padding: "7px 10px",
                  fontSize: "11.5px",
                  fontWeight: 600,
                  borderRadius: "var(--radius-xs)",
                  cursor: "pointer",
                  background:
                    caseStatus?.label === "Faux positif classé"
                      ? "rgba(16, 185, 129, 0.25)"
                      : "rgba(16, 185, 129, 0.1)",
                  border: "1px solid rgba(16, 185, 129, 0.4)",
                  color: "#6ee7b7",
                  transition: "all 0.12s",
                }}
              >
                Faux positif / Relâcher
              </button>
              <button
                type="button"
                onClick={() =>
                  handleCaseAction("Compte gelé", "warning", "Compte émetteur gelé")
                }
                style={{
                  flex: "1 1 120px",
                  padding: "7px 10px",
                  fontSize: "11.5px",
                  fontWeight: 600,
                  borderRadius: "var(--radius-xs)",
                  cursor: "pointer",
                  background:
                    caseStatus?.label === "Compte gelé"
                      ? "rgba(245, 158, 11, 0.25)"
                      : "rgba(245, 158, 11, 0.1)",
                  border: "1px solid rgba(245, 158, 11, 0.4)",
                  color: "#fcd34d",
                  transition: "all 0.12s",
                }}
              >
                Geler compte
              </button>
            </div>

            <div style={{ display: "flex", flexDirection: "column", gap: "6px" }}>
              <textarea
                value={note}
                onChange={(e) => setNote(e.target.value)}
                placeholder="Note d'audit et justification d'enquête..."
                rows={2}
                aria-label="Note d'audit d'enquête"
                style={{
                  width: "100%",
                  padding: "7px 10px",
                  fontSize: "12px",
                  fontFamily: "inherit",
                  background: "var(--surface-inset)",
                  border: "1px solid var(--border-hairline)",
                  borderRadius: "var(--radius-xs)",
                  color: "#fff",
                  resize: "vertical",
                  outline: "none",
                }}
              />
              <div style={{ display: "flex", justifyContent: "flex-end" }}>
                <button
                  type="button"
                  className="btn-tiny"
                  onClick={handleSaveNote}
                >
                  Enregistrer la note
                </button>
              </div>
            </div>
          </section>

          {/* 2. Trajectoire des Soldes */}
          <section className="drawer-section">
            <div className="drawer-section-title">Comptes & Trajectoire des Soldes</div>
            <div className="balance-trajectories">
              {/* Origine */}
              <div className="trajectory-card">
                <div className="trajectory-head">
                  <span className="trajectory-role">Émetteur (Origine)</span>
                  <code className="account-tag">{alert.nameOrig || "Compte émetteur"}</code>
                </div>
                {origBefore !== null ? (
                  <div className="balance-flow">
                    <div className="balance-point">
                      <span>Solde initial</span>
                      <strong>{fmtMoney(origBefore)}</strong>
                    </div>
                    <span className="balance-arrow">→</span>
                    <div className="balance-point">
                      <span>Solde final</span>
                      <strong className={origAfter === 0 ? "text-rose" : ""}>
                        {fmtMoney(origAfter)}
                      </strong>
                    </div>
                  </div>
                ) : (
                  <div className="balance-empty-hint">Non renseigné dans l'alerte</div>
                )}
                {origDelta !== null && (
                  <div className="trajectory-delta">
                    Variation nette :{" "}
                    <b className={origDelta < 0 ? "text-rose" : ""}>
                      {origDelta.toLocaleString("fr-FR")} $
                    </b>
                  </div>
                )}
              </div>

              {/* Destination */}
              <div className="trajectory-card">
                <div className="trajectory-head">
                  <span className="trajectory-role">Bénéficiaire (Destinataire)</span>
                  <code className="account-tag">{alert.nameDest || "Compte bénéficiaire"}</code>
                </div>
                {destBefore !== null ? (
                  <div className="balance-flow">
                    <div className="balance-point">
                      <span>Solde initial</span>
                      <strong>{fmtMoney(destBefore)}</strong>
                    </div>
                    <span className="balance-arrow">→</span>
                    <div className="balance-point">
                      <span>Solde final</span>
                      <strong>{fmtMoney(destAfter)}</strong>
                    </div>
                  </div>
                ) : (
                  <div className="balance-empty-hint">Non renseigné dans l'alerte</div>
                )}
                {destDelta !== null && (
                  <div className="trajectory-delta">
                    Variation nette :{" "}
                    <b className={destDelta === 0 ? "text-rose" : "text-emerald"}>
                      {destDelta === 0 ? "0 $ (Solde inchangé)" : `+${destDelta.toLocaleString("fr-FR")} $`}
                    </b>
                  </div>
                )}
              </div>
            </div>
          </section>

          {/* 3. Analyse du Risque & Signatures */}
          <section className="drawer-section">
            <div className="drawer-section-title">Indicateurs de Risque & Signatures Métier</div>
            <div className="drawer-ml-card">
              <div className="drawer-ml-head">
                <div className="drawer-ml-score">
                  <span className="drawer-ml-label">Probabilité de fraude estimée</span>
                  <strong className="drawer-ml-value">{fmtPct(probability, 2)}</strong>
                </div>
                <div className="drawer-ml-threshold">
                  <span>Seuil critique τ*</span>
                  <b>{fmtPct(threshold, 1)}</b>
                </div>
              </div>

              <div className="prob-cell drawer-prob-bar">
                <span className="prob-track">
                  <i
                    className={probability >= threshold ? "bar-danger" : "bar-safe"}
                    style={{ width: pctWidth(probability) }}
                  />
                </span>
              </div>

              <div className="drawer-rule-banner">
                <IconShield size={16} />
                <span>
                  {probability >= threshold
                    ? `Score supérieur au seuil décisionnel (τ* = ${fmtPct(threshold, 1)}) — Interception immédiate par le modèle.`
                    : "Score inférieur au seuil décisionnel nominal."}
                </span>
              </div>

              <div className="drawer-signals-list">
                <span className="drawer-signals-title">Indicateurs déclenchés</span>
                <div className="drawer-signals-tags">
                  {signals.map((sig, i) => (
                    <span key={i} className={`signal-tag signal-${sig.tone}`}>
                      <IconZap size={12} />
                      {sig.label}
                    </span>
                  ))}
                </div>
              </div>
            </div>
          </section>

          {/* 4. Métadonnées de Pipeline */}
          <section className="drawer-section">
            <div className="drawer-section-title">Métadonnées de Pipeline</div>
            <div className="drawer-meta-grid">
              <div className="drawer-meta-item">
                <span>Modèle d'inférence</span>
                <strong>{alert.model_version || model?.model_version || "v1.0.0-xgb"}</strong>
              </div>
              <div className="drawer-meta-item">
                <span>Décision pipeline</span>
                <strong className={blocked ? "text-rose" : "text-emerald"}>{decision}</strong>
              </div>
              <div className="drawer-meta-item">
                <span>Canal transactionnel</span>
                <strong>{alert.type}</strong>
              </div>
              <div className="drawer-meta-item">
                <span>Classe de sévérité</span>
                <strong className={`text-${severity.tone}`}>{severity.label}</strong>
              </div>
            </div>
          </section>

          {/* 5. Document JSON brut */}
          <section className="drawer-section">
            <div className="drawer-section-title-row">
              <span className="drawer-section-title">Audit Brut JSON</span>
              <button
                type="button"
                className="btn-tiny"
                onClick={() => copyText(JSON.stringify(alert, null, 2), true)}
              >
                {copiedJson ? <IconCheck size={12} /> : <IconCopy size={12} />}
                <span>{copiedJson ? "Copié !" : "Copier JSON"}</span>
              </button>
            </div>
            <details className="json-block" open={false}>
              <summary>
                <IconTerminal size={14} /> Voir le document complet
              </summary>
              <pre>{JSON.stringify(alert, null, 2)}</pre>
            </details>
          </section>
        </div>
      </aside>
    </>
  );
}
