import { useCallback, useEffect, useState } from "react";
import { api } from "./api.js";
import { IconAlert, IconCheck, IconX } from "./icons.jsx";
import useLiveData from "./useLiveData.js";
import usePolling from "./usePolling.js";
import Sidebar from "./components/Sidebar.jsx";
import Topbar from "./components/Topbar.jsx";
import OverviewPage from "./components/OverviewPage.jsx";
import LivePage from "./components/LivePage.jsx";
import AlertsPage from "./components/AlertsPage.jsx";
import TestForm from "./components/TestForm.jsx";
import { ErrorBoundary } from "./components/ErrorBoundary.jsx";

const PAGES = {
  overview: {
    title: "Vue d'ensemble",
    subtitle: "Poste de pilotage macroscopique et analyse d'impact financier.",
  },
  alerts: {
    title: "Registre de triage",
    subtitle: "File d'attente d'investigation et arbitrage des transactions suspectes.",
  },
  live: {
    title: "Flux & Télémétrie",
    subtitle: "Supervision du cluster Kafka-Spark et régulation du débit d'ingestion.",
  },
  test: {
    title: "Bac à sable unitaire",
    subtitle: "Laboratoire d'inférence synchrone en mémoire et analyse de règles.",
  },
};

function initialTab() {
  const hash = window.location.hash.replace("#", "");
  return PAGES[hash] ? hash : "overview";
}

export default function App() {
  const [tab, setTab] = useState(initialTab);
  const [sidebarOpen, setSidebarOpen] = useState(false);
  const [windowRange, setWindowRange] = useState("15m");
  const [health, setHealth] = useState(null);
  const [healthError, setHealthError] = useState(null);
  const [model, setModel] = useState(null);
  const [toast, setToast] = useState(null);
  const [refreshing, setRefreshing] = useState(false);

  const data = useLiveData(windowRange);

  const notify = useCallback((message, type = "info") => {
    setToast({ id: Date.now(), message, type });
  }, []);

  usePolling(async () => {
    try {
      setHealth(await api("/health"));
      setHealthError(null);
    } catch (error) {
      setHealth(null);
      setHealthError(error.message);
    }
  }, 10000);

  usePolling(async () => {
    try {
      setModel(await api("/model/info"));
    } catch {
      /* le modèle sera affiché dès que l'API répond */
    }
  }, 30000);

  useEffect(() => {
    if (!toast) return undefined;
    const timer = window.setTimeout(() => setToast(null), 4500);
    return () => window.clearTimeout(timer);
  }, [toast]);

  useEffect(() => {
    const onHashChange = () => setTab(initialTab());
    window.addEventListener("hashchange", onHashChange);
    return () => window.removeEventListener("hashchange", onHashChange);
  }, []);

  useEffect(() => {
    document.title = `${PAGES[tab].title} · Sentinel Fraud Intelligence`;
  }, [tab]);

  function navigate(nextTab) {
    if (!PAGES[nextTab]) return;
    setTab(nextTab);
    window.location.hash = nextTab;
    window.scrollTo({ top: 0, behavior: "smooth" });
  }

  async function refreshAll() {
    setRefreshing(true);
    try {
      await data.refresh();
    } finally {
      window.setTimeout(() => setRefreshing(false), 450);
    }
  }

  const meta = PAGES[tab];
  const degraded = health && health.status !== "healthy";

  return (
    <div className="app-shell">
      {sidebarOpen && (
        <div
          className="sidebar-backdrop"
          onClick={() => setSidebarOpen(false)}
          aria-hidden="true"
        />
      )}

      <Sidebar
        active={tab}
        onNavigate={navigate}
        alertCount={data.alerts.length}
        model={model}
        isOpen={sidebarOpen}
        onClose={() => setSidebarOpen(false)}
      />

      <div className="app-main">
        <Topbar
          title={meta.title}
          subtitle={meta.subtitle}
          health={health}
          healthError={healthError}
          stream={data.stream}
          lastUpdated={data.lastUpdated}
          onRefresh={refreshAll}
          refreshing={refreshing}
          onToggleSidebar={() => setSidebarOpen((prev) => !prev)}
        />

        {health?.mode === "mock" && (
          <div className="banner banner-mock">
            <IconAlert size={15} />
            <span>
              Mode MOCK actif : les compteurs, alertes et le simulateur sont générés en mémoire. Les services
              Kafka/MongoDB/Spark ne sont pas sollicités.
            </span>
          </div>
        )}
        {healthError && (
          <div className="banner banner-danger">
            <IconAlert size={15} />
            <span>{healthError}</span>
          </div>
        )}
        {!healthError && degraded && health.mode === "real" && (
          <div className="banner banner-warn">
            <IconAlert size={15} />
            <span>
              Service dégradé — Kafka : {health.kafka}, MongoDB : {health.mongodb}, modèle :{" "}
              {health.model_loaded ? "chargé" : "non chargé"}.
            </span>
          </div>
        )}

        <main className="content">
          <ErrorBoundary>
            {tab === "overview" && (
              <OverviewPage
                data={data}
                health={health}
                healthError={healthError}
                model={model}
                windowRange={windowRange}
                onWindowRange={setWindowRange}
                onNavigate={navigate}
                onNotify={notify}
              />
            )}
            {tab === "live" && (
              <LivePage
                data={data}
                health={health}
                healthError={healthError}
                model={model}
                windowRange={windowRange}
                onWindowRange={setWindowRange}
                onNotify={notify}
                onNavigate={navigate}
              />
            )}
            {tab === "alerts" && (
              <AlertsPage
                alerts={data.alerts}
                newIds={data.newIds}
                model={model}
                onNotify={notify}
              />
            )}
            {tab === "test" && (
              <TestForm
                onNotify={notify}
                model={model}
              />
            )}
          </ErrorBoundary>
        </main>
      </div>

      {toast && (
        <div className={`toast toast-${toast.type}`} role="status" aria-live="polite">
          <span className="toast-icon">
            {toast.type === "error" ? <IconAlert size={17} /> : <IconCheck size={17} />}
          </span>
          <span className="toast-message">{toast.message}</span>
          <button type="button" onClick={() => setToast(null)} aria-label="Fermer la notification">
            <IconX size={15} />
          </button>
        </div>
      )}
    </div>
  );
}
