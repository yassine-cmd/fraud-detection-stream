import { fmtMoney } from "../api.js";

export default function AlertsTable({ alerts, newIds }) {
  return (
    <div className="table-wrap">
      <table>
        <thead><tr><th>Heure (UTC)</th><th>Transaction</th><th>Type</th>
          <th className="num">Montant</th><th className="num">Probabilité</th><th>Modèle</th></tr></thead>
        <tbody>
          {alerts.length === 0 && <tr><td colSpan={6} className="empty">Aucune alerte</td></tr>}
          {alerts.map((a) => (
            <tr key={a.transaction_id} className={newIds.has(a.transaction_id) ? "new" : ""}>
              <td>{a.timestamp.replace("T", " ").replace("Z", "").slice(0, 23)}</td>
              <td>{a.transaction_id}</td><td>{a.type}</td>
              <td className="num">{fmtMoney(a.amount)}</td>
              <td className="num">{a.probability.toFixed(3)}</td>
              <td>{a.model_version}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}
