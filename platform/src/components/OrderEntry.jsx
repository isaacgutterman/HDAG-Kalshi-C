import { useState } from "react";
import { api } from "../api.js";

export default function OrderEntry({ markets, onFilled }) {
  const [ticker, setTicker]   = useState("");
  const [side, setSide]       = useState("YES");
  const [size, setSize]       = useState(1);
  const [price, setPrice]     = useState(50);
  const [loading, setLoading] = useState(false);
  const [error, setError]     = useState("");
  const [lastFill, setLastFill] = useState(null);

  async function submit() {
    if (!ticker) return;
    setLoading(true);
    setError("");
    setLastFill(null);
    try {
      const fill = await api.placeOrder(ticker, side, Number(size), Number(price));
      setLastFill(fill);
      onFilled?.();
    } catch (e) {
      setError(e.message);
    }
    setLoading(false);
  }

  return (
    <div className="card">
      <div className="card-title">Place Order</div>

      <div className="form-row">
        {/* Market */}
        <div className="form-group">
          <label>Market</label>
          <select value={ticker} onChange={(e) => setTicker(e.target.value)} style={{ width: 220 }}>
            <option value="">— select —</option>
            {markets.map((m) => (
              <option key={m.ticker} value={m.ticker}>{m.ticker}</option>
            ))}
          </select>
        </div>

        {/* Side */}
        <div className="form-group">
          <label>Side</label>
          <select value={side} onChange={(e) => setSide(e.target.value)} style={{ width: 90 }}>
            <option value="YES">YES</option>
            <option value="NO">NO</option>
          </select>
        </div>

        {/* Size */}
        <div className="form-group">
          <label>Contracts</label>
          <input
            type="number"
            min={1} max={20}
            value={size}
            onChange={(e) => setSize(e.target.value)}
            style={{ width: 80 }}
          />
        </div>

        {/* Limit price */}
        <div className="form-group">
          <label>Limit (¢)</label>
          <input
            type="number"
            min={1} max={99}
            value={price}
            onChange={(e) => setPrice(e.target.value)}
            style={{ width: 80 }}
          />
        </div>

        <div className="form-group" style={{ justifyContent: "flex-end" }}>
          <button className="btn btn-primary" onClick={submit} disabled={!ticker || loading}>
            {loading ? "Placing…" : "Place Order"}
          </button>
        </div>
      </div>

      {error && <div className="error-box" style={{ marginTop: 10 }}>{error}</div>}

      {lastFill && (
        <div
          style={{
            marginTop: 10,
            padding: "8px 12px",
            background: "rgba(34,197,94,0.1)",
            border: "1px solid var(--green)",
            borderRadius: 6,
            fontSize: 12,
            color: "var(--green)",
          }}
        >
          ✓ Filled {lastFill.fill_qty} × {lastFill.side} @ {lastFill.avg_price.toFixed(1)}¢ —
          cost ${lastFill.total_cost.toFixed(3)}, fees ${lastFill.fees.toFixed(3)}
          {lastFill.status === "partial" && " (partial fill)"}
        </div>
      )}

      <p style={{ marginTop: 8, fontSize: 11, color: "var(--muted)" }}>
        Est. max cost: ${((Number(price) / 100) * Number(size)).toFixed(2)} · Fees: 7% of potential profit
      </p>
    </div>
  );
}
