# HDAG Team 3 — Task 2: Trading Platform

Paper trading simulator with a React + FastAPI dashboard. Runs strategy signals
against real Kalshi orderbook data (Task 1 DB) without using real capital.

---

## Quick start

### 1. Backend

```bash
cd task2/backend
pip install -r requirements.txt

# Point at Task 1's database
export KALSHI_DB_PATH=/path/to/kalshi.db

# If you need a demo DB for testing without Task 1's data:
# python seed_demo.py kalshi_demo.db
# export KALSHI_DB_PATH=kalshi_demo.db

uvicorn main:app --reload --port 8000
```

API docs auto-generated at: http://localhost:8000/docs

### 2. Frontend

```bash
cd task2/frontend
npm install
npm run dev
```

Dashboard: http://localhost:5173

---

## Architecture

```
task2/
├── backend/
│   ├── main.py         FastAPI app — all HTTP routes
│   ├── engine.py       Order simulation (fills, slippage, fees)
│   ├── portfolio.py    In-memory portfolio state + risk limits
│   ├── backtest.py     Walk-forward backtester (2 strategies)
│   ├── db.py           SQLite adapter for Task 1's schema
│   ├── seed_demo.py    Generate synthetic DB for testing
│   └── requirements.txt
└── frontend/
    └── src/
        ├── App.jsx             Root — polling, tab nav
        ├── api.js              API client
        └── components/
            ├── PortfolioSummary.jsx   4 metric cards (balance, P&L, Sharpe, drawdown)
            ├── PositionsTable.jsx     Open positions with live unrealized P&L
            ├── OrderEntry.jsx         Manual order placement form
            ├── RiskPanel.jsx          Gauges, strategy toggles, kill switch
            ├── TradeLog.jsx           Trade log + market feed
            └── BacktestPanel.jsx      Backtest config, balance curve, trade table
```

---

## DB schema assumptions (Task 1)

`engine.py` and `db.py` assume Task 1 created these tables with integer cent prices:

```sql
markets             (ticker, status, yes_bid, yes_ask, volume, last_updated, game_phase)
orderbook_snapshots (id, ticker, timestamp, yes_price, quantity, side, game_phase)
trades              (id, ticker, timestamp, yes_price, size, taker_side, game_phase)
```

If Task 1 used different column names, update the queries in `db.py` — nowhere else.

---

## Order simulation

`engine.py` models:

- **Partial fills** — walks price levels; fills what's available at each level
- **Slippage** — large orders walk up/down the book naturally
- **Fees** — 7% of potential profit per contract (Kalshi taker model)
- **Latency** — configurable `LATENCY_MS` env var (default 200ms)

```
KALSHI_FEE_RATE=0.07   # override fee rate
LATENCY_MS=200         # override simulated latency
```

---

## Risk limits (portfolio.py)

| Limit | Default | Behaviour |
|---|---|---|
| Starting balance | $100 | Virtual cash |
| Max position size | 20 contracts | Per (ticker, side) |
| Daily loss cap | $20 | Blocks new orders |
| Max drawdown | 30% | Blocks new orders |

All limits enforced in `check_risk()` before every order.

---

## Backtest strategies

| Strategy | Logic |
|---|---|
| `mean_reversion` | Model prob = rolling mean price / 100. Trade when market deviates by > edge_threshold. |
| `momentum` | Linear trend fit over last 5 bars. Trade in the direction of the slope. |

Position sizing: half-Kelly criterion (conservative; widen after stable paper trading).

**Walk-forward only** — no look-ahead bias. Train on t=0..i-1, signal at t=i, evaluate at t=i+1.

To add a real ML model, implement a new signal function in `backtest.py` following the same
signature `(history, current, edge_threshold) -> dict | None` and register it in `STRATEGIES`.

---

## API reference

| Method | Endpoint | Description |
|---|---|---|
| POST | `/orders` | Place paper order |
| POST | `/settle` | Settle position at resolution |
| GET | `/portfolio` | Summary with live P&L |
| GET | `/positions` | Open positions |
| GET | `/trades` | Trade log |
| GET | `/balance_history` | Balance curve data |
| POST | `/kill` | Kill switch — flatten all + halt |
| POST | `/resume` | Re-enable after kill |
| GET | `/strategies` | Strategy list + on/off |
| POST | `/strategies/{name}/toggle` | Toggle strategy |
| GET | `/markets` | Markets from Task 1 DB |
| GET | `/markets/{ticker}/feed` | Recent trade tape |
| POST | `/backtest` | Run walk-forward backtest |
| GET | `/health` | Server health check |

---

## Extending to real Kalshi orders

The `simulate_order()` call in `engine.py` is the only thing that needs replacing.
Swap it for the authenticated Kalshi client from Task 1 (`kalshi-python`) with the same
return shape. Strategy logic and portfolio tracking stay unchanged.
