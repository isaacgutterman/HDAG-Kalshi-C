CREATE TABLE IF NOT EXISTS events (
    event_ticker TEXT PRIMARY KEY,
    title TEXT NOT NULL,
    category TEXT,
    status TEXT,
    start_time TEXT,
    settlement_time TEXT,
    last_updated_ts TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS markets (
    market_ticker TEXT PRIMARY KEY,
    event_ticker TEXT NOT NULL,
    title TEXT NOT NULL,
    status TEXT,
    close_time TEXT,
    expiration_time TEXT,
    strike_type TEXT,
    yes_sub_title TEXT,
    no_sub_title TEXT,
    last_price INTEGER,
    last_updated_ts TEXT NOT NULL,
    FOREIGN KEY (event_ticker) REFERENCES events (event_ticker)
);

CREATE TABLE IF NOT EXISTS trades (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    market_ticker TEXT NOT NULL,
    trade_id TEXT NOT NULL,
    side TEXT,
    price INTEGER,
    count INTEGER,
    trade_ts TEXT NOT NULL,
    phase TEXT NOT NULL,
    collected_ts TEXT NOT NULL,
    FOREIGN KEY (market_ticker) REFERENCES markets (market_ticker),
    UNIQUE (market_ticker, trade_id)
);

CREATE TABLE IF NOT EXISTS orderbook_snapshots (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    market_ticker TEXT NOT NULL,
    snapshot_ts_ms INTEGER NOT NULL,
    side TEXT NOT NULL,
    price INTEGER NOT NULL,
    quantity INTEGER NOT NULL,
    collected_ts_ms INTEGER NOT NULL,
    FOREIGN KEY (market_ticker) REFERENCES markets (market_ticker)
);

CREATE TABLE IF NOT EXISTS balance_snapshots (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    balance_cents INTEGER NOT NULL,
    available_cents INTEGER,
    reserved_cents INTEGER,
    snapshot_ts TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS positions (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    market_ticker TEXT NOT NULL,
    position_side TEXT,
    quantity INTEGER NOT NULL,
    average_price INTEGER,
    snapshot_ts TEXT NOT NULL,
    FOREIGN KEY (market_ticker) REFERENCES markets (market_ticker),
    UNIQUE (market_ticker)
);

CREATE TABLE IF NOT EXISTS checkpoints (
    checkpoint_key TEXT PRIMARY KEY,
    checkpoint_value TEXT NOT NULL,
    updated_ts INTEGER NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_markets_event_ticker
    ON markets (event_ticker);

CREATE INDEX IF NOT EXISTS idx_trades_market_trade_ts
    ON trades (market_ticker, trade_ts);

CREATE INDEX IF NOT EXISTS idx_orderbook_snapshots_market_snapshot_ts
    ON orderbook_snapshots (market_ticker, snapshot_ts_ms);

CREATE INDEX IF NOT EXISTS idx_positions_market_snapshot_ts
    ON positions (market_ticker, snapshot_ts);

CREATE INDEX IF NOT EXISTS idx_balance_snapshots_snapshot_ts
    ON balance_snapshots (snapshot_ts);
