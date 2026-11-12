import { useMemo, useState } from "react";
import { fmtInt, fmtMoney, fmtPct, getSeverity } from "../api.js";
import {
  IconBell,
  IconDownload,
  IconLayers,
  IconPause,
  IconPercent,
  IconPlay,
  IconSearch,
  IconShield,
  IconWallet,
  IconX,
} from "../icons.jsx";
import AlertsTable from "./AlertsTable.jsx";
import AlertDrawer from "./AlertDrawer.jsx";

const SEVERITY_OPTIONS = [
  { key: "ALL", label: "Toutes sévérités" },
  { key: "CRITICAL", label: "Critique (≥ 99%)" },
  { key: "MAJOR", label: "Majeure (≥ 97%)" },
  { key: "THRESHOLD", label: "Seuil (≥ 94.5%)" },
];

export default function AlertsPage({
  alerts = [],
  newIds,
  onNotify,
  model,
  selectedAlert: propSelectedAlert,
  onSelectAlert: propOnSelectAlert,
}) {
  const [search, setSearch] = useState("");
  const [type, setType] = useState("ALL");
  const [severityFilter, setSeverityFilter] = useState("ALL");
  const [localSelectedAlert, setLocalSelectedAlert] = useState(null);
  const [isPaused, setIsPaused] = useState(false);
  const [frozenAlerts, setFrozenAlerts] = useState(null);

  const selectedAlert = propSelectedAlert !== undefined ? propSelectedAlert : localSelectedAlert;
  const setSelectedAlert = propOnSelectAlert || setLocalSelectedAlert;

  function togglePause() {
    if (isPaused) {
      setIsPaused(false);
      setFrozenAlerts(null);
      onNotify?.("Reprise du flux d'alertes en temps réel.", "info");
    } else {
      setIsPaused(true);
      setFrozenAlerts(alerts);
      onNotify?.("Flux d'alertes suspendu pour examen.", "warning");
    }
  }

  const activeAlerts = isPaused && frozenAlerts !== null ? frozenAlerts : alerts;

  const types = useMemo(() => [...new Set(activeAlerts.map((alert) => alert.type))].sort(), [activeAlerts]);

  const filtered = useMemo(() => {
    const needle = search.trim().toLowerCase();
    return activeAlerts.filter((alert) => {
      const matchesType = type === "ALL" || alert.type === type;
      const prob = Number(alert.probability) || 0;
      let matchesSeverity = true;
      if (severityFilter === "CRITICAL") {
        matchesSeverity = prob >= 0.99;
      } else if (severityFilter === "MAJOR") {
        matchesSeverity = prob >= 0.97;
      } else if (severityFilter === "THRESHOLD") {
        matchesSeverity = prob >= 0.9447;
      }
      const matchesSearch =
        !needle ||
        String(alert.transaction_id || "").toLowerCase().includes(needle) ||
        String(alert.nameOrig || "").toLowerCase().includes(needle) ||
        String(alert.nameDest || "").toLowerCase().includes(needle) ||
        String(alert.model_version || "").toLowerCase().includes(needle) ||
        String(alert.type || "").toLowerCase().includes(needle) ||
        String(alert.amount || "").includes(needle);
      return matchesType && matchesSeverity && matchesSearch;
    });
  }, [activeAlerts, search, type, severityFilter]);

  const isFiltered = search.trim().length > 0 || type !== "ALL" || severityFilter !== "ALL";

  function resetFilters() {
    setSearch("");
    setType("ALL");
    setSeverityFilter("ALL");
  }

  const totals = useMemo(() => {
    const amount = activeAlerts.reduce((sum, alert) => sum + (Number(alert.amount) || 0), 0);
    const avgProbability = activeAlerts.length
      ? activeAlerts.reduce((sum, alert) => sum + (Number(alert.probability) || 0), 0) / activeAlerts.length
      : 0;
    return { amount, avgProbability };
  }, [activeAlerts]);

  function handleExport() {
    const header = [
      "timestamp",
      "transaction_id",
      "type",
      "amount",
      "nameOrig",
      "nameDest",
      "oldbalanceOrg",
      "newbalanceOrig",
      "oldbalanceDest",
      "newbalanceDest",
      "severity",
      "probability",
      "model_version",
      "decision",
    ];
    const lines = filtered.map((alert) => {
      const p = Number(alert.probability) || 0;
      const sev =
        p >= 0.99 ? "Critique" : p >= 0.97 ? "Majeure" : p >= 0.9447 ? "Seuil" : getSeverity(p).label;
      return [
        alert.timestamp,
        alert.transaction_id,
        alert.type,
        alert.amount,
        alert.nameOrig ?? "",
        alert.nameDest ?? "",
        alert.oldbalanceOrg ?? "",
        alert.newbalanceOrig ?? "",
        alert.oldbalanceDest ?? "",
        alert.newbalanceDest ?? "",
        sev,
        alert.probability,
        alert.model_version,
        alert.decision || "BLOCKED",
      ]
        .map((value) => `"${String(value ?? "").replace(/"/g, '""')}"`)
        .join(",");
    });
    const blob = new Blob([[header.join(","), ...lines].join("\n")], {
      type: "text/csv;charset=utf-8",
    });
    const url = URL.createObjectURL(blob);
    const link = document.createElement("a");
    link.href = url;
    link.download = `alertes-fraude-${new Date().toISOString().slice(0, 19).replace(/[:T]/g, "-")}.csv`;
    document.body.appendChild(link);
    link.click();
    link.remove();
    URL.revokeObjectURL(url);
    onNotify?.(`${filtered.length} alerte(s) exportée(s) en CSV.`, "success");
  }

  const exportCsv = handleExport;

  return (
    <div className="page-stack">
      <div className="page-head">
        <div>
          <span className="eyebrow">Supervision</span>
          <h2>Registre des alertes</h2>
          <p>
            Transactions dont la probabilité dépasse le seuil du modèle, triées de la plus récente
            à la plus ancienne. Cliquez sur une ligne pour inspecter l'enregistrement d'audit.
          </p>
        </div>
        <div style={{ display: "flex", gap: "8px", alignItems: "center" }}>
          <button
            type="button"
            className={`btn ${isPaused ? "btn-danger-ghost active" : "btn-ghost"}`}
            onClick={togglePause}
            title={isPaused ? "Reprendre le flux en temps réel" : "Figer la liste des alertes"}
            aria-pressed={isPaused}
          >
            {isPaused ? <IconPlay size={16} /> : <IconPause size={16} />}
            <span>{isPaused ? "Reprendre flux" : "Pause flux"}</span>
          </button>
          <button
            type="button"
            className="btn btn-ghost"
            onClick={handleExport}
            disabled={!filtered.length}
            title="Télécharger l'extrait CSV des alertes affichées"
          >
            <IconDownload size={16} /> Exporter CSV ({filtered.length})
          </button>
        </div>
      </div>

      <div className="stat-strip">
        <div className="stat-tile">
          <span className="stat-icon cyan">
            <IconBell size={18} />
          </span>
          <div>
            <span>Alertes chargées</span>
            <strong>{fmtInt(activeAlerts.length)}</strong>
            <small>max. 100 dernières</small>
          </div>
        </div>
        <div className="stat-tile">
          <span className="stat-icon rose">
            <IconWallet size={18} />
          </span>
          <div>
            <span>Montant cumulé bloqué</span>
            <strong>{fmtMoney(totals.amount)}</strong>
            <small>sur les alertes chargées</small>
          </div>
        </div>
        <div className="stat-tile">
          <span className="stat-icon amber">
            <IconPercent size={18} />
          </span>
          <div>
            <span>Probabilité moyenne</span>
            <strong>{fmtPct(totals.avgProbability, 1)}</strong>
            <small>confiance du modèle</small>
          </div>
        </div>
        <div className="stat-tile">
          <span className="stat-icon violet">
            <IconLayers size={18} />
          </span>
          <div>
            <span>Types concernés</span>
            <strong>{fmtInt(types.length)}</strong>
            <small>TRANSFER / CASH_OUT</small>
          </div>
        </div>
      </div>

      <section className="card alerts-card">
        <div className="alerts-toolbar">
          <div className="search-box">
            <IconSearch size={16} />
            <input
              type="search"
              placeholder="Rechercher compte, identifiant, type…"
              value={search}
              onChange={(event) => setSearch(event.target.value)}
              aria-label="Rechercher une alerte"
            />
            {search && (
              <button
                type="button"
                className="search-clear-btn"
                onClick={() => setSearch("")}
                aria-label="Effacer la recherche"
              >
                <IconX size={14} />
              </button>
            )}
          </div>

          <div className="filter-group-wrap">
            <div className="filter-tabs" role="group" aria-label="Filtrer par type de transaction">
              <button
                type="button"
                className={type === "ALL" ? "active" : ""}
                onClick={() => setType("ALL")}
              >
                Toutes
              </button>
              {types.map((item) => (
                <button
                  key={item}
                  type="button"
                  className={type === item ? "active" : ""}
                  onClick={() => setType(item)}
                >
                  {item}
                </button>
              ))}
            </div>

            <div className="filter-tabs severity-tabs" role="group" aria-label="Filtrer par sévérité">
              {SEVERITY_OPTIONS.map((opt) => (
                <button
                  key={opt.key}
                  type="button"
                  className={`sev-tab-btn ${severityFilter === opt.key ? "active" : ""}`}
                  onClick={() => setSeverityFilter(opt.key)}
                >
                  {opt.label}
                </button>
              ))}
            </div>
          </div>

          <span className="result-count">
            {fmtInt(filtered.length)} / {fmtInt(activeAlerts.length)}
            {isPaused && (
              <span style={{ marginLeft: "8px", color: "var(--accent-amber)", fontSize: "11px" }}>
                (Pause active)
              </span>
            )}
          </span>
        </div>

        <AlertsTable
          alerts={filtered}
          newIds={isPaused ? new Set() : newIds}
          full
          onSelectAlert={setSelectedAlert}
          selectedId={selectedAlert?.transaction_id}
          isFiltered={isFiltered}
          onResetFilters={resetFilters}
          onNotify={onNotify}
        />
      </section>

      {/* Slide-over Detail Drawer */}
      {selectedAlert && (
        <AlertDrawer
          alert={selectedAlert}
          onClose={() => setSelectedAlert(null)}
          model={model}
          onNotify={onNotify}
        />
      )}
    </div>
  );
}
