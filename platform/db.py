"""
db.py — SQLite connection adapter for Task 1's schema.

Expected schema (from Task 1 brief):
  markets         (ticker, status, yes_bid, yes_ask, volume, last_updated, game_phase)
  orderbook_snapshots (id, ticker, timestamp, yes_price, quantity, side, game_phase)
  trades          (id, ticker, timestamp, yes_price, size, taker_side, game_phase)

If Task 1 used different column names, update the queries here — not in main.py.
Prices are stored as integers (cents).
"""

import sqlite3
import os
from contextlib import contextmanager

DB_PATH = os.environ.get("KALSHI_DB_PATH", "kalshi.db")


@contextmanager
def get_conn():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    try:
        yield conn
    finally:
        conn.close()


def get_orderbook(conn: sqlite3.Connection, ticker: str, timestamp: int | None = None):
    """
    Return (asks, bids) as sorted lists of (price_cents, qty).
    If timestamp is None, uses the latest snapshot.
    asks: [(price, qty), ...] ascending  — YES ask levels
    bids: [(price, qty), ...] descending — YES bid levels
    """
    cur = conn.cursor()
    if timestamp is None:
        cur.execute(
            """
            SELECT yes_price, quantity, side
            FROM orderbook_snapshots
            WHERE ticker = ?
            ORDER BY timestamp DESC
            LIMIT 100
            """,
            (ticker,),
        )
    else:
        cur.execute(
            """
            SELECT yes_price, quantity, side
            FROM orderbook_snapshots
            WHERE ticker = ? AND timestamp <= ?
            ORDER BY timestamp DESC
            LIMIT 100
            """,
            (ticker, timestamp),
        )

    rows = cur.fetchall()
    asks, bids = [], []
    for row in rows:
        price, qty, side = row["yes_price"], row["quantity"], row["side"]
        if side == "ask":
            asks.append((price, qty))
        else:
            bids.append((price, qty))

    asks.sort(key=lambda x: x[0])
    bids.sort(key=lambda x: x[0], reverse=True)
    return asks, bids


def get_latest_yes_price(conn: sqlite3.Connection, ticker: str) -> int | None:
    """Pull the current mid-price for a ticker from the markets table."""
    cur = conn.cursor()
    cur.execute(
        "SELECT yes_bid, yes_ask FROM markets WHERE ticker = ? LIMIT 1", (ticker,)
    )
    row = cur.fetchone()
    if not row:
        return None
    bid, ask = row["yes_bid"], row["yes_ask"]
    if bid and ask:
        return (bid + ask) // 2
    return bid or ask


def get_trade_history(
    conn: sqlite3.Connection,
    ticker: str,
    limit: int = 200,
    since_ts: int | None = None,
):
    """Return recent trade tape for a ticker, newest first."""
    cur = conn.cursor()
    if since_ts:
        cur.execute(
            """
            SELECT * FROM trades
            WHERE ticker = ? AND timestamp >= ?
            ORDER BY timestamp DESC LIMIT ?
            """,
            (ticker, since_ts, limit),
        )
    else:
        cur.execute(
            "SELECT * FROM trades WHERE ticker = ? ORDER BY timestamp DESC LIMIT ?",
            (ticker, limit),
        )
    return [dict(r) for r in cur.fetchall()]
