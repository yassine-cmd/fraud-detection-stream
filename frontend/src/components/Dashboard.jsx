import { useRef, useState } from "react";
import { api, fmtInt, fmtMoney, POLL_MS } from "../api.js";
import usePolling from "../usePolling.js";
import TrafficChart from "./TrafficChart.jsx";
import SimulatorPanel from "./SimulatorPanel.jsx";
import AlertsTable from "./AlertsTable.jsx";

const BUCKET = 10;

export default function Dashboard() {
  const [win, setWin] = useState("15m");
  const [stats, setStats] = useState(null);
  const [points, setPoints] = useState([]);
  const [alerts, setAlerts] = useState([]);
  const [sim, setSim] = useState(null);
  const [status, setStatus] = useState("");
  const knownIds = useRef(null); // null => premier chargement (pas de surbrillance)
  const [newIds, setNewIds] = useState(new Set());

  usePolling(async () => {
    try {
      const [s, ts, al, st] = await Promise.all([
        api("/stats"), api(`/stats/timeseries?window=${win}&bucket=${BUCKET}s`),
        api("/alerts/latest?limit=20"), api("/stream/status").catch(() => null),
      ]);
      setStats(s); setPoints(ts.points); setAlerts(al); if (st) setSim(st);
      const ids = new Set(al.map((a) => a.transaction_id));
      setNewIds(knownIds.current ? new Set([...ids].filter((i) => !knownIds.current.has(i))) : new Set());
      knownIds.current = ids;
      setStatus(`Dernier rafraîchissement : ${new Date().toLocaleTimeString("fr-FR")} (toutes les ${POLL_MS / 1000} s)`);
    } catch (e) {
      setStatus("Erreur de rafraîchissement : " + e.message);
    }
  }, POLL_MS, [win]);

  // débit : avant-dernier bucket (le dernier est en cours de remplissage)
  const ref = points.length > 1 ? points[points.length - 2] : points[0];
  const tps = ref ? fmtInt(Math.round(ref.tx / BUCKET)) + " tx/s" : "–";

  return (
    <section className="panel">
      <div className="cards">
        <Card label="Transactions" v={stats ? fmtInt(stats.total_tx) : "–"} />
        <Card label="Fraudes détectées" v={stats ? fmtInt(stats.total_frauds) : "–"} />
        <Card label="Taux de fraude" v={stats ? (stats.fraud_rate * 100).toFixed(3) + " %" : "–"} />
        <Card label="Montant frauduleux" v={stats ? fmtMoney(stats.fraud_amount) : "–"} />
        <Card label="Débit (dernière fenêtre)" v={tps} />
      </div>
      <div className="grid2">
        <div className="box">
          <div className="box-h">
            <h2>Évolution</h2>
            <select id="window" value={win} onChange={(e) => setWin(e.target.value)} aria-label="Fenêtre">
              <option value="5m">5 min</option><option value="15m">15 min</option><option value="1h">1 h</option>
            </select>
          </div>
          <TrafficChart points={points} />
        </div>
        <SimulatorPanel status={sim} onStatus={setSim} />
      </div>
      <div className="box">
        <h2>Dernières alertes</h2>
        <AlertsTable alerts={alerts} newIds={newIds} />
      </div>
      <p className="hint">{status}</p>
    </section>
  );
}

const Card = ({ label, v }) => (<div className="card"><label>{label}</label><b>{v}</b></div>);
