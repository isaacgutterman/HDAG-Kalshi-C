from __future__ import annotations

import logging
from dataclasses import dataclass

from app.client import KalshiHttpClient
from app.dto import MarketDTO
from app.storage.repositories import CheckpointRepository, Market, MarketRepository

logger = logging.getLogger(__name__)

MARKETS_PATH = "/trade-api/v2/markets"
MARKETS_CHECKPOINT_KEY = "markets_sync_cursor"


@dataclass(frozen=True)
class MarketSyncResult:
    pages_processed: int
    markets_upserted: int
    checkpoint_value: str


async def sync_markets(
    client: KalshiHttpClient,
    market_repository: MarketRepository,
    checkpoint_repository: CheckpointRepository,
    page_size: int = 200,
    checkpoint_key: str = MARKETS_CHECKPOINT_KEY,
) -> MarketSyncResult:
    checkpoint = checkpoint_repository.get(checkpoint_key)
    cursor = checkpoint.value if checkpoint is not None else ""
    pages_processed = 0
    markets_upserted = 0

    while True:
        params = _build_market_params(cursor=cursor, limit=page_size)
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

        pages_processed += 1
        markets_upserted += upserted_count
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

        if not next_cursor:
            return MarketSyncResult(
                pages_processed=pages_processed,
                markets_upserted=markets_upserted,
                checkpoint_value=next_cursor,
            )

        cursor = next_cursor


def _build_market_params(cursor: str, limit: int) -> dict[str, str | int]:
    params: dict[str, str | int] = {"limit": limit}
    if cursor:
        params["cursor"] = cursor

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
