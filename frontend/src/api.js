export const API = window.API_BASE || "http://localhost:8000/api/v1";
export const POLL_MS = window.POLL_MS || 3000;

export async function api(path, { method = "GET", body } = {}) {
  const r = await fetch(API + path, {
    method,
    headers: { "Content-Type": "application/json" },
    body: body ? JSON.stringify(body) : undefined,
  });
  if (!r.ok) {
    let detail = r.statusText;
    try {
      const j = await r.json();
      detail = Array.isArray(j.detail)
        ? j.detail.map((d) => `${(d.loc || []).slice(1).join(".")} : ${d.msg}`).join(" ; ")
        : j.detail || detail;
    } catch (_) { /* corps non JSON */ }
    const e = new Error(detail);
    e.status = r.status;
    throw e;
  }
  return r.json();
}

export const fmtInt = (n) => Number(n).toLocaleString("fr-FR");
export const fmtMoney = (n) => Number(n).toLocaleString("fr-FR", { maximumFractionDigits: 0 });
