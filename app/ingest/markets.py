from __future__ import annotations

import json
import logging
import time
from dataclasses import dataclass
from pathlib import Path

from app.client import KalshiHttpClient
from app.dto import MarketDTO
from app.storage.repositories import CheckpointRepository, Market, MarketRepository

logger = logging.getLogger(__name__)

MARKETS_PATH = "/trade-api/v2/markets"
MARKETS_CHECKPOINT_KEY = "markets_sync_cursor"
DEBUG_LOG_PATH = Path("/Users/happy/Documents/kalshi-pipeline/.cursor/debug.log")


@dataclass(frozen=True)
class MarketSyncResult:
    pages_processed: int
    markets_upserted: int
    checkpoint_value: str


def _debug_log(
    *,
    run_id: str,
    hypothesis_id: str,
    location: str,
    message: str,
    data: dict[str, object],
) -> None:
    payload = {
        "id": f"{run_id}_{hypothesis_id}_{int(time.time() * 1000)}",
        "timestamp": int(time.time() * 1000),
        "runId": run_id,
        "hypothesisId": hypothesis_id,
        "location": location,
        "message": message,
        "data": data,
    }
    try:
        with DEBUG_LOG_PATH.open("a", encoding="utf-8") as debug_file:
            debug_file.write(json.dumps(payload) + "\n")
    except Exception:
        pass


async def sync_markets(
    client: KalshiHttpClient,
    market_repository: MarketRepository,
    checkpoint_repository: CheckpointRepository,
    page_size: int = 200,
    checkpoint_key: str = MARKETS_CHECKPOINT_KEY,
    status: str | None = None,
    series_ticker: str | None = None,
    min_close_ts: int | None = None,
    max_close_ts: int | None = None,
    watchlist_tickers: list[str] | None = None,
) -> MarketSyncResult:
    watchlist = _normalize_watchlist_tickers(watchlist_tickers)
    use_checkpoint = not watchlist
    checkpoint = checkpoint_repository.get(checkpoint_key) if use_checkpoint else None
    cursor = checkpoint.value if checkpoint is not None else ""
    pages_processed = 0
    markets_upserted = 0
    run_id = f"sync_markets_{int(time.time() * 1000)}"

    # #region agent log
    _debug_log(
        run_id=run_id,
        hypothesis_id="H0",
        location="app/ingest/markets.py:sync_markets:entry",
        message="sync_markets_started",
        data={
            "initial_cursor": cursor,
            "page_size": page_size,
            "checkpoint_exists": checkpoint is not None,
            "mode": "watchlist" if watchlist else "discovery",
        },
    )
    # #endregion

    while True:
        params = _build_market_params(
            cursor=cursor,
            limit=page_size,
            status=status if not watchlist else None,
            series_ticker=series_ticker if not watchlist else None,
            min_close_ts=min_close_ts if not watchlist else None,
            max_close_ts=max_close_ts if not watchlist else None,
            tickers=watchlist,
        )
        logger.info(
            "Requesting Kalshi markets page",
            extra={"path": MARKETS_PATH, "cursor": cursor or None, "params": params},
        )
        response = await client.get(path=MARKETS_PATH, params=params, authenticated=False)
        payload = response.json()

        market_payloads = payload.get("markets", [])
        page_markets = [_market_from_dto(MarketDTO.model_validate(item)) for item in market_payloads]
        upserted_count = market_repository.upsert_many(page_markets)
        next_cursor = _normalize_cursor(payload.get("cursor"))
        cursor_stalled = bool(next_cursor) and next_cursor == cursor

        # #region agent log
        _debug_log(
            run_id=run_id,
            hypothesis_id="H1",
            location="app/ingest/markets.py:sync_markets:loop",
            message="cursor_transition_observed",
            data={
                "page_number_next": pages_processed + 1,
                "current_cursor": cursor,
                "next_cursor": next_cursor,
                "cursor_stalled": cursor_stalled,
                "market_payload_count": len(market_payloads),
                "upserted_count": upserted_count,
            },
        )
        # #endregion

        pages_processed += 1
        markets_upserted += upserted_count
        if use_checkpoint:
            checkpoint_repository.set(checkpoint_key, next_cursor)

        logger.info(
            "Processed Kalshi markets page",
            extra={
                "path": MARKETS_PATH,
                "page_number": pages_processed,
                "market_count": upserted_count,
                "next_cursor": next_cursor or None,
            },
        )

        if cursor_stalled:
            logger.warning(
                "Detected cursor stall while syncing markets; stopping pagination",
                extra={
                    "path": MARKETS_PATH,
                    "cursor": cursor,
                    "next_cursor": next_cursor,
                    "page_number": pages_processed,
                },
            )
            # #region agent log
            _debug_log(
                run_id=run_id,
                hypothesis_id="H3",
                location="app/ingest/markets.py:sync_markets:cursor_stall_exit",
                message="cursor_stall_guard_triggered",
                data={
                    "pages_processed": pages_processed,
                    "markets_upserted": markets_upserted,
                    "cursor": cursor,
                    "next_cursor": next_cursor,
                },
            )
            # #endregion
            return MarketSyncResult(
                pages_processed=pages_processed,
                markets_upserted=markets_upserted,
                checkpoint_value=next_cursor,
            )

        if not next_cursor:
            # #region agent log
            _debug_log(
                run_id=run_id,
                hypothesis_id="H2",
                location="app/ingest/markets.py:sync_markets:exit",
                message="pagination_ended_with_empty_cursor",
                data={
                    "pages_processed": pages_processed,
                    "markets_upserted": markets_upserted,
                },
            )
            # #endregion
            return MarketSyncResult(
                pages_processed=pages_processed,
                markets_upserted=markets_upserted,
                checkpoint_value=next_cursor,
            )

        cursor = next_cursor


def _build_market_params(
    cursor: str,
    limit: int,
    status: str | None = None,
    series_ticker: str | None = None,
    min_close_ts: int | None = None,
    max_close_ts: int | None = None,
    tickers: list[str] | None = None,
) -> dict[str, str | int]:
    params: dict[str, str | int] = {"limit": limit}
    if cursor:
        params["cursor"] = cursor
    if status:
        params["status"] = status
    if series_ticker:
        params["series_ticker"] = series_ticker
    if min_close_ts is not None:
        params["min_close_ts"] = min_close_ts
    if max_close_ts is not None:
        params["max_close_ts"] = max_close_ts
    if tickers:
        params["tickers"] = ",".join(tickers)

    return params


def _market_from_dto(market: MarketDTO) -> Market:
    return Market(
        market_ticker=market.market_ticker,
        event_ticker=market.event_ticker,
        title=market.title,
        status=market.status,
        close_time=market.close_time,
        expiration_time=market.expiration_time,
        strike_type=market.strike_type,
        yes_sub_title=market.yes_sub_title,
        no_sub_title=market.no_sub_title,
        last_price=market.last_price,
        last_updated_ts=market.last_updated_ts or "",
    )


def _normalize_cursor(value: object) -> str:
    if value is None:
        return ""

    return str(value)


def _normalize_watchlist_tickers(value: list[str] | None) -> list[str]:
    if value is None:
        return []

    return [ticker.strip() for ticker in value if ticker.strip()]
