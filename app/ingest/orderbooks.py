from __future__ import annotations

import asyncio
import logging
import time
from dataclasses import dataclass
from datetime import UTC, datetime
from urllib.parse import quote

from app.client import KalshiHttpClient
from app.storage.repositories import (
    MarketRepository,
    OrderbookLevel,
    OrderbookSnapshotRepository,
)

logger = logging.getLogger(__name__)

ORDERBOOK_PATH_PREFIX = "/trade-api/v2/markets"


@dataclass(frozen=True)
class OrderbookPollResult:
    polls_completed: int
    markets_processed: int
    levels_inserted: int


async def poll_orderbooks(
    client: KalshiHttpClient,
    orderbook_repository: OrderbookSnapshotRepository,
    market_repository: MarketRepository,
    market_tickers: list[str],
    poll_interval_seconds: float = 5.0,
    max_polls: int | None = None,
) -> OrderbookPollResult:
    polls_completed = 0
    levels_inserted = 0

    while max_polls is None or polls_completed < max_polls:
        for market_ticker in market_tickers:
            market = market_repository.get(market_ticker)
            if market is None:
                raise ValueError(
                    f"Market '{market_ticker}' must exist before polling orderbooks"
                )

            path = build_orderbook_path(market_ticker)
            logger.info(
                "Requesting Kalshi orderbook snapshot",
                extra={"path": path, "market_ticker": market_ticker},
            )
            response = await client.get(path=path, authenticated=False)
            payload = response.json()
            levels = flatten_orderbook_snapshot(payload=payload, market_ticker=market_ticker)
            inserted_count = orderbook_repository.insert_snapshot(levels)
            levels_inserted += inserted_count

            logger.info(
                "Stored Kalshi orderbook snapshot",
                extra={
                    "path": path,
                    "market_ticker": market_ticker,
                    "levels_inserted": inserted_count,
                    "snapshot_ts_ms": levels[0].snapshot_ts_ms if levels else None,
                },
            )

        polls_completed += 1

        if max_polls is not None and polls_completed >= max_polls:
            break

        await asyncio.sleep(poll_interval_seconds)

    return OrderbookPollResult(
        polls_completed=polls_completed,
        markets_processed=len(market_tickers) * polls_completed,
        levels_inserted=levels_inserted,
    )


def build_orderbook_path(market_ticker: str) -> str:
    encoded_ticker = quote(market_ticker, safe="")
    return f"{ORDERBOOK_PATH_PREFIX}/{encoded_ticker}/orderbook"


def flatten_orderbook_snapshot(
    payload: object,
    market_ticker: str,
    collected_ts_ms: int | None = None,
) -> list[OrderbookLevel]:
    orderbook_payload = _extract_orderbook_payload(payload)
    snapshot_ts_ms = _extract_snapshot_ts_ms(orderbook_payload)
    resolved_collected_ts_ms = (
        collected_ts_ms if collected_ts_ms is not None else _current_time_ms()
    )

    levels: list[OrderbookLevel] = []
    for side in ("yes", "no"):
        raw_levels = orderbook_payload.get(side, [])
        if not isinstance(raw_levels, list):
            raise ValueError(f"Orderbook side '{side}' must be a list")

        for raw_level in raw_levels:
            price, quantity = _parse_level(raw_level)
            levels.append(
                OrderbookLevel(
                    market_ticker=market_ticker,
                    snapshot_ts_ms=snapshot_ts_ms,
                    side=side,
                    price=price,
                    quantity=quantity,
                    collected_ts_ms=resolved_collected_ts_ms,
                )
            )

    return levels


def _extract_orderbook_payload(payload: object) -> dict[str, object]:
    if not isinstance(payload, dict):
        raise ValueError("Orderbook response payload must be a JSON object")

    if "orderbook" in payload:
        nested_payload = payload["orderbook"]
        if not isinstance(nested_payload, dict):
            raise ValueError(
                "Orderbook response payload field 'orderbook' must be an object"
            )
        return nested_payload

    return payload


def _extract_snapshot_ts_ms(payload: dict[str, object]) -> int:
    raw_timestamp = (
        payload.get("snapshot_ts_ms") or payload.get("snapshot_ts") or payload.get("ts")
    )
    if raw_timestamp is None:
        return _current_time_ms()

    return _coerce_timestamp_ms(raw_timestamp)


def _parse_level(raw_level: object) -> tuple[int, int]:
    if isinstance(raw_level, dict):
        return _parse_level_mapping(raw_level)

    if isinstance(raw_level, (list, tuple)) and len(raw_level) == 2:
        return int(raw_level[0]), int(raw_level[1])

    raise ValueError("Orderbook level must be an object or a two-item sequence")


def _parse_level_mapping(raw_level: dict[str, object]) -> tuple[int, int]:
    raw_price = raw_level.get("price")
    raw_quantity = raw_level.get("quantity", raw_level.get("count"))

    if raw_price is None or raw_quantity is None:
        raise ValueError("Orderbook level object must include price and quantity/count")

    return int(raw_price), int(raw_quantity)


def _coerce_timestamp_ms(value: object) -> int:
    if isinstance(value, int):
        return value

    if isinstance(value, float):
        return int(value)

    if isinstance(value, str):
        stripped = value.strip()
        if stripped.isdigit():
            return int(stripped)

        parsed = datetime.fromisoformat(stripped.replace("Z", "+00:00"))
        return int(parsed.astimezone(UTC).timestamp() * 1000)

    raise ValueError(
        "Orderbook snapshot timestamp must be an int, float, or ISO timestamp string"
    )


def _current_time_ms() -> int:
    return time.time_ns() // 1_000_000
