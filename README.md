# Kalshi Pipeline

Professional Python data-ingestion scaffold for HDAG Team 3, Case 3: Model-Driven Directional Edge.

## Project Purpose

This repository is building an authenticated Kalshi data pipeline for:

- market discovery and historical market sync
- historical trade sync for watched markets
- orderbook polling for watched markets
- authenticated portfolio sync
- real-time WebSocket intake for watched markets
- local SQLite storage for backtesting and live strategy support

The current emphasis is professional ingestion infrastructure first: typed data transfer objects, explicit scripts, reproducible local storage, and testable ingestion paths.

## Architecture Overview

The codebase is organized into a small ingestion stack:

- `app/config.py`: loads environment-driven settings
- `app/auth.py`: builds Kalshi request signatures from an RSA private key
- `app/client.py`: thin async HTTP client with retries and optional auth
- `app/dto.py`: Pydantic DTOs for API payload validation
- `app/ingest/`: ingestion jobs for markets, events, trades, orderbooks, portfolio, and WebSocket consumption
- `app/storage/`: SQLite connection/bootstrap code plus repositories
- `scripts/`: operator entrypoints for common sync and streaming tasks
- `tests/`: focused automated tests for core ingestion and storage behavior

Current storage backend:

- SQLite only
- schema bootstrapped from `app/storage/schema.sql`
- WAL mode enabled by the DB bootstrap path

## Repo Structure

- `app/`
- `app/ingest/`
- `app/services/`
- `app/storage/`
- `scripts/`
- `tests/`
- `data/`
- `.env.example`
- `pyproject.toml`

## Setup

Python requirements:

- Python 3.11 or newer

Recommended local setup:

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -e '.[dev]'
```

Quick sanity checks after install:

```bash
python -m pip check
PYTHONPATH=. pytest tests/test_config.py
```

Expected results:

- `python -m pip check` reports no broken requirements
- the focused pytest command passes

## Environment Variables

Copy `.env.example` to `.env` before running scripts.

```bash
cp .env.example .env
```

Current variables used by the code:

- `KALSHI_ENV`: environment label, defaults to `demo`
- `KALSHI_BASE_URL`: HTTP API base URL
- `KALSHI_WS_URL`: WebSocket URL
- `KALSHI_API_KEY_ID`: API key id for authenticated calls
- `KALSHI_PRIVATE_KEY_PATH`: local path to RSA private key PEM file
- `SQLITE_DB_PATH`: SQLite database file path
- `WATCH_TICKERS`: comma-separated ticker list used by watchlist-oriented scripts
- `LOG_LEVEL`: log level passed through the logging setup

Example `.env.example` values:

```env
KALSHI_ENV=demo
KALSHI_BASE_URL=https://demo-api.kalshi.co
KALSHI_WS_URL=wss://demo-api.kalshi.co/trade-api/ws/v2
KALSHI_API_KEY_ID=your_api_key_id_here
KALSHI_PRIVATE_KEY_PATH=secrets/kalshi-demo-key.pem
SQLITE_DB_PATH=data/kalshi_markets.sqlite3
WATCH_TICKERS=INX-2026-DEC-ABOVE-6000,BTC-2026-DEC-ABOVE-150000
LOG_LEVEL=INFO
```

Notes:

- `WATCH_TICKERS` is used by `sync_trades.py`, `poll_orderbooks.py`, and `stream_market_data.py`
- `sync_markets.py` defaults to bounded discovery and supports optional watchlist-only mode
- authenticated portfolio and authenticated WebSocket usage require a valid key id and readable PEM file

## Database Bootstrap

Bootstrap the local SQLite database before running sync jobs:

```bash
PYTHONPATH=. python3 scripts/bootstrap_db.py
```

Expected output:

```text
Bootstrapped SQLite schema at data/kalshi_markets.sqlite3
```

What this does:

- creates the SQLite file if needed
- applies the current schema
- enables the expected SQLite connection behavior through the storage bootstrap path

## Script Execution Order

Recommended teammate workflow:

1. Bootstrap the database.
2. Run market discovery.
3. Run any watchlist-based historical jobs.
4. Run portfolio sync if authenticated account state is needed.
5. Start WebSocket streaming last for live intake.

### 1. Market Discovery

Default behavior is bounded discovery, not watchlist-only:

```bash
PYTHONPATH=. python3 scripts/sync_markets.py
```

Current default behavior:

- calls `GET /trade-api/v2/markets`
- paginates using Kalshi cursors
- applies a bounded discovery filter set in the script
- stores results in the `markets` table

Optional watchlist-only mode:

```bash
PYTHONPATH=. python3 scripts/sync_markets.py --watchlist-only
```

Watchlist-only mode:

- narrows the request to `WATCH_TICKERS`
- is intended for targeted refreshes
- is not the default behavior

Expected output shape:

```text
Synced markets (pages_processed=..., markets_upserted=..., checkpoint='...')
```

### 2. Historical Trades For Watched Markets

```bash
PYTHONPATH=. python3 scripts/sync_trades.py
```

Requirements:

- `WATCH_TICKERS` should be populated
- corresponding markets should already exist locally

Expected output shape:

```text
Synced trades (markets_processed=..., trades_upserted=...)
```

### 3. Orderbook Polling For Watched Markets

Single-pass polling:

```bash
PYTHONPATH=. python3 scripts/poll_orderbooks.py
```

Custom polling example:

```bash
PYTHONPATH=. python3 scripts/poll_orderbooks.py --poll-interval-seconds 2 --max-polls 3
```

Expected output shape:

```text
Polled orderbooks (polls_completed=..., markets_processed=..., levels_inserted=...)
```

### 4. Authenticated Portfolio Sync

```bash
PYTHONPATH=. python3 scripts/sync_portfolio.py
```

Requirements:

- `KALSHI_API_KEY_ID` must be set
- `KALSHI_PRIVATE_KEY_PATH` must point to a readable PEM file

Expected output shape:

```text
Synced portfolio (balance_snapshots_inserted=..., positions_upserted=...)
```

### 5. Real-Time WebSocket Stream

```bash
PYTHONPATH=. python3 scripts/stream_market_data.py
```

Current behavior:

- uses `WATCH_TICKERS`
- bootstraps DB if needed
- tries to build authenticated WebSocket headers if credentials are present
- runs until interrupted
- writes supported trade and orderbook messages to SQLite

Safe manual validation:

- use 1-2 demo tickers in `WATCH_TICKERS`
- stop the process with `Ctrl+C` after confirming subscription or reconnect logs

## Testing Commands

Run the full suite:

```bash
PYTHONPATH=. pytest
```

Run focused suites when iterating on a specific area:

```bash
PYTHONPATH=. pytest tests/test_markets.py
PYTHONPATH=. pytest tests/test_websocket.py
```

Expected output:

- pytest discovers tests under `tests/`
- passing tests are reported
- depending on the local plugin mix, you may still see a warning about `asyncio_mode`

## Security Checks

Run these commands inside the project virtual environment after installing dev dependencies:

```bash
python -m pip check
python -m pip_audit
bandit -r app
PYTHONPATH=. pytest
```

Expected results:

- `python -m pip check` reports no broken requirements
- `python -m pip_audit` reports no known vulnerabilities, or prints findings that need review
- `bandit -r app` completes and reports any security findings in the application package
- `PYTHONPATH=. pytest` validates the local codebase behavior

## Secrets And Key Hygiene

- Keep `.env` local only and never commit it
- Use demo credentials for development by default
- Do not reuse production credentials in local experiments unless there is a deliberate operational need
- Keep private keys outside version control in a restricted path such as `secrets/kalshi-demo-key.pem`
- Tighten permissions on key files, for example:

```bash
chmod 600 secrets/kalshi-demo-key.pem
```

- Treat `.pem`, `.key`, `.p12`, and `.pfx` files as sensitive
- Rotate credentials immediately if key material or `.env` contents are exposed in logs, screenshots, copied files, or shell history

## Troubleshooting

`ModuleNotFoundError` when running scripts:

- activate the project venv
- run `pip install -e '.[dev]'`

`sync_markets.py` returns one page with `markets_upserted=0`:

- check whether the `checkpoints` table contains an older `markets_sync_cursor`
- a stale cursor from a previous query shape can cause an empty terminal page

Authenticated scripts fail immediately:

- verify `KALSHI_API_KEY_ID` is set
- verify `KALSHI_PRIVATE_KEY_PATH` exists and points to the intended PEM file
- verify the file is readable by your current shell user

WebSocket stream reconnects continuously:

- confirm demo credentials are valid if you expect authenticated headers
- confirm `WATCH_TICKERS` contains active tickers
- confirm `websockets` and `certifi` are installed in the environment actually running the script

Trade, orderbook, or stream jobs complain about missing markets:

- run market discovery first
- confirm the watched tickers exist in the local `markets` table

Unexpected SQLite behavior against an older local DB:

- this project does not currently auto-migrate older DB files
- schema changes may require rebuilding the local database

## Current Status

Implemented today:

- authenticated request signing
- async HTTP client with retries
- typed DTOs
- SQLite repositories and checkpoints
- market discovery and watchlist refresh support
- historical trades sync
- orderbook polling
- authenticated portfolio sync
- WebSocket reader and consumer foundation

Not yet implemented:

- production deployment workflow
- schema migrations for older SQLite files
- CI automation
- higher-level strategy or risk logic
