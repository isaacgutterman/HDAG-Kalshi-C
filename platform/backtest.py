"""
backtest.py — Walk-forward backtester.

IMPORTANT: No random train/test splits on time-series data (see brief).
Only walk-forward validation: train on t=0..i-1, signal at t=i, evaluate at t=i+1.

Two built-in strategies:
  mean_reversion — buy when market price deviates from lookback mean
  momentum       — buy in the direction of recent price trend

To plug in a real ML model, add a new strategy function following the same
signature and register it in STRATEGIES.
"""

from __future__ import annotations
import sqlite3
import os
from typing import Callable, Optional
import numpy as np

from db import get_conn, get_orderbook

DB_PATH = os.environ.get("KALSHI_DB_PATH", "kalshi.db")
FEE_RATE = float(os.environ.get("KALSHI_FEE_RATE", "0.07"))
STARTING_BALANCE = 100.0


# ── Signal type ────────────────────────────────────────────────────────────────
# A signal function takes (history, current_bar, edge_threshold) and returns
# either None (no trade) or a dict:
#   {"side": "YES"|"NO", "limit_price": int, "model_prob": float}
SignalFn = Callable[[list[dict], dict, float], Optional[dict]]


def mean_reversion_signal(
    history: list[dict], current: dict, edge_threshold: float
) -> Optional[dict]:
    """
    Model probability = rolling mean of YES prices / 100.
    If model_prob > market_prob + threshold -> buy YES (market underpricing).
    If model_prob < market_prob - threshold -> buy NO  (market overpricing).
    """
    if len(history) < 5:
        return None
    prices = [t["yes_price"] for t in history]
    model_prob = np.mean(prices) / 100.0
    market_prob = current["yes_price"] / 100.0

    edge = model_prob - market_prob
    if abs(edge) < edge_threshold:
        return None

    if edge > 0:
        return {"side": "YES", "limit_price": current["yes_price"] + 2, "model_prob": model_prob}
    else:
        no_price = 100 - current["yes_price"]
        return {"side": "NO",  "limit_price": no_price + 2,             "model_prob": 1 - model_prob}


def momentum_signal(
    history: list[dict], current: dict, edge_threshold: float
) -> Optional[dict]:
    """
    Simple momentum: if the last N closes are monotonically trending,
    extrapolate one step and bet with the trend.
    """
    if len(history) < 5:
        return None
    prices = [t["yes_price"] for t in history[-5:]]
    slope = np.polyfit(range(len(prices)), prices, 1)[0]  # linear trend

    market_prob = current["yes_price"] / 100.0
    # Convert slope to a probability adjustment
    model_prob = np.clip(market_prob + slope / 100.0, 0.05, 0.95)

    edge = model_prob - market_prob
    if abs(edge) < edge_threshold:
        return None

    if edge > 0:
        return {"side": "YES", "limit_price": current["yes_price"] + 2, "model_prob": model_prob}
    else:
        no_price = 100 - current["yes_price"]
        return {"side": "NO",  "limit_price": no_price + 2,             "model_prob": 1 - model_prob}


STRATEGIES: dict[str, SignalFn] = {
    "mean_reversion": mean_reversion_signal,
    "momentum":       momentum_signal,
}


# ── Backtester ─────────────────────────────────────────────────────────────────

def run_backtest(
    ticker: str,
    strategy: str = "mean_reversion",
    lookback: int = 20,
    edge_threshold: float = 0.08,
    half_kelly: bool = True,
) -> dict:
    """
    Walk-forward backtest for `ticker`.

    Returns a report dict with metrics and trade log. The balance_curve
    field is consumed by the React chart.
    """
    if strategy not in STRATEGIES:
        return {"error": f"unknown strategy '{strategy}'. Options: {list(STRATEGIES)}"}

    signal_fn = STRATEGIES[strategy]

    with get_conn() as conn:
        # Fetch all historical trades, oldest first
        cur = conn.cursor()
        cur.execute(
            "SELECT * FROM trades WHERE ticker = ? ORDER BY timestamp ASC",
            (ticker,),
        )
        all_trades = [dict(r) for r in cur.fetchall()]

        cur.execute(
            "SELECT * FROM orderbook_snapshots WHERE ticker = ? ORDER BY timestamp ASC",
            (ticker,),
        )
        all_snaps = [dict(r) for r in cur.fetchall()]

    if len(all_trades) < lookback + 5:
        return {
            "error": "insufficient_data",
            "have": len(all_trades),
            "need": lookback + 5,
            "ticker": ticker,
        }

    # Index snapshots by timestamp for quick lookup
    snap_index: dict[int, list[dict]] = {}
    for s in all_snaps:
        snap_index.setdefault(s["timestamp"], []).append(s)

    balance = STARTING_BALANCE
    peak = STARTING_BALANCE
    balance_curve: list[dict] = [{"t": 0, "balance": balance}]
    trade_log: list[dict] = []

    for i in range(lookback, len(all_trades) - 1):
        history = all_trades[i - lookback : i]
        current = all_trades[i]
        nxt     = all_trades[i + 1]

        signal = signal_fn(history, current, edge_threshold)
        if signal is None:
            continue

        side        = signal["side"]
        limit_price = signal["limit_price"]
        model_prob  = signal.get("model_prob", 0.5)

        # Position sizing: half-Kelly criterion
        if half_kelly:
            p = model_prob
            # Kelly for binary bet: f* = (p*(1/q) - (1-p)) / (1/q)  where q = limit_price/100
            q = limit_price / 100.0
            if q <= 0 or q >= 1:
                continue
            kelly_f = (p / q - (1 - p) / (1 - q))
            half_f  = max(0.0, kelly_f * 0.5)
            max_spend = half_f * balance
            size = max(1, int(max_spend / q))
            size = min(size, 20)
        else:
            size = 1

        # Simulate fill: walk the orderbook at current timestamp
        ts = current["timestamp"]
        asks = _build_asks(all_snaps, ticker, ts, side)
        if not asks:
            continue

        fills, filled_qty, avg_price_cents = _walk_book(asks, size, limit_price)
        if filled_qty == 0:
            continue

        cost = avg_price_cents / 100.0 * filled_qty
        fees = FEE_RATE * (1.0 - avg_price_cents / 100.0) * filled_qty
        if cost + fees > balance:
            continue

        # Mark-to-market exit at next bar's YES price
        p_next = nxt["yes_price"]
        if side == "YES":
            pnl = (p_next - avg_price_cents) / 100.0 * filled_qty - fees
        else:
            pnl = ((100 - p_next) - avg_price_cents) / 100.0 * filled_qty - fees

        balance += pnl
        if balance > peak:
            peak = balance

        balance_curve.append({"t": i, "balance": round(balance, 4)})
        trade_log.append({
            "i":         i,
            "timestamp": current["timestamp"],
            "side":      side,
            "qty":       filled_qty,
            "avg_price": round(avg_price_cents, 2),
            "model_prob":round(model_prob, 3),
            "pnl":       round(pnl, 4),
            "balance":   round(balance, 4),
        })

    # ── Metrics ────────────────────────────────────────────────────────────────
    values = np.array([p["balance"] for p in balance_curve])
    returns = np.diff(values) / np.where(values[:-1] == 0, 1, values[:-1])
    sharpe = (
        float(returns.mean() / returns.std() * np.sqrt(252))
        if len(returns) > 1 and returns.std() > 0
        else 0.0
    )
    running_max = np.maximum.accumulate(values)
    drawdowns = np.where(running_max > 0, (running_max - values) / running_max, 0)
    max_dd = float(drawdowns.max()) if len(drawdowns) > 0 else 0.0

    wins = [t for t in trade_log if t["pnl"] > 0]
    avg_pnl = float(np.mean([t["pnl"] for t in trade_log])) if trade_log else 0.0

    return {
        "ticker":             ticker,
        "strategy":           strategy,
        "lookback":           lookback,
        "edge_threshold":     edge_threshold,
        "half_kelly":         half_kelly,
        "starting_balance":   STARTING_BALANCE,
        "final_balance":      round(balance, 4),
        "total_pnl":          round(balance - STARTING_BALANCE, 4),
        "total_return_pct":   round((balance - STARTING_BALANCE) / STARTING_BALANCE * 100, 2),
        "sharpe_ratio":       round(sharpe, 3),
        "max_drawdown":       round(max_dd, 4),
        "total_trades":       len(trade_log),
        "win_rate":           round(len(wins) / len(trade_log), 3) if trade_log else 0.0,
        "avg_pnl_per_trade":  round(avg_pnl, 4),
        "balance_curve":      balance_curve,
        "recent_trades":      trade_log[-50:],
    }


# ── Internal helpers ───────────────────────────────────────────────────────────

def _build_asks(
    all_snaps: list[dict], ticker: str, timestamp: int, side: str
) -> list[tuple[int, int]]:
    """Return sorted ask levels at or before `timestamp`."""
    relevant = [
        s for s in all_snaps
        if s["ticker"] == ticker and s["timestamp"] <= timestamp
    ]
    if not relevant:
        return []
    # Use only the most recent batch
    latest_ts = max(s["timestamp"] for s in relevant)
    batch = [s for s in relevant if s["timestamp"] == latest_ts]

    if side == "YES":
        levels = [(s["yes_price"], s["quantity"]) for s in batch if s.get("side") == "ask"]
    else:
        levels = [(100 - s["yes_price"], s["quantity"]) for s in batch if s.get("side") == "bid"]

    levels.sort(key=lambda x: x[0])
    return levels


def _walk_book(
    asks: list[tuple[int, int]], size: int, limit_price: int
) -> tuple[list[dict], int, float]:
    fills = []
    remaining = size
    total_cents = 0

    for price, qty in asks:
        if remaining <= 0 or price > limit_price:
            break
        fq = min(remaining, qty)
        fills.append({"price": price, "qty": fq})
        total_cents += price * fq
        remaining -= fq

    filled = size - remaining
    avg = total_cents / filled if filled > 0 else 0
    return fills, filled, avg
