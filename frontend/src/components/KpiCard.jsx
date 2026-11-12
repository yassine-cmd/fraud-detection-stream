export default function KpiCard({
  label,
  value,
  suffix,
  hint,
  tone = "neutral",
  trend,
}) {
  return (
    <div className={`metric-tile tone-${tone}`}>
      <span className="metric-label">{label}</span>
      <div className="metric-value-row">
        <span className="metric-value">{value}</span>
        {suffix && <span className="metric-suffix">{suffix}</span>}
      </div>
      <div className="metric-meta">
        {trend && (
          <span className={`metric-trend ${trend.direction || "neutral"}`}>
            {trend.value} <span className="trend-label">{trend.label}</span>
          </span>
        )}
        {hint && <span className="metric-hint">{hint}</span>}
      </div>
    </div>
  );
}
