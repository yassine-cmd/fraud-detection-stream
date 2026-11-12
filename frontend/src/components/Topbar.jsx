import { IconMenu, IconRefresh } from "../icons.jsx";

export default function Topbar({
  title,
  subtitle,
  health,
  healthError,
  lastUpdated,
  onRefresh,
  refreshing,
  onToggleSidebar,
}) {
  const status = healthError ? "offline" : health?.status || "degraded";
  const lagSec = health?.pipeline_lag_seconds;

  let statusMode = "degraded";
  let statusLabel = "Service dégradé";
  let statusTitle = healthError || "État du système";

  if (healthError) {
    statusMode = "offline";
    statusLabel = "API hors ligne";
  } else if (status === "healthy") {
    if (lagSec !== undefined && lagSec !== null && lagSec > 30) {
      statusMode = "lagging";
      const lagMin = Math.round(lagSec / 60);
      statusLabel = lagMin > 1 ? `Différé (~${lagMin} min)` : `Sync (${Math.round(lagSec)}s)`;
      statusTitle = `Retard d'ingestion Spark : ~${Math.round(lagSec)} secondes de décalage`;
    } else {
      statusMode = "live";
      statusLabel = "En direct";
      statusTitle = "Flux temps réel actif et synchronisé (< 30s de décalage)";
    }
  } else {
    statusMode = "degraded";
    statusLabel = "Pipeline dégradé";
    statusTitle = "Retard important sur le flux ou dépendance indisponible";
  }

  return (
    <header className="topbar">
      <div className="topbar-left">
        <button
          type="button"
          className="menu-btn"
          onClick={onToggleSidebar}
          aria-label="Ouvrir le menu de navigation"
        >
          <IconMenu size={18} />
        </button>

        <div className="topbar-title">
          <h1>{title}</h1>
          {subtitle && <p className="topbar-subtitle">{subtitle}</p>}
        </div>
      </div>

      <div className="topbar-actions">
        {statusMode === "live" && (
          <div className="live-status-pill" title={statusTitle}>
            <span className="live-pulse-dot" />
            <span>{statusLabel}</span>
          </div>
        )}
        {statusMode === "lagging" && (
          <div
            className="status-alert-pill status-degraded"
            style={{ borderColor: "#f59e0b", background: "rgba(245, 158, 11, 0.12)", color: "#fbbf24" }}
            title={statusTitle}
          >
            <span className="status-warn-dot" style={{ background: "#f59e0b" }} />
            <span>{statusLabel}</span>
          </div>
        )}
        {(statusMode === "degraded" || statusMode === "offline") && (
          <div className={`status-alert-pill status-${statusMode}`} title={statusTitle}>
            <span className="status-warn-dot" />
            <span>{statusLabel}</span>
          </div>
        )}

        <button
          type="button"
          className={`refresh-btn ${refreshing ? "is-refreshing" : ""}`}
          onClick={onRefresh}
          title={lastUpdated ? `Dernière synchronisation : ${lastUpdated.toLocaleTimeString("fr-FR")}` : "Actualiser les données"}
          aria-label="Actualiser les données"
        >
          <IconRefresh size={15} />
          <span className="refresh-label">Actualiser</span>
        </button>
      </div>
    </header>
  );
}
