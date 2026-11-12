/**
 * Utilitaires de formatage partagés et homogènes pour l'application Sentinel.
 */

export function fmtInt(n) {
  if (n === null || n === undefined || isNaN(n)) return "0";
  return Number(n).toLocaleString("fr-FR");
}

export function fmtCurrency(n) {
  if (n === null || n === undefined || isNaN(n)) return "0,00 $";
  return (
    Number(n).toLocaleString("fr-FR", {
      minimumFractionDigits: 2,
      maximumFractionDigits: 2,
    }) + " $"
  );
}

export function fmtPercent(n, digits = 2) {
  if (n === null || n === undefined || isNaN(n)) return "0,00 %";
  return (Number(n) * 100).toFixed(digits) + " %";
}

export function fmtLatency(ms) {
  if (ms === null || ms === undefined || isNaN(ms)) return "-";
  const num = Number(ms);
  if (num < 1000) return `${Math.round(num)} ms`;
  if (num < 60000) return `${(num / 1000).toFixed(1)} s`;
  const mins = Math.floor(num / 60000);
  const secs = Math.round((num % 60000) / 1000);
  return secs > 0 ? `${mins} min ${secs} s` : `${mins} min`;
}

export function fmtDate(isoStr) {
  if (!isoStr) return "-";
  try {
    const d = new Date(isoStr);
    return d.toLocaleTimeString("fr-FR", {
      hour: "2-digit",
      minute: "2-digit",
      second: "2-digit",
    });
  } catch {
    return isoStr;
  }
}
