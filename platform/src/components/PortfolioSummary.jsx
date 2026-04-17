export default function PortfolioSummary({ data }) {
  if (!data) return <div className="grid-4"><MetricCard label="Loading…" value="—" /></div>;

  const pnlClass = data.total_pnl > 0 ? "positive" : data.total_pnl < 0 ? "negative" : "neutral";
  const ddPct    = (data.max_drawdown * 100).toFixed(1);
  const returnPct = (((data.balance - data.starting_balance) / data.starting_balance) * 100).toFixed(2);

  return (
    <div className="grid-4">
      <MetricCard
        label="Balance"
        value={`$${data.balance.toFixed(2)}`}
        sub={`${returnPct}% return`}
        className={data.balance >= data.starting_balance ? "positive" : "negative"}
      />
      <MetricCard
        label="Total P&L"
        value={`${data.total_pnl >= 0 ? "+" : ""}$${data.total_pnl.toFixed(2)}`}
        sub={`R: $${data.realized_pnl.toFixed(2)} · U: $${data.unrealized_pnl.toFixed(2)}`}
        className={pnlClass}
      />
      <MetricCard
        label="Sharpe Ratio"
        value={data.sharpe_ratio != null ? data.sharpe_ratio.toFixed(2) : "—"}
        sub="annualised"
        className={data.sharpe_ratio > 1 ? "positive" : data.sharpe_ratio < 0 ? "negative" : "neutral"}
      />
      <MetricCard
        label="Max Drawdown"
        value={`${ddPct}%`}
        sub={`cap: ${(data.max_drawdown_limit * 100).toFixed(0)}%`}
        className={data.max_drawdown > 0.2 ? "negative" : "neutral"}
      />
    </div>
  );
}

function MetricCard({ label, value, sub, className = "neutral" }) {
  return (
    <div className="card metric-card">
      <div className="card-title">{label}</div>
      <div className={`metric-value ${className}`}>{value}</div>
      {sub && <div className="metric-sub">{sub}</div>}
    </div>
  );
}
