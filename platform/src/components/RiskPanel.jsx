import { useState } from "react";
import { api } from "../api.js";

export default function RiskPanel({ portfolio, strategies, onKill, onResume, onStrategyToggle }) {
  const [killing, setKilling] = useState(false);

  if (!portfolio) return <div className="card"><div className="empty">Loading…</div></div>;

  const dailyPct     = Math.min(1, Math.abs(portfolio.daily_loss) / portfolio.daily_loss_cap);
  const drawdownPct  = Math.min(1, portfolio.max_drawdown / portfolio.max_drawdown_limit);

  async function handleKill() {
    setKilling(true);
    try {
      if (portfolio.killed) {
        await api.resume();
        onResume?.();
      } else {
        await api.kill();
        onKill?.();
      }
    } catch (_) {}
    setKilling(false);
  }

  return (
    <div className="card" style={{ minWidth: 240 }}>
      <div className="card-title">Risk Monitor</div>

      {/* Daily loss gauge */}
      <GaugeRow
        label="Daily Loss"
        value={`$${Math.abs(portfolio.daily_loss).toFixed(2)}`}
        cap={`/ $${portfolio.daily_loss_cap.toFixed(0)}`}
        pct={dailyPct}
        color={dailyPct > 0.75 ? "var(--red)" : dailyPct > 0.5 ? "var(--yellow)" : "var(--green)"}
      />

      {/* Drawdown gauge */}
      <GaugeRow
        label="Max Drawdown"
        value={`${(portfolio.max_drawdown * 100).toFixed(1)}%`}
        cap={`/ ${(portfolio.max_drawdown_limit * 100).toFixed(0)}%`}
        pct={drawdownPct}
        color={drawdownPct > 0.75 ? "var(--red)" : drawdownPct > 0.5 ? "var(--yellow)" : "var(--green)"}
      />

      {/* Strategy toggles */}
      <div style={{ marginTop: 14 }}>
        <div className="card-title" style={{ marginBottom: 6 }}>Strategies</div>
        {Object.entries(strategies).map(([name, enabled]) => (
          <div
            key={name}
            style={{
              display: "flex",
              alignItems: "center",
              justifyContent: "space-between",
              marginBottom: 6,
            }}
          >
            <span style={{ fontSize: 12, color: "var(--muted)", fontFamily: "monospace" }}>
              {name}
            </span>
            <ToggleSwitch
              enabled={enabled}
              onChange={() => onStrategyToggle?.(name)}
            />
          </div>
        ))}
      </div>

      {/* Kill switch */}
      <div style={{ marginTop: 16 }}>
        <button
          className={`kill-btn ${portfolio.killed ? "killed" : ""}`}
          onClick={handleKill}
          disabled={killing}
        >
          {killing ? "…" : portfolio.killed ? "⚡ RESUME TRADING" : "⚠ KILL SWITCH"}
        </button>
        {portfolio.killed && (
          <p style={{ marginTop: 6, fontSize: 11, color: "var(--red)", textAlign: "center" }}>
            All positions cleared — trading halted
          </p>
        )}
      </div>
    </div>
  );
}

function GaugeRow({ label, value, cap, pct, color }) {
  return (
    <div style={{ marginBottom: 12 }}>
      <div style={{ display: "flex", justifyContent: "space-between", fontSize: 12, marginBottom: 2 }}>
        <span style={{ color: "var(--muted)" }}>{label}</span>
        <span>
          <span style={{ color }}>{value}</span>
          <span style={{ color: "var(--muted)" }}> {cap}</span>
        </span>
      </div>
      <div className="progress-bar">
        <div
          className="progress-fill"
          style={{ width: `${(pct * 100).toFixed(1)}%`, background: color }}
        />
      </div>
    </div>
  );
}

function ToggleSwitch({ enabled, onChange }) {
  return (
    <div
      onClick={onChange}
      style={{
        width: 36,
        height: 20,
        borderRadius: 10,
        background: enabled ? "var(--green)" : "var(--border)",
        position: "relative",
        cursor: "pointer",
        transition: "background 0.2s",
      }}
    >
      <div
        style={{
          position: "absolute",
          top: 3,
          left: enabled ? 18 : 3,
          width: 14,
          height: 14,
          borderRadius: "50%",
          background: "#fff",
          transition: "left 0.2s",
        }}
      />
    </div>
  );
}
