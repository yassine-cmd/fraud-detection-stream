import { useMemo, useState } from "react";
import { fmtMoney, fmtPct, fmtProb, fmtTimeUTC, getSeverity, pctWidth, shortId } from "../api.js";
import { IconBell, IconCopy, IconSearch, IconX } from "../icons.jsx";

function CopyButton({ text, onNotify }) {
  const [copied, setCopied] = useState(false);

  async function copy(event) {
    event.stopPropagation();
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
      setCopied(true);
      window.setTimeout(() => setCopied(false), 1400);
      onNotify?.("Identifiant copié dans le presse-papier.", "info");
    }
  }

  return (
    <button
      type="button"
      className="copy-btn"
      onClick={copy}
      title={copied ? "Copié !" : "Copier l'identifiant"}
      aria-label="Copier l'identifiant"
    >
      <IconCopy size={13} />
      <span>{copied ? "Copié !" : shortId(text, 14)}</span>
    </button>
  );
}

export default function AlertsTable({
  alerts = [],
  newIds = new Set(),
  full = false,
  onSelectAlert,
  selectedId,
  isFiltered = false,
  onResetFilters,
  onNotify,
}) {
  const [sortField, setSortField] = useState(null);
  const [sortDirection, setSortDirection] = useState("desc");

  function handleSort(field) {
    if (sortField === field) {
      setSortDirection((prev) => (prev === "asc" ? "desc" : "asc"));
    } else {
      setSortField(field);
      setSortDirection("desc");
    }
  }

  const sortedAlerts = useMemo(() => {
    if (!sortField) return alerts;
    return [...alerts].sort((a, b) => {
      const valA = Number(a[sortField]) || 0;
      const valB = Number(b[sortField]) || 0;
      return sortDirection === "asc" ? valA - valB : valB - valA;
    });
  }, [alerts, sortField, sortDirection]);

  if (!alerts.length) {
    if (isFiltered) {
      return (
        <div className="table-empty search-empty-state">
          <span className="table-empty-icon">
            <IconSearch size={24} />
          </span>
          <strong>Aucun résultat pour cette recherche</strong>
          <p>Aucune transaction interceptée ne correspond aux filtres ou termes spécifiés.</p>
          {onResetFilters && (
            <button type="button" className="btn btn-ghost" onClick={onResetFilters}>
              <IconX size={14} /> Effacer les filtres
            </button>
          )}
        </div>
      );
    }
    return (
      <div className="table-empty">
        <span className="table-empty-icon">
          <IconBell size={24} />
        </span>
        <strong>Aucune alerte pour le moment</strong>
        <p>Les transactions bloquées par le modèle apparaîtront ici en temps réel.</p>
      </div>
    );
  }

  return (
    <div className="table-wrap">
      <table className="alerts-table">
        <thead>
          <tr>
            <th>Heure UTC</th>
            <th>Transaction</th>
            <th>Type</th>
            <th
              className="num sortable-th"
              onClick={() => handleSort("amount")}
              style={{ cursor: "pointer", userSelect: "none" }}
              title="Cliquer pour trier par montant"
              tabIndex={0}
              role="columnheader"
              aria-sort={sortField === "amount" ? (sortDirection === "asc" ? "ascending" : "descending") : "none"}
              onKeyDown={(e) => {
                if (e.key === "Enter" || e.key === " ") {
                  e.preventDefault();
                  handleSort("amount");
                }
              }}
            >
              Montant {sortField === "amount" ? (sortDirection === "asc" ? "▲" : "▼") : "↕"}
            </th>
            <th>Sévérité</th>
            <th
              className="sortable-th"
              onClick={() => handleSort("probability")}
              style={{ cursor: "pointer", userSelect: "none" }}
              title="Cliquer pour trier par probabilité"
              tabIndex={0}
              role="columnheader"
              aria-sort={sortField === "probability" ? (sortDirection === "asc" ? "ascending" : "descending") : "none"}
              onKeyDown={(e) => {
                if (e.key === "Enter" || e.key === " ") {
                  e.preventDefault();
                  handleSort("probability");
                }
              }}
            >
              Probabilité {sortField === "probability" ? (sortDirection === "asc" ? "▲" : "▼") : "↕"}
            </th>
            {full && <th>Modèle</th>}
            {full && <th>Décision</th>}
          </tr>
        </thead>
        <tbody>
          {sortedAlerts.map((alert) => {
            const probability = Number(alert.probability) || 0;
            const severity = getSeverity(probability);
            const isSelected = selectedId === alert.transaction_id;
            const isClickable = Boolean(onSelectAlert);

            return (
              <tr
                key={alert.transaction_id}
                className={`
                  ${newIds.has(alert.transaction_id) ? "is-new" : ""}
                  ${isClickable ? "is-clickable" : ""}
                  ${isSelected ? "is-selected" : ""}
                `.trim()}
                onClick={() => onSelectAlert?.(alert)}
                tabIndex={isClickable ? 0 : undefined}
                role={isClickable ? "button" : undefined}
                aria-selected={isSelected}
                aria-label={isClickable ? `Voir les détails de la transaction ${alert.transaction_id}` : undefined}
                onKeyDown={(e) => {
                  if (isClickable && (e.key === "Enter" || e.key === " ")) {
                    e.preventDefault();
                    onSelectAlert(alert);
                  }
                }}
              >
                <td className="time-cell" title={alert.timestamp}>
                  {full ? `${alert.timestamp.slice(0, 10)} ` : ""}
                  {fmtTimeUTC(alert.timestamp)}
                </td>
                <td>
                  <CopyButton text={alert.transaction_id} onNotify={onNotify} />
                </td>
                <td>
                  <span className={`type-badge type-${String(alert.type).toLowerCase()}`}>
                    {alert.type}
                  </span>
                </td>
                <td className="num amount-cell">{fmtMoney(alert.amount)}</td>
                <td>
                  <span className={`severity-badge severity-${severity.tone}`}>
                    {severity.label}
                  </span>
                </td>
                <td>
                  <div className="prob-cell">
                    <span className="prob-track">
                      <i
                        className={probability >= 0.9447 ? "bar-danger" : "bar-safe"}
                        style={{ width: pctWidth(probability) }}
                      />
                    </span>
                    <b>{fmtProb(probability)}</b>
                  </div>
                </td>
                {full && <td className="model-cell">{alert.model_version}</td>}
                {full && (
                  <td>
                    <span className={`decision-badge ${alert.decision === "ALLOWED" ? "badge-success" : "badge-danger"}`}>
                      {alert.decision || "BLOCKED"}
                    </span>
                  </td>
                )}
              </tr>
            );
          })}
        </tbody>
      </table>
    </div>
  );
}
