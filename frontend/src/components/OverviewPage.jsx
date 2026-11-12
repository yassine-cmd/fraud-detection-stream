import { useState } from "react";
import { fmtInt, fmtLatency, fmtMoney, fmtMoneyCompact, fmtPct } from "../api.js";
import { IconArrowUpRight, IconBell, IconGauge } from "../icons.jsx";
import AlertsTable from "./AlertsTable.jsx";
import AlertDrawer from "./AlertDrawer.jsx";
import KpiCard from "./KpiCard.jsx";
import SystemHealth from "./SystemHealth.jsx";
import TrafficChart from "./TrafficChart.jsx";
import TypeBreakdown from "./TypeBreakdown.jsx";

export default function OverviewPage({
  data,
  health,
  healthError,
  model,
  windowRange,
  onWindowRange,
  onNavigate,
  onNotify,
  selectedAlert: propSelectedAlert,
  onSelectAlert: propOnSelectAlert,
}) {
  const { stats, points, alerts, stream, breakdown, latency, error, newIds } = data;
  const [localSelectedAlert, setLocalSelectedAlert] = useState(null);

  const selectedAlert = propSelectedAlert !== undefined ? propSelectedAlert : localSelectedAlert;
  const setSelectedAlert = propOnSelectAlert || setLocalSelectedAlert;

  const reference = points.length > 1 ? points[points.length - 2] : points[0];
  const previous = points.length > 2 ? points[points.length - 3] : null;
  const throughput = reference ? Math.round(reference.tx / 10) : 0;
  const deltaTx = reference && previous ? reference.tx - previous.tx : null;
  const deltaFrauds = reference && previous ? reference.frauds - previous.frauds : null;
  const windowTx = points.reduce((sum, point) => sum + point.tx, 0);
  const windowFrauds = points.reduce((sum, point) => sum + point.frauds, 0);
  const windowRate = windowTx ? windowFrauds / windowTx : 0;

  return (
    <div className="page-stack">
      {error && (
        <div className="global-alert" role="alert">
          <IconGauge size={16} />
          <span>{error}</span>
        </div>
      )}

      {/* 1. Seamless Executive Metric Strip (No card fatigue) */}
      <section className="metric-strip" aria-label="Indicateurs clés de performance">
        <KpiCard
          label="Transactions analysées"
          value={fmtInt(stats?.total_tx)}
          tone="neutral"
          trend={
            throughput > 0
              ? {
                  value: `${fmtInt(throughput)} tx/s`,
                  label: "débit instantané",
                  direction: "up",
                }
              : null
          }
        />
        <KpiCard
          label="Fraudes interceptées"
          value={fmtInt(stats?.total_frauds)}
          tone="fraud"
          hint={`${fmtPct(stats?.fraud_rate, 2)} du volume filtré`}
          trend={
            deltaFrauds !== null && deltaFrauds > 0
              ? {
                  value: `+${fmtInt(deltaFrauds)}`,
                  label: "nouvelles",
                  direction: "down",
                }
              : null
          }
        />
        <KpiCard
          label="Taux de fraude"
          value={stats ? (Number(stats.fraud_rate) * 100).toFixed(2).replace(".", ",") : "—"}
          suffix="%"
          tone="warning"
          hint={`Seuil décisionnel : ${model ? fmtPct(model.threshold, 1) : "94,5 %"}`}
        />
        <KpiCard
          label="Montant intercepté"
          value={fmtMoneyCompact(stats?.fraud_amount)}
          tone="legit"
          hint="Cumul des fraudes bloquées (rétention 24h)"
        />
      </section>

      {/* 2. Primary Analytics Dual-Pane: Traffic Ingestion (64%) vs Risk Breakdown (36%) */}
      <div className="analytics-grid">
        <section className="card chart-card">
          <div className="card-heading">
            <div>
              <span className="eyebrow">Pipeline temps réel</span>
              <h2>Débit d'ingestion & Détections</h2>
            </div>
            <div className="chart-head-actions">
              <span className="live-pill">
                <i /> Live · 3 s
              </span>
              <div className="segmented" role="group" aria-label="Fenêtre temporelle">
                {[
                  ["5m", "5 min"],
                  ["15m", "15 min"],
                  ["1h", "1 h"],
                ].map(([value, label]) => (
                  <button
                    key={value}
                    type="button"
                    className={windowRange === value ? "active" : ""}
                    onClick={() => onWindowRange(value)}
                  >
                    {label}
                  </button>
                ))}
              </div>
            </div>
          </div>

          <TrafficChart points={points} />

          <div className="chart-stats">
            <div>
              <span>Débit moyen</span>
              <strong>{fmtInt(throughput)} tx/s</strong>
            </div>
            <div>
              <span>Fraudes bloquées</span>
              <strong className="text-rose">{fmtInt(windowFrauds)}</strong>
            </div>
            <div className="chart-latency">
              <span>Latence P95 flux</span>
              <strong>{latency?.p95_ms ? fmtLatency(latency.p95_ms) : "—"}</strong>
            </div>
          </div>
        </section>

        <TypeBreakdown rows={breakdown} />
      </div>

      {/* 3. Horizontal Infrastructure Telemetry Strip */}
      <SystemHealth
        health={health}
        healthError={healthError}
        stream={stream}
        streamError={data.streamError}
      />

      {/* 4. Threat Watchlist (Top 5 Critical Incidents) */}
      <section className="card alerts-card full-width">
        <div className="card-heading">
          <div>
            <span className="eyebrow">Surveillance des menaces</span>
            <h2>Incidents critiques récents (Top 5)</h2>
          </div>
          <div className="heading-actions">
            <button type="button" className="btn btn-ghost" onClick={() => onNavigate("alerts")}>
              Accéder au registre de triage ({fmtInt(alerts.length)}) <IconArrowUpRight size={14} />
            </button>
          </div>
        </div>
        <AlertsTable
          alerts={alerts.slice(0, 5)}
          newIds={newIds}
          full={false}
          onSelectAlert={setSelectedAlert}
          selectedId={selectedAlert?.transaction_id}
          onNotify={onNotify}
        />
        {!alerts.length && (
          <div className="alerts-teaser">
            <IconBell size={15} />
            <span>Aucune transaction frauduleuse détectée dans l'intervalle actif.</span>
          </div>
        )}
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
