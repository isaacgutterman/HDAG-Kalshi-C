import { useState } from "react";
import { api } from "../api.js";

export default function TradeLog({ trades, markets }) {
  const [watchTicker, setWatchTicker] = useState("");
  const [feed, setFeed]               = useState([]);
  const [feedLoading, setFeedLoading] = useState(false);

  async function loadFeed(ticker) {
    if (!ticker) return;
    setFeedLoading(true);
    try {
      const data = await api.getMarketFeed(ticker);
      setFeed(data);
    } catch (_) {}
    setFeedLoading(false);
  }

  return (
    <div className="grid-2" style={{ marginTop: 0 }}>
      {/* Trade log */}
      <div className="card">
        <div className="card-title">Trade Log ({trades.length})</div>
        {trades.length === 0 ? (
          <div className="empty">No trades yet — place an order above</div>
        ) : (
          <div className="table-wrap" style={{ maxHeight: 260, overflowY: "auto" }}>
            <table>
              <thead>
                <tr>
                  <th>Time</th>
                  <th>Ticker</th>
                  <th>Side</th>
                  <th>Qty</th>
                  <th>Price</th>
                  <th>P&L</th>
                  <th>Action</th>
                </tr>
              </thead>
              <tbody>
                {trades.map((t, i) => {
                  const pnlClass = t.pnl > 0 ? "positive" : t.pnl < 0 ? "negative" : "neutral";
                  return (
                    <tr key={i}>
                      <td style={{ color: "var(--muted)", fontSize: 11 }}>
                        {new Date(t.timestamp).toLocaleTimeString()}
                      </td>
                      <td style={{ fontFamily: "monospace", fontSize: 11 }}>{t.ticker}</td>
                      <td><span className={`badge badge-${t.side.toLowerCase()}`}>{t.side}</span></td>
                      <td>{t.qty}</td>
                      <td>{t.avg_price.toFixed(1)}¢</td>
                      <td className={pnlClass}>
                        {t.action === "CLOSE"
                          ? `${t.pnl >= 0 ? "+" : ""}$${t.pnl.toFixed(3)}`
                          : "—"}
                      </td>
                      <td>
                        <span
                          style={{
                            fontSize: 10,
                            padding: "1px 5px",
                            borderRadius: 3,
                            background: t.action === "OPEN" ? "rgba(59,130,246,.2)" : "rgba(34,197,94,.2)",
                            color: t.action === "OPEN" ? "var(--blue)" : "var(--green)",
                          }}
                        >
                          {t.action}
                        </span>
                      </td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          </div>
        )}
      </div>

      {/* Market feed */}
      <div className="card">
        <div className="card-title">Live Market Feed</div>
        <div className="form-row" style={{ marginBottom: 12 }}>
          <select
            value={watchTicker}
            onChange={(e) => setWatchTicker(e.target.value)}
            style={{ flex: 1, width: "auto" }}
          >
            <option value="">— select market —</option>
            {markets.map((m) => (
              <option key={m.ticker} value={m.ticker}>{m.ticker}</option>
            ))}
          </select>
          <button
            className="btn btn-ghost"
            onClick={() => loadFeed(watchTicker)}
            disabled={!watchTicker || feedLoading}
          >
            {feedLoading ? "…" : "Refresh"}
          </button>
        </div>

        {feed.length === 0 ? (
          <div className="empty">Select a market and click Refresh</div>
        ) : (
          <div className="table-wrap" style={{ maxHeight: 220, overflowY: "auto" }}>
            <table>
              <thead>
                <tr>
                  <th>Time</th>
                  <th>YES Price</th>
                  <th>Size</th>
                  <th>Taker</th>
                  <th>Phase</th>
                </tr>
              </thead>
              <tbody>
                {feed.map((t, i) => (
                  <tr key={i}>
                    <td style={{ color: "var(--muted)", fontSize: 11 }}>
                      {new Date(t.timestamp).toLocaleTimeString()}
                    </td>
                    <td>{t.yes_price}¢</td>
                    <td>{t.size}</td>
                    <td>
                      <span className={`badge badge-${(t.taker_side || "").toLowerCase()}`}>
                        {t.taker_side?.toUpperCase() ?? "—"}
                      </span>
                    </td>
                    <td style={{ color: "var(--muted)", fontSize: 11 }}>{t.game_phase}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </div>
    </div>
  );
}
