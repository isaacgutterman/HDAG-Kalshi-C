import { useState, useEffect, useCallback } from "react";
import { api } from "./api.js";
import PortfolioSummary from "./components/PortfolioSummary.jsx";
import PositionsTable   from "./components/PositionsTable.jsx";
import TradeLog         from "./components/TradeLog.jsx";
import OrderEntry       from "./components/OrderEntry.jsx";
import RiskPanel        from "./components/RiskPanel.jsx";
import BacktestPanel    from "./components/BacktestPanel.jsx";

const POLL_MS = 2500;

export default function App() {
  const [tab,        setTab]        = useState("dashboard");
  const [portfolio,  setPortfolio]  = useState(null);
  const [positions,  setPositions]  = useState([]);
  const [trades,     setTrades]     = useState([]);
  const [markets,    setMarkets]    = useState([]);
  const [strategies, setStrategies] = useState({});
  const [toast,      setToast]      = useState(null);
  const [lastPoll,   setLastPoll]   = useState(null);

  // ── Data fetching ──────────────────────────────────────────────────────────

  const refresh = useCallback(async () => {
    try {
      const [port, pos, trd] = await Promise.all([
        api.getPortfolio(),
        api.getPositions(),
        api.getTrades(60),
      ]);
      setPortfolio(port);
      setPositions(pos);
      setTrades(trd);
      setStrategies(port.strategies ?? {});
      setLastPoll(new Date().toLocaleTimeString());
    } catch (e) {
      // Silently ignore poll errors — server may be starting up
    }
  }, []);

  // Initial load — also fetch markets (slow-changing)
  useEffect(() => {
    refresh();
    api.getMarkets(100).then(setMarkets).catch(() => {});
  }, [refresh]);

  // Live poll
  useEffect(() => {
    const id = setInterval(refresh, POLL_MS);
    return () => clearInterval(id);
  }, [refresh]);

  // ── Toast helper ───────────────────────────────────────────────────────────

  function showToast(msg, type = "success") {
    setToast({ msg, type });
    setTimeout(() => setToast(null), 3000);
  }

  // ── Event handlers ─────────────────────────────────────────────────────────

  async function handleStrategyToggle(name) {
    try {
      const updated = await api.toggleStrategy(name);
      setStrategies((prev) => ({ ...prev, ...updated }));
      const enabled = updated[name];
      showToast(`${name}: ${enabled ? "enabled" : "disabled"}`);
    } catch (e) {
      showToast(e.message, "error");
    }
  }

  function handleKill() {
    refresh();
    showToast("Kill switch activated — all positions cleared", "error");
  }

  function handleResume() {
    refresh();
    showToast("Trading resumed");
  }

  // ── Render ─────────────────────────────────────────────────────────────────

  return (
    <div className="app">
      {/* Header */}
      <header className="header">
        <div>
          <h1>HDAG — Kalshi Paper Trader</h1>
          <div className="subtitle">
            Team 3 · Model-Driven Directional Edge
            {lastPoll && (
              <span style={{ marginLeft: 12, color: "var(--border)" }}>
                · last update {lastPoll}
              </span>
            )}
          </div>
        </div>
        <div className="tabs">
          <button
            className={`tab ${tab === "dashboard" ? "active" : ""}`}
            onClick={() => setTab("dashboard")}
          >
            Dashboard
          </button>
          <button
            className={`tab ${tab === "backtest" ? "active" : ""}`}
            onClick={() => setTab("backtest")}
          >
            Backtest
          </button>
        </div>
      </header>

      {/* Content */}
      <main className="content">
        {tab === "dashboard" && (
          <div className="section">
            {/* Row 1: portfolio metrics */}
            <PortfolioSummary data={portfolio} />

            {/* Row 2: order entry + risk panel side by side */}
            <div style={{ display: "grid", gridTemplateColumns: "1fr auto", gap: 16 }}>
              <OrderEntry
                markets={markets}
                onFilled={() => { refresh(); showToast("Order filled"); }}
              />
              <RiskPanel
                portfolio={portfolio}
                strategies={strategies}
                onKill={handleKill}
                onResume={handleResume}
                onStrategyToggle={handleStrategyToggle}
              />
            </div>

            {/* Row 3: positions */}
            <PositionsTable positions={positions} />

            {/* Row 4: trade log + market feed */}
            <TradeLog trades={trades} markets={markets} />
          </div>
        )}

        {tab === "backtest" && <BacktestPanel markets={markets} />}
      </main>

      {/* Toast */}
      {toast && (
        <div className={`toast toast-${toast.type}`}>{toast.msg}</div>
      )}
    </div>
  );
}
