"""
engine.py — Order simulation engine.

Matches strategy orders against stored orderbook snapshots.
Models partial fills, slippage, Kalshi fees, and configurable latency.

Kalshi fee model (simplified from docs.kalshi.com):
  fee = FEE_RATE * potential_profit_per_contract * filled_qty
  For YES at price p cents: potential profit = (100 - p) cents
  For NO  at price p cents: potential profit = (100 - p) cents  [symmetric]
"""

import time
import uuid
import os
from datetime import datetime, timezone

from db import get_conn, get_orderbook

FEE_RATE = float(os.environ.get("KALSHI_FEE_RATE", "0.07"))   # 7% of potential profit
LATENCY_MS = int(os.environ.get("LATENCY_MS", "200"))          # simulated fill delay


def simulate_order(
    ticker: str,
    side: str,       # "YES" or "NO"
    size: int,       # contracts
    limit_price: int,  # max price, cents (1–99)
    timestamp: int | None = None,  # Unix ms; None = live (latest snapshot)
) -> dict:
    """
    Simulate an order fill against the orderbook.

    Returns a fill result dict:
      status       : "filled" | "partial" | "rejected"
      order_id     : uuid string
      fill_qty     : contracts actually filled
      avg_price    : weighted average fill price (cents)
      total_cost   : dollars paid (excl. fees)
      fees         : dollar fees charged
      fills_detail : list of {price, qty} — shows book walk
      timestamp    : UTC ISO string
      reason       : (if rejected) why
    """
    time.sleep(LATENCY_MS / 1000.0)

    with get_conn() as conn:
        asks, bids = get_orderbook(conn, ticker, timestamp)

    # For a YES buy we walk the ask side (ascending prices).
    # For a NO buy, the NO ask price = 100 - YES bid price (inverted bid side).
    if side == "YES":
        levels = asks
    else:
        no_levels = [(100 - price, qty) for price, qty in bids]
        no_levels.sort(key=lambda x: x[0])
        levels = no_levels

    if not levels:
        return _rejected("no_liquidity_in_snapshot", ticker, side, size)

    fills = []
    remaining = size
    total_cost_cents = 0

    for price_cents, qty in levels:
        if remaining <= 0:
            break
        if price_cents > limit_price:
            break  # above limit — stop walking

        fill_qty = min(remaining, qty)
        fills.append({"price": price_cents, "qty": fill_qty})
        total_cost_cents += price_cents * fill_qty
        remaining -= fill_qty

    if not fills:
        return _rejected("price_above_limit", ticker, side, size)

    filled_qty = size - remaining
    avg_price = total_cost_cents / filled_qty           # cents
    total_cost_dollars = total_cost_cents / 100.0

    # Fee = FEE_RATE × (potential profit per contract) × qty
    # potential profit per contract (cents) = 100 - avg_price
    fees = FEE_RATE * (1.0 - avg_price / 100.0) * filled_qty

    return {
        "status": "filled" if remaining == 0 else "partial",
        "order_id": str(uuid.uuid4()),
        "ticker": ticker,
        "side": side,
        "requested_qty": size,
        "fill_qty": filled_qty,
        "avg_price": round(avg_price, 2),
        "total_cost": round(total_cost_dollars, 4),
        "fees": round(fees, 4),
        "fills_detail": fills,
        "timestamp": datetime.now(timezone.utc).isoformat(),
    }


def _rejected(reason: str, ticker: str, side: str, size: int) -> dict:
    return {
        "status": "rejected",
        "reason": reason,
        "order_id": str(uuid.uuid4()),
        "ticker": ticker,
        "side": side,
        "requested_qty": size,
        "fill_qty": 0,
        "avg_price": 0,
        "total_cost": 0,
        "fees": 0,
        "fills_detail": [],
        "timestamp": datetime.now(timezone.utc).isoformat(),
    }
