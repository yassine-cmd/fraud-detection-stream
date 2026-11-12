import {
  IconActivity,
  IconBarChart,
  IconBell,
  IconExternal,
  IconFlask,
  IconGauge,
  IconShield,
  IconX,
} from "../icons.jsx";
import { docsUrl, fmtPct } from "../api.js";

const NAV = [
  { id: "overview", label: "Vue d'ensemble", icon: IconGauge, section: "Opérations Fraude" },
  { id: "alerts", label: "Registre de triage", icon: IconBell, section: "Opérations Fraude", badge: true },
  { id: "live", label: "Flux & Télémétrie", icon: IconActivity, section: "Ingénierie & Modèle" },
  { id: "test", label: "Bac à sable unitaire", icon: IconFlask, section: "Ingénierie & Modèle" },
];

const SECTIONS = NAV.reduce((groups, item) => {
  const last = groups[groups.length - 1];
  if (last && last.name === item.section) {
    last.items.push(item);
  } else {
    groups.push({ name: item.section, items: [item] });
  }
  return groups;
}, []);

export default function Sidebar({ active, onNavigate, alertCount, model, isOpen, onClose }) {
  return (
    <aside
      className={`sidebar ${isOpen ? "is-open" : ""}`}
      aria-label="Menu principal"
    >
      <div className="sidebar-header">
        <button
          className="brand"
          type="button"
          onClick={() => {
            onNavigate("overview");
            onClose?.();
          }}
        >
          <span className="brand-mark">
            <IconShield size={22} />
          </span>
          <span className="brand-copy">
            <strong>Sentinel</strong>
            <small>Fraud Intelligence</small>
          </span>
        </button>

        <button
          type="button"
          className="sidebar-close-btn"
          onClick={onClose}
          aria-label="Fermer le menu de navigation"
        >
          <IconX size={16} />
        </button>
      </div>

      <nav className="nav" aria-label="Navigation principale">
        {SECTIONS.map((section) => (
          <div key={section.name} className="nav-group">
            <span className="nav-section">{section.name}</span>
            {section.items.map((item) => {
              const Icon = item.icon;
              return (
                <button
                  key={item.id}
                  type="button"
                  className={`nav-item ${active === item.id ? "active" : ""}`}
                  onClick={() => {
                    onNavigate(item.id);
                    onClose?.();
                  }}
                  title={item.label}
                >
                  <span className="nav-icon">
                    <Icon size={18} />
                  </span>
                  <span className="nav-label">{item.label}</span>
                  {item.badge && alertCount > 0 && (
                    <span className="nav-badge">{alertCount > 99 ? "99+" : alertCount}</span>
                  )}
                </button>
              );
            })}
          </div>
        ))}
      </nav>

      <div className="sidebar-spacer" />

      <div className="model-mini">
        <div className="model-mini-head">
          <span className="model-chip">
            <IconBarChart size={13} />
          </span>
          <span>Modèle actif</span>
        </div>
        <strong className="model-mini-version">{model?.model_version || "—"}</strong>
        <div className="model-mini-meta">
          <span>Seuil</span>
          <b>{model ? fmtPct(model.threshold, 1) : "—"}</b>
        </div>
        <div className="model-mini-meta">
          <span>Type</span>
          <b>{model?.model_type || "—"}</b>
        </div>
      </div>

      <a className="sidebar-link" href={docsUrl()} target="_blank" rel="noreferrer">
        <span>API & Swagger</span>
        <IconExternal size={14} />
      </a>
    </aside>
  );
}
