"""
seed_demo.py — Creates a synthetic kalshi.db for testing Task 2 in isolation.

Usage: python seed_demo.py [output_path]
Default output: kalshi.db in the current directory.

Generates ~500 orderbook snapshots and trades across 3 fake market tickers
using a random walk for YES prices. Prices are integers (cents).
"""

import sqlite3
import random
import time
import sys
import math

DB_PATH = sys.argv[1] if len(sys.argv) > 1 else "kalshi.db"

# ── Markets ────────────────────────────────────────────────────────────────────
TICKERS = [
    {"ticker": "NBA-CELTICS-WIN-T1", "event_ticker": "NBA-CELTICS-T1", "game_phase": "live"},
    {"ticker": "NBA-LAKERS-WIN-T2",  "event_ticker": "NBA-LAKERS-T2",  "game_phase": "pre_game"},
    {"ticker": "NFL-CHIEFS-WIN-T3",  "event_ticker": "NFL-CHIEFS-T3",  "game_phase": "pre_game"},
]

# ── Schema ─────────────────────────────────────────────────────────────────────
SCHEMA = """
CREATE TABLE IF NOT EXISTS markets (
    ticker        TEXT PRIMARY KEY,
    status        TEXT DEFAULT 'open',
    yes_bid       INTEGER,
    yes_ask       INTEGER,
    volume        INTEGER DEFAULT 0,
    last_updated  INTEGER,
    event_ticker  TEXT,
    game_phase    TEXT
);

CREATE TABLE IF NOT EXISTS orderbook_snapshots (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    ticker      TEXT NOT NULL,
    timestamp   INTEGER NOT NULL,
    yes_price   INTEGER NOT NULL,
    quantity    INTEGER NOT NULL,
    side        TEXT NOT NULL,  -- 'ask' or 'bid'
    game_phase  TEXT
);

CREATE TABLE IF NOT EXISTS trades (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    ticker      TEXT NOT NULL,
    timestamp   INTEGER NOT NULL,
    yes_price   INTEGER NOT NULL,
    size        INTEGER NOT NULL,
    taker_side  TEXT NOT NULL,  -- 'yes' or 'no'
    game_phase  TEXT
);
"""


def random_walk(start: int, n: int, step: int = 8) -> list[int]:
    """Generate a bounded random walk of YES prices in cents."""
    prices = [start]
    for _ in range(n - 1):
        delta = random.randint(-step, step)
        nxt = max(10, min(90, prices[-1] + delta))
        prices.append(nxt)
    return prices


def seed(conn: sqlite3.Connection):
    conn.executescript(SCHEMA)
    now_ms = int(time.time() * 1000)
    interval_ms = 60_000  # 1 minute between snapshots

    for mkt in TICKERS:
        ticker = mkt["ticker"]
        n_bars = 250

        prices = random_walk(random.randint(35, 65), n_bars)
        base_ts = now_ms - n_bars * interval_ms

        for i, yes_mid in enumerate(prices):
            ts = base_ts + i * interval_ms
            spread = random.randint(1, 3)
            yes_bid = max(1,  yes_mid - spread)
            yes_ask = min(99, yes_mid + spread)
            volume = random.randint(200, 2000)

            # Insert orderbook snapshot: 3 ask levels, 3 bid levels
            for lvl in range(3):
                ask_price = yes_ask + lvl * random.randint(1, 2)
                bid_price = yes_bid - lvl * random.randint(1, 2)
                qty = random.randint(20, 200)

                conn.execute(
                    "INSERT INTO orderbook_snapshots (ticker, timestamp, yes_price, quantity, side, game_phase) "
                    "VALUES (?, ?, ?, ?, 'ask', ?)",
                    (ticker, ts, min(99, ask_price), qty, mkt["game_phase"]),
                )
                conn.execute(
                    "INSERT INTO orderbook_snapshots (ticker, timestamp, yes_price, quantity, side, game_phase) "
                    "VALUES (?, ?, ?, ?, 'bid', ?)",
                    (ticker, ts, max(1, bid_price), qty, mkt["game_phase"]),
                )

            # Insert a few random trades at this timestamp
            for _ in range(random.randint(1, 5)):
                trade_price = random.randint(yes_bid, yes_ask)
                trade_size  = random.randint(1, 20)
                side        = random.choice(["yes", "no"])
                conn.execute(
                    "INSERT INTO trades (ticker, timestamp, yes_price, size, taker_side, game_phase) "
                    "VALUES (?, ?, ?, ?, ?, ?)",
                    (ticker, ts, trade_price, trade_size, side, mkt["game_phase"]),
                )

        # Update market row to latest snapshot
        final_yes = prices[-1]
        final_bid = max(1,  final_yes - 2)
        final_ask = min(99, final_yes + 2)
        conn.execute(
            "INSERT OR REPLACE INTO markets (ticker, status, yes_bid, yes_ask, volume, last_updated, event_ticker, game_phase) "
            "VALUES (?, 'open', ?, ?, ?, ?, ?, ?)",
            (ticker, final_bid, final_ask, random.randint(5000, 50000), now_ms,
             mkt["event_ticker"], mkt["game_phase"]),
        )

    conn.commit()


if __name__ == "__main__":
    conn = sqlite3.connect(DB_PATH)
    seed(conn)
    conn.close()
    print(f"Demo DB written to: {DB_PATH}")
    print("Tickers seeded:", [m["ticker"] for m in TICKERS])
    print("Start server with:  KALSHI_DB_PATH=" + DB_PATH + " uvicorn main:app --reload --port 8000")
