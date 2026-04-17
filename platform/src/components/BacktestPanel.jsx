import { useState } from "react";
import {
  AreaChart, Area, XAxis, YAxis, CartesianGrid,
  Tooltip, ReferenceLine, ResponsiveContainer,
} from "recharts";
import { api } from "../api.js";

const STRATEGIES = ["mean_reversion", "momentum"];

export default function BacktestPanel({ markets }) {
  const [ticker,    setTicker]    = useState("");
  const [strategy,  setStrategy]  = useState("mean_reversion");
  const [lookback,  setLookback]  = useState(20);
  const [threshold, setThreshold] = useState(0.08);
  const [halfKelly, setHalfKelly] = useState(true);
  const [loading,   setLoading]   = useState(false);
  const [result,    setResult]    = useState(null);
  const [error,     setError]     = useState("");

  async function run() {
    if (!ticker) return;
    setLoading(true);
    setError("");
    setResult(null);
    try {
      const r = await api.runBacktest({
        ticker,
        strategy,
        lookback:       Number(lookback),
        edge_threshold: Number(threshold),
        half_kelly:     halfKelly,
      });
      setResult(r);
    } catch (e) {
      setError(e.message);
    }
    setLoading(false);
  }

  const chartData = result?.balance_curve?.map((p) => ({
    t: p.t,
    balance: p.balance,
  })) ?? [];

  const pnlPositive = result && result.total_pnl >= 0;

  return (
    <div className="section">
      {/* Config */}
      <div className="card">
        <div className="card-title">Backtest Configuration</div>
        <div className="form-row">
          <div className="form-group">
            <label>Market Ticker</label>
            <select value={ticker} onChange={(e) => setTicker(e.target.value)} style={{ width: 220 }}>
              <option value="">— select —</option>
              {markets.map((m) => (
                <option key={m.ticker} value={m.ticker}>{m.ticker}</option>
              ))}
            </select>
          </div>

          <div className="form-group">
            <label>Strategy</label>
            <select value={strategy} onChange={(e) => setStrategy(e.target.value)}>
              {STRATEGIES.map((s) => (
                <option key={s} value={s}>{s}</option>
              ))}
            </select>
          </div>

          <div className="form-group">
            <label>Lookback (bars)</label>
            <input
              type="number" min={5} max={200}
              value={lookback}
              onChange={(e) => setLookback(e.target.value)}
              style={{ width: 90 }}
            />
          </div>

          <div className="form-group">
            <label>Edge Threshold</label>
            <input
              type="number" min={0.01} max={0.5} step={0.01}
              value={threshold}
              onChange={(e) => setThreshold(e.target.value)}
              style={{ width: 90 }}
            />
          </div>

          <div className="form-group">
            <label>Half-Kelly</label>
            <div style={{ display: "flex", alignItems: "center", gap: 8, marginTop: 4 }}>
              <input
                type="checkbox"
                checked={halfKelly}
                onChange={(e) => setHalfKelly(e.target.checked)}
                style={{ width: "auto" }}
              />
              <span style={{ fontSize: 12, color: "var(--muted)" }}>enabled</span>
            </div>
          </div>

          <div className="form-group" style={{ justifyContent: "flex-end" }}>
            <button className="btn btn-primary" onClick={run} disabled={!ticker || loading}>
              {loading ? "Running…" : "▶ Run Backtest"}
            </button>
          </div>
        </div>

        <p style={{ marginTop: 8, fontSize: 11, color: "var(--muted)" }}>
          Walk-forward only — no look-ahead bias. Train on t=0..i-1, signal at t=i, evaluate at t=i+1.
        </p>
      </div>

      {error && <div className="error-box">{error}</div>}

      {result && (
        <>
          {/* Metrics */}
          <div className="grid-4">
            <MetricCard label="Final Balance"    value={`$${result.final_balance.toFixed(2)}`}    sub={`started $${result.starting_balance}`} color={pnlPositive ? "positive" : "negative"} />
            <MetricCard label="Total Return"     value={`${result.total_return_pct >= 0 ? "+" : ""}${result.total_return_pct.toFixed(1)}%`}  color={pnlPositive ? "positive" : "negative"} />
            <MetricCard label="Sharpe Ratio"     value={result.sharpe_ratio.toFixed(2)} sub="walk-forward" color={result.sharpe_ratio > 1 ? "positive" : "neutral"} />
            <MetricCard label="Max Drawdown"     value={`${(result.max_drawdown * 100).toFixed(1)}%`} color={result.max_drawdown > 0.2 ? "negative" : "neutral"} />
            <MetricCard label="Total Trades"     value={result.total_trades} />
            <MetricCard label="Win Rate"         value={`${(result.win_rate * 100).toFixed(0)}%`} color={result.win_rate > 0.5 ? "positive" : "negative"} />
            <MetricCard label="Avg P&L / Trade"  value={`${result.avg_pnl_per_trade >= 0 ? "+" : ""}$${result.avg_pnl_per_trade.toFixed(4)}`} color={result.avg_pnl_per_trade >= 0 ? "positive" : "negative"} />
            <MetricCard label="Edge Threshold"   value={`${(result.edge_threshold * 100).toFixed(0)}%`} sub={result.strategy} />
          </div>

          {/* Balance curve */}
          <div className="card">
            <div className="card-title">Balance Curve — {result.ticker} / {result.strategy}</div>
            <ResponsiveContainer width="100%" height={260}>
              <AreaChart data={chartData} margin={{ top: 8, right: 16, bottom: 0, left: 0 }}>
                <defs>
                  <linearGradient id="balGrad" x1="0" y1="0" x2="0" y2="1">
                    <stop offset="5%"  stopColor={pnlPositive ? "#22c55e" : "#ef4444"} stopOpacity={0.3} />
                    <stop offset="95%" stopColor={pnlPositive ? "#22c55e" : "#ef4444"} stopOpacity={0} />
                  </linearGradient>
                </defs>
                <CartesianGrid stroke="#334155" strokeDasharray="3 3" vertical={false} />
                <XAxis dataKey="t" tick={{ fontSize: 10, fill: "#94a3b8" }} tickLine={false} axisLine={false} label={{ value: "trade #", position: "insideBottomRight", offset: -5, fill: "#94a3b8", fontSize: 10 }} />
                <YAxis tick={{ fontSize: 10, fill: "#94a3b8" }} tickLine={false} axisLine={false} tickFormatter={(v) => `$${v.toFixed(0)}`} />
                <Tooltip
                  contentStyle={{ background: "#1e293b", border: "1px solid #334155", borderRadius: 6, fontSize: 12 }}
                  formatter={(v) => [`$${v.toFixed(4)}`, "Balance"]}
                />
                <ReferenceLine y={100} stroke="#94a3b8" strokeDasharray="4 4" label={{ value: "start", fill: "#94a3b8", fontSize: 10 }} />
                <Area
                  type="monotone" dataKey="balance"
                  stroke={pnlPositive ? "#22c55e" : "#ef4444"}
                  strokeWidth={2}
                  fill="url(#balGrad)"
                  dot={false}
                />
              </AreaChart>
            </ResponsiveContainer>
          </div>

          {/* Recent trades table */}
          <div className="card">
            <div className="card-title">Recent Backtest Trades (last 50)</div>
            <div className="table-wrap" style={{ maxHeight: 240, overflowY: "auto" }}>
              <table>
                <thead>
                  <tr>
                    <th>#</th>
                    <th>Side</th>
                    <th>Qty</th>
                    <th>Avg Price</th>
                    <th>Model Prob</th>
                    <th>P&L</th>
                    <th>Balance</th>
                  </tr>
                </thead>
                <tbody>
                  {result.recent_trades.map((t, i) => (
                    <tr key={i}>
                      <td style={{ color: "var(--muted)" }}>{t.i}</td>
                      <td><span className={`badge badge-${t.side.toLowerCase()}`}>{t.side}</span></td>
                      <td>{t.qty}</td>
                      <td>{t.avg_price.toFixed(1)}¢</td>
                      <td style={{ color: "var(--blue)" }}>{(t.model_prob * 100).toFixed(1)}%</td>
                      <td className={t.pnl >= 0 ? "positive" : "negative"}>
                        {t.pnl >= 0 ? "+" : ""}${t.pnl.toFixed(4)}
                      </td>
                      <td>${t.balance.toFixed(3)}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </div>
        </>
      )}
    </div>
  );
}

function MetricCard({ label, value, sub, color = "neutral" }) {
  return (
    <div className="card metric-card">
      <div className="card-title">{label}</div>
      <div className={`metric-value ${color}`} style={{ fontSize: 20 }}>{value}</div>
      {sub && <div className="metric-sub">{sub}</div>}
    </div>
  );
}
