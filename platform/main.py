"""
main.py — HDAG Team 3 Paper Trading API

Run with:
  KALSHI_DB_PATH=../kalshi.db uvicorn main:app --reload --port 8000
"""

from __future__ import annotations
import os
from datetime import datetime, timezone

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field
from typing import Literal, Optional

from db import get_conn, get_latest_yes_price, get_trade_history
from engine import simulate_order
from portfolio import Portfolio
from backtest import run_backtest, STRATEGIES

app = FastAPI(title="HDAG Kalshi Simulator", version="0.2.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

# Global portfolio instance (in-memory; resets on server restart)
portfolio = Portfolio()
portfolio.strategies = {name: False for name in STRATEGIES}


# ── Request models ─────────────────────────────────────────────────────────────

class OrderRequest(BaseModel):
    ticker: str
    side: Literal["YES", "NO"]
    size: int = Field(ge=1, le=100)
    limit_price: int = Field(ge=1, le=99, description="Price in cents")

class SettleRequest(BaseModel):
    ticker: str
    side: Literal["YES", "NO"]
    settlement_price: int = Field(ge=0, le=100, description="100=YES wins, 0=NO wins")

class BacktestRequest(BaseModel):
    ticker: str
    strategy: str = "mean_reversion"
    lookback: int = Field(default=20, ge=5, le=200)
    edge_threshold: float = Field(default=0.08, ge=0.01, le=0.50)
    half_kelly: bool = True


# ── Helper ─────────────────────────────────────────────────────────────────────

def _current_prices(tickers: list[str]) -> dict[str, int]:
    prices = {}
    with get_conn() as conn:
        for t in tickers:
            p = get_latest_yes_price(conn, t)
            if p is not None:
                prices[t] = p
    return prices


# ── Order routes ───────────────────────────────────────────────────────────────

@app.post("/orders", summary="Place a paper order")
def place_order(req: OrderRequest):
    estimated_cost = req.limit_price / 100.0 * req.size
    err = portfolio.check_risk(req.ticker, req.side, req.size, estimated_cost)
    if err:
        raise HTTPException(400, detail=err)

    result = simulate_order(req.ticker, req.side, req.size, req.limit_price)

    if result["status"] == "rejected":
        raise HTTPException(400, detail=f"Order rejected: {result['reason']}")

    portfolio.apply_fill(
        ticker=req.ticker,
        side=req.side,
        qty=result["fill_qty"],
        avg_price=result["avg_price"],
        fees=result["fees"],
        order_id=result["order_id"],
    )
    return result


@app.post("/settle", summary="Settle a position at market resolution")
def settle_position(req: SettleRequest):
    pnl = portfolio.close_position(req.ticker, req.side, req.settlement_price)
    if pnl is None:
        raise HTTPException(404, detail=f"No open {req.side} position for {req.ticker}")
    return {"ticker": req.ticker, "side": req.side, "pnl": pnl, "balance": portfolio.balance}


# ── Portfolio routes ───────────────────────────────────────────────────────────

@app.get("/portfolio", summary="Portfolio summary with live P&L")
def get_portfolio():
    tickers = list({pos.ticker for pos in portfolio.positions.values()})
    prices = _current_prices(tickers)
    return portfolio.to_summary(prices)


@app.get("/positions", summary="Open positions with unrealized P&L")
def get_positions():
    tickers = list({pos.ticker for pos in portfolio.positions.values()})
    prices = _current_prices(tickers)
    return portfolio.positions_list(prices)


@app.get("/trades", summary="Trade log (newest first)")
def get_trades(limit: int = 100):
    records = portfolio.trade_log[-limit:][::-1]
    return [vars(t) for t in records]


@app.get("/balance_history", summary="Balance curve for charting")
def balance_history(limit: int = 500):
    hist = portfolio.balance_history[-limit:]
    return [{"timestamp": ts, "balance": bal} for ts, bal in hist]


# ── Risk controls ──────────────────────────────────────────────────────────────

@app.post("/kill", summary="Kill switch — flatten all positions and halt trading")
def kill_switch():
    portfolio.kill()
    return {"status": "killed", "message": "All positions cleared. POST /resume to re-enable."}


@app.post("/resume", summary="Re-enable trading after kill switch")
def resume():
    portfolio.resume()
    return {"status": "active"}


# ── Strategy toggles ───────────────────────────────────────────────────────────

@app.get("/strategies", summary="List strategies and their on/off status")
def list_strategies():
    return portfolio.strategies


@app.post("/strategies/{name}/toggle", summary="Toggle a strategy on or off")
def toggle_strategy(name: str):
    if name not in portfolio.strategies:
        raise HTTPException(404, detail=f"Unknown strategy. Options: {list(portfolio.strategies)}")
    portfolio.strategies[name] = not portfolio.strategies[name]
    return {name: portfolio.strategies[name]}


# ── Market data routes ─────────────────────────────────────────────────────────

@app.get("/markets", summary="List markets from Task 1 DB")
def list_markets(limit: int = 50, status: str | None = None):
    with get_conn() as conn:
        conn.row_factory = __import__("sqlite3").Row
        cur = conn.cursor()
        if status:
            cur.execute(
                "SELECT * FROM markets WHERE status = ? ORDER BY volume DESC LIMIT ?",
                (status, limit),
            )
        else:
            cur.execute("SELECT * FROM markets ORDER BY volume DESC LIMIT ?", (limit,))
        return [dict(r) for r in cur.fetchall()]


@app.get("/markets/{ticker}/feed", summary="Recent trade tape for a ticker")
def market_feed(ticker: str, limit: int = 50):
    with get_conn() as conn:
        return get_trade_history(conn, ticker, limit)


@app.get("/markets/{ticker}/price", summary="Current YES price (cents) for a ticker")
def market_price(ticker: str):
    with get_conn() as conn:
        price = get_latest_yes_price(conn, ticker)
    if price is None:
        raise HTTPException(404, detail=f"No price data for {ticker}")
    return {"ticker": ticker, "yes_price": price}


# ── Backtest route ─────────────────────────────────────────────────────────────

@app.post("/backtest", summary="Run walk-forward backtest and return report")
def backtest(req: BacktestRequest):
    result = run_backtest(
        ticker=req.ticker,
        strategy=req.strategy,
        lookback=req.lookback,
        edge_threshold=req.edge_threshold,
        half_kelly=req.half_kelly,
    )
    if "error" in result:
        raise HTTPException(400, detail=result["error"])
    return result


# ── Health check ───────────────────────────────────────────────────────────────

@app.get("/health")
def health():
    return {
        "status": "ok",
        "db_path": os.environ.get("KALSHI_DB_PATH", "kalshi.db"),
        "server_time": datetime.now(timezone.utc).isoformat(),
    }
