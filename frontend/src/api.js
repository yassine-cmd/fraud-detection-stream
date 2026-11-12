/* Client HTTP unique du front : aucune logique ML ici (SNF4). */
const RAW_BASE =
  typeof window !== "undefined" && window.API_BASE ? window.API_BASE : "/api/v1";

export const API = String(RAW_BASE).replace(/\/+$/, "");
export const POLL_MS = Number(window.POLL_MS) || 3000;

export async function api(path, { method = "GET", body, signal } = {}) {
  let response;
  try {
    response = await fetch(API + path, {
      method,
      signal,
      cache: "no-store",
      headers: body ? { "Content-Type": "application/json" } : undefined,
      body: body ? JSON.stringify(body) : undefined,
    });
  } catch (error) {
    if (error.name === "AbortError") throw error;
    throw new Error("API injoignable — vérifiez que le service api est démarré.");
  }

  if (!response.ok) {
    let detail = `${response.status} ${response.statusText}`;
    try {
      const payload = await response.json();
      if (Array.isArray(payload.detail)) {
        detail = payload.detail
          .map((item) => {
            const field = (item.loc || []).slice(1).join(".");
            return field ? `${field} : ${item.msg}` : item.msg;
          })
          .join(" ; ");
      } else if (payload.detail) {
        detail = typeof payload.detail === "string" ? payload.detail : JSON.stringify(payload.detail);
      }
    } catch {
      /* corps non JSON */
    }
    const error = new Error(detail);
    error.status = response.status;
    throw error;
  }

  if (response.status === 204) return null;
  return response.json();
}

export function docsUrl() {
  if (/^https?:\/\//i.test(API)) {
    return API.replace(/\/api\/v1\/?$/i, "") + "/docs";
  }
  return `${window.location.protocol}//${window.location.hostname}:8000/docs`;
}

export const fmtInt = (value) =>
  value === null || value === undefined || Number.isNaN(Number(value))
    ? "—"
    : Number(value).toLocaleString("fr-FR");

export const fmtMoney = (value) =>
  value === null || value === undefined || Number.isNaN(Number(value))
    ? "—"
    : `${Number(value).toLocaleString("fr-FR", { maximumFractionDigits: 0 })} $`;

export const fmtMoneyCompact = (value) => {
  const n = Number(value);
  if (!Number.isFinite(n)) return "—";
  if (n >= 1e9) return `${(n / 1e9).toFixed(2).replace(".", ",")} Md $`;
  if (n >= 1e6) return `${(n / 1e6).toFixed(1).replace(".", ",")} M $`;
  if (n >= 1e3) return `${(n / 1e3).toFixed(0)} k $`;
  return `${Number(n.toFixed(0)).toLocaleString("fr-FR")} $`;
};

export const fmtProb = (value) => {
  const n = Number(value);
  if (!Number.isFinite(n)) return "—";
  const pct = n * 100;
  if (pct >= 99.99 && pct < 100) return `${pct.toFixed(2).replace(".", ",")} %`;
  if (pct >= 99.9 && pct < 100) return `${pct.toFixed(2).replace(".", ",")} %`;
  if (pct < 0.01 && pct > 0) return "< 0,01 %";
  return `${pct.toFixed(2).replace(".", ",")} %`;
};

export const fmtLatency = (ms) => {
  const n = Number(ms);
  if (!Number.isFinite(n) || n <= 0) return "—";
  if (n < 1000) return `${Math.round(n)} ms`;
  if (n < 60000) return `${(n / 1000).toFixed(1).replace(".", ",")} s`;
  const mins = Math.floor(n / 60000);
  const secs = Math.round((n % 60000) / 1000);
  return `${mins} min ${secs} s`;
};

export const fmtCompact = (value) => {
  const n = Number(value);
  if (!Number.isFinite(n)) return "—";
  return Intl.NumberFormat("fr-FR", { notation: "compact", maximumFractionDigits: 1 }).format(n);
};

export const fmtPct = (value, digits = 2) =>
  value === null || value === undefined || Number.isNaN(Number(value))
    ? "—"
    : `${(Number(value) * 100).toFixed(digits).replace(".", ",")} %`;

export const fmtDuration = (seconds) => {
  const total = Math.max(0, Math.floor(Number(seconds) || 0));
  const h = Math.floor(total / 3600);
  const m = Math.floor((total % 3600) / 60);
  const s = total % 60;
  if (h) return `${h} h ${String(m).padStart(2, "0")} min`;
  if (m) return `${m} min ${String(s).padStart(2, "0")} s`;
  return `${s} s`;
};

export const fmtTimeUTC = (iso) => {
  if (!iso || typeof iso !== "string") return "—";
  const match = iso.match(/T(\d{2}:\d{2}:\d{2})/);
  return match ? match[1] : iso.slice(11, 19);
};

export const fmtDateUTC = (iso) => {
  if (!iso || typeof iso !== "string") return "—";
  return `${iso.slice(0, 10)} ${fmtTimeUTC(iso)} UTC`;
};

export const shortId = (id, size = 18) => {
  if (!id) return "—";
  const text = String(id);
  return text.length <= size ? text : `${text.slice(0, size)}…`;
};

export const pctWidth = (value) => `${Math.max(0, Math.min(100, Number(value) * 100))}%`;

export function getSeverity(probability) {
  const p = Number(probability) || 0;
  if (p >= 0.95) return { key: "CRITICAL", label: "Critique", tone: "critical" };
  if (p >= 0.8) return { key: "HIGH", label: "Élevée", tone: "high" };
  if (p >= 0.6) return { key: "MEDIUM", label: "Moyenne", tone: "medium" };
  return { key: "LOW", label: "Faible", tone: "low" };
}
