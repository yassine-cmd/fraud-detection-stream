import { useRef, useState } from "react";
import { api, POLL_MS } from "./api";
import usePolling from "./usePolling";

/**
 * Données temps réel partagées par toutes les pages.
 * - polling rapide (3 s) : compteurs, série, alertes, simulateur ;
 * - polling lent (15 s) : répartition par type et latences.
 */
export default function useLiveData(windowRange) {
  const [stats, setStats] = useState(null);
  const [points, setPoints] = useState([]);
  const [alerts, setAlerts] = useState([]);
  const [stream, setStream] = useState(null);
  const [breakdown, setBreakdown] = useState([]);
  const [latency, setLatency] = useState(null);
  const [error, setError] = useState(null);
  const [insightsError, setInsightsError] = useState(null);
  const [streamError, setStreamError] = useState(null);
  const [lastUpdated, setLastUpdated] = useState(null);
  const [loading, setLoading] = useState(true);
  const [newIds, setNewIds] = useState(() => new Set());
  const knownIds = useRef(null);

  async function fetchFast() {
    const [statsRes, seriesRes, alertsRes, streamRes] = await Promise.allSettled([
      api("/stats"),
      api(`/stats/timeseries?window=${windowRange}&bucket=10s`),
      api("/alerts/latest?limit=100"),
      api("/stream/status"),
    ]);

    let firstError = null;
    if (statsRes.status === "fulfilled") setStats(statsRes.value);
    else firstError = firstError || statsRes.reason;

    if (seriesRes.status === "fulfilled") setPoints(seriesRes.value.points || []);
    else firstError = firstError || seriesRes.reason;

    if (alertsRes.status === "fulfilled") {
      const nextAlerts = alertsRes.value || [];
      const ids = new Set(nextAlerts.map((item) => item.transaction_id));
      if (knownIds.current === null) {
        setNewIds(new Set());
      } else {
        setNewIds(new Set([...ids].filter((id) => !knownIds.current.has(id))));
      }
      knownIds.current = ids;
      setAlerts(nextAlerts);
    } else {
      firstError = firstError || alertsRes.reason;
    }

    if (streamRes.status === "fulfilled") {
      setStream(streamRes.value);
      setStreamError(null);
    } else {
      setStreamError(streamRes.reason?.message || "Simulateur indisponible");
    }

    setError(firstError ? firstError.message : null);
    setLoading(false);
    setLastUpdated(new Date());
  }

  async function fetchInsights() {
    const [breakdownRes, latencyRes] = await Promise.allSettled([
      api(`/stats/breakdown?window=${windowRange}`),
      api(`/stats/latency?window=${windowRange}`),
    ]);
    let firstError = null;
    if (breakdownRes.status === "fulfilled") setBreakdown(breakdownRes.value.by_type || []);
    else firstError = firstError || breakdownRes.reason;

    if (latencyRes.status === "fulfilled") setLatency(latencyRes.value);
    else firstError = firstError || latencyRes.reason;

    setInsightsError(firstError ? firstError.message : null);
  }

  usePolling(fetchFast, POLL_MS, [windowRange]);
  usePolling(fetchInsights, 15000, [windowRange]);

  return {
    stats,
    points,
    alerts,
    stream,
    breakdown,
    latency,
    error,
    insightsError,
    streamError,
    lastUpdated,
    loading,
    newIds,
    setStream,
    refresh: fetchFast,
  };
}
