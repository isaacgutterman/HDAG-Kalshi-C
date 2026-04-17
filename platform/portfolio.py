"""
portfolio.py — In-memory virtual portfolio.

$100 starting balance.
Tracks open positions, trade log, P&L, and enforces risk limits.
All prices in cents internally; dollar amounts in public API.
"""

from __future__ import annotations
import uuid
from dataclasses import dataclass, field
from datetime import datetime, date, timezone
from typing import Optional
import numpy as np

# ── Risk limits ────────────────────────────────────────────────────────────────
STARTING_BALANCE = 100.0      # dollars
DAILY_LOSS_CAP   = 20.0       # max daily realized loss
MAX_DRAWDOWN_PCT = 0.30       # 30% drawdown hard stop
MAX_POSITION_SIZE = 20        # max contracts per (ticker, side)


@dataclass
class TradeRecord:
    order_id: str
    ticker: str
    side: str         # YES / NO
    action: str       # OPEN / CLOSE
    qty: int
    avg_price: float  # cents
    fees: float       # dollars
    timestamp: str
    pnl: float = 0.0  # realized PnL (CLOSE only)


@dataclass
class Position:
    ticker: str
    side: str
    size: int
    avg_fill_price: float  # cents
    opened_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())


class Portfolio:
    def __init__(self):
        self.balance: float = STARTING_BALANCE
        self._peak_balance: float = STARTING_BALANCE
        self.positions: dict[str, Position] = {}   # key = f"{ticker}_{side}"
        self.trade_log: list[TradeRecord] = []
        self._daily_realized: dict[str, float] = {}  # date -> realized pnl
        self.balance_history: list[tuple[str, float]] = [
            (datetime.now(timezone.utc).isoformat(), STARTING_BALANCE)
        ]
        self.killed: bool = False
        # strategy name -> enabled bool; populated by main.py
        self.strategies: dict[str, bool] = {}

    # ── Risk checks ────────────────────────────────────────────────────────────

    def check_risk(
        self, ticker: str, side: str, size: int, estimated_cost: float
    ) -> Optional[str]:
        """Returns an error string if a risk limit would be breached, else None."""
        if self.killed:
            return "kill_switch_active — call POST /resume to re-enable"
        if estimated_cost > self.balance:
            return f"insufficient_balance (have ${self.balance:.2f}, need ${estimated_cost:.2f})"
        key = f"{ticker}_{side}"
        current = self.positions[key].size if key in self.positions else 0
        if current + size > MAX_POSITION_SIZE:
            return f"max_position_size exceeded ({MAX_POSITION_SIZE} contracts per side)"
        today_loss = self._daily_realized.get(_today(), 0.0)
        if today_loss <= -DAILY_LOSS_CAP:
            return f"daily_loss_cap reached (${DAILY_LOSS_CAP:.0f}/day)"
        drawdown = _drawdown(self._peak_balance, self.balance)
        if drawdown >= MAX_DRAWDOWN_PCT:
            return f"max_drawdown triggered ({MAX_DRAWDOWN_PCT*100:.0f}%)"
        return None

    # ── Portfolio mutations ────────────────────────────────────────────────────

    def apply_fill(
        self, ticker: str, side: str, qty: int, avg_price: float, fees: float, order_id: str
    ) -> None:
        """Record a new opening fill."""
        cost = avg_price / 100.0 * qty + fees
        self.balance -= cost
        _record_balance(self)

        key = f"{ticker}_{side}"
        if key in self.positions:
            pos = self.positions[key]
            new_size = pos.size + qty
            pos.avg_fill_price = (pos.avg_fill_price * pos.size + avg_price * qty) / new_size
            pos.size = new_size
        else:
            self.positions[key] = Position(ticker, side, qty, avg_price)

        self.trade_log.append(TradeRecord(
            order_id=order_id, ticker=ticker, side=side,
            action="OPEN", qty=qty, avg_price=avg_price,
            fees=fees, timestamp=datetime.now(timezone.utc).isoformat(),
        ))

    def close_position(self, ticker: str, side: str, settlement_price: int) -> Optional[float]:
        """
        Settle a position at settlement_price cents (100 = outcome won, 0 = lost).
        Returns realized PnL in dollars, or None if no position found.
        """
        key = f"{ticker}_{side}"
        if key not in self.positions:
            return None
        pos = self.positions.pop(key)

        # Receive settlement proceeds
        proceeds = settlement_price / 100.0 * pos.size
        self.balance += proceeds
        pnl = (settlement_price - pos.avg_fill_price) / 100.0 * pos.size

        _record_balance(self)
        if self.balance > self._peak_balance:
            self._peak_balance = self.balance

        today = _today()
        self._daily_realized[today] = self._daily_realized.get(today, 0.0) + pnl

        self.trade_log.append(TradeRecord(
            order_id="settle-" + str(uuid.uuid4())[:8],
            ticker=ticker, side=side, action="CLOSE",
            qty=pos.size, avg_price=settlement_price,
            fees=0.0, timestamp=datetime.now(timezone.utc).isoformat(),
            pnl=round(pnl, 4),
        ))
        return round(pnl, 4)

    def kill(self) -> None:
        """Emergency flatten — clear all positions, lock trading."""
        self.killed = True
        self.positions.clear()
        _record_balance(self)

    def resume(self) -> None:
        self.killed = False

    # ── Metrics ────────────────────────────────────────────────────────────────

    def unrealized_pnl(self, current_prices: dict[str, int]) -> float:
        total = 0.0
        for key, pos in self.positions.items():
            cp = current_prices.get(pos.ticker, pos.avg_fill_price)
            if pos.side == "YES":
                total += (cp - pos.avg_fill_price) / 100.0 * pos.size
            else:
                total += ((100 - cp) - pos.avg_fill_price) / 100.0 * pos.size
        return round(total, 4)

    def realized_pnl(self) -> float:
        return round(sum(t.pnl for t in self.trade_log if t.action == "CLOSE"), 4)

    def sharpe_ratio(self) -> Optional[float]:
        values = np.array([v for _, v in self.balance_history])
        if len(values) < 10:
            return None
        returns = np.diff(values) / values[:-1]
        std = returns.std()
        if std == 0:
            return None
        # Annualise assuming ~8760 hourly observations/year
        return round(float(returns.mean() / std * np.sqrt(8760)), 3)

    def max_drawdown(self) -> float:
        values = np.array([v for _, v in self.balance_history])
        peak = np.maximum.accumulate(values)
        dd = (peak - values) / np.where(peak == 0, 1, peak)
        return round(float(dd.max()), 4) if len(dd) > 0 else 0.0

    def to_summary(self, current_prices: dict[str, int] = {}) -> dict:
        upnl = self.unrealized_pnl(current_prices)
        rpnl = self.realized_pnl()
        today_loss = self._daily_realized.get(_today(), 0.0)
        drawdown = self.max_drawdown()
        return {
            "balance":            round(self.balance, 4),
            "starting_balance":   STARTING_BALANCE,
            "total_pnl":          round(rpnl + upnl, 4),
            "realized_pnl":       rpnl,
            "unrealized_pnl":     upnl,
            "sharpe_ratio":       self.sharpe_ratio(),
            "max_drawdown":       drawdown,
            "daily_loss":         round(today_loss, 4),
            "daily_loss_cap":     DAILY_LOSS_CAP,
            "max_drawdown_limit": MAX_DRAWDOWN_PCT,
            "max_position_size":  MAX_POSITION_SIZE,
            "position_count":     len(self.positions),
            "trade_count":        len(self.trade_log),
            "killed":             self.killed,
            "strategies":         self.strategies,
        }

    def positions_list(self, current_prices: dict[str, int] = {}) -> list[dict]:
        out = []
        for key, pos in self.positions.items():
            cp = current_prices.get(pos.ticker, int(pos.avg_fill_price))
            if pos.side == "YES":
                upnl = (cp - pos.avg_fill_price) / 100.0 * pos.size
            else:
                upnl = ((100 - cp) - pos.avg_fill_price) / 100.0 * pos.size
            out.append({
                "ticker":          pos.ticker,
                "side":            pos.side,
                "size":            pos.size,
                "avg_fill_price":  round(pos.avg_fill_price, 2),
                "current_price":   cp,
                "unrealized_pnl":  round(upnl, 4),
                "opened_at":       pos.opened_at,
            })
        return out


# ── Helpers ────────────────────────────────────────────────────────────────────

def _today() -> str:
    return date.today().isoformat()


def _drawdown(peak: float, current: float) -> float:
    if peak == 0:
        return 0.0
    return (peak - current) / peak


def _record_balance(p: Portfolio) -> None:
    p.balance_history.append((datetime.now(timezone.utc).isoformat(), p.balance))
