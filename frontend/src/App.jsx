import { useState } from "react";
import { api } from "./api.js";
import usePolling from "./usePolling.js";
import Dashboard from "./components/Dashboard.jsx";
import TestForm from "./components/TestForm.jsx";

export default function App() {
  const [tab, setTab] = useState("dash");
  const [health, setHealth] = useState(null);
  const [healthErr, setHealthErr] = useState(null);

  usePolling(async () => {
    try { setHealth(await api("/health")); setHealthErr(null); }
    catch (e) { setHealth(null); setHealthErr(e.message); }
  }, 15000);

  let pill = ["pill pill-off", "API : …"];
  let banner = null;
  if (healthErr) {
    pill = ["pill pill-bad", "API injoignable"];
    banner = { text: "API injoignable : " + healthErr, cls: "" };
  } else if (health) {
    pill = [`pill ${health.status === "healthy" ? "pill-on" : "pill-warn"}`,
      `API ${health.status} · modèle ${health.model_version || "?"} · ${health.mode}`];
    if (health.mode === "mock") banner = { text: "Mode MOCK : les données affichées sont simulées.", cls: "warn" };
    else if (health.status !== "healthy")
      banner = { text: `Service dégradé — Kafka : ${health.kafka}, MongoDB : ${health.mongodb}, modèle chargé : ${health.model_loaded}`, cls: "warn" };
  }

  return (
    <>
      <header>
        <h1>Détection de fraude <span>en flux</span></h1>
        <nav>
          <button className={"tab" + (tab === "dash" ? " active" : "")} onClick={() => setTab("dash")}>Tableau de bord</button>
          <button className={"tab" + (tab === "test" ? " active" : "")} onClick={() => setTab("test")}>Test unitaire</button>
        </nav>
        <div className={pill[0]} title="État de l'API">{pill[1]}</div>
      </header>
      {banner && <div className={"banner " + banner.cls}>{banner.text}</div>}
      <main>
        {/* Dashboard reste monté pour conserver le polling et l'historique des alertes */}
        <div hidden={tab !== "dash"}><Dashboard onError={(m) => setHealthErr(m)} /></div>
        {tab === "test" && <TestForm />}
      </main>
    </>
  );
}
