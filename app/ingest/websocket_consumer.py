from __future__ import annotations

import asyncio
import json
import logging
import ssl
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from typing import Any

from app.ingest.orderbooks import flatten_orderbook_snapshot
from app.ingest.trades import _normalize_trade_payload
from app.storage.repositories import (
    EventRepository,
    MarketRepository,
    OrderbookSnapshotRepository,
    TradeRepository,
)

logger = logging.getLogger(__name__)

STOP_SIGNAL = object()
SUPPORTED_TRADE_MESSAGE_TYPES = frozenset({"trade", "trade_update"})
SUPPORTED_ORDERBOOK_MESSAGE_TYPES = frozenset(
    {"orderbook", "orderbook_snapshot", "orderbook_update"}
)

SleepFn = Callable[[float], Awaitable[object]]
WebSocketConnectFn = Callable[[str], Any]


@dataclass(frozen=True)
class StreamStats:
    messages_read: int
    messages_processed: int
    trades_upserted: int
    orderbook_levels_inserted: int


def build_subscribe_message(market_tickers: list[str]) -> str:
    return json.dumps(
        {
            "id": 1,
            "cmd": "subscribe",
            "params": {
                "channels": ["trade", "orderbook_snapshot"],
                "market_tickers": market_tickers,
            },
        }
    )


async def stream_market_data(
    ws_url: str,
    market_tickers: list[str],
    trade_repository: TradeRepository,
    orderbook_repository: OrderbookSnapshotRepository,
    market_repository: MarketRepository,
    event_repository: EventRepository,
    ws_headers: dict[str, str] | None = None,
    connect_fn: WebSocketConnectFn | None = None,
    queue_maxsize: int = 1_000,
) -> None:
    queue: asyncio.Queue[object] = asyncio.Queue(maxsize=queue_maxsize)
    reader_task = asyncio.create_task(
        websocket_reader(
            queue=queue,
            ws_url=ws_url,
            market_tickers=market_tickers,
            ws_headers=ws_headers,
            connect_fn=connect_fn,
        )
    )
    consumer_task = asyncio.create_task(
        queue_consumer(
            queue=queue,
            trade_repository=trade_repository,
            orderbook_repository=orderbook_repository,
            market_repository=market_repository,
            event_repository=event_repository,
        )
    )

    try:
        await asyncio.gather(reader_task, consumer_task)
    finally:
        reader_task.cancel()
        consumer_task.cancel()
        await asyncio.gather(reader_task, consumer_task, return_exceptions=True)


async def websocket_reader(
    queue: asyncio.Queue[object],
    ws_url: str,
    market_tickers: list[str],
    ws_headers: dict[str, str] | None = None,
    connect_fn: WebSocketConnectFn | None = None,
    sleep_fn: SleepFn = asyncio.sleep,
    max_backoff_seconds: float = 30.0,
) -> None:
    backoff_seconds = 1.0
    subscribe_message = build_subscribe_message(market_tickers)

    while True:
        try:
            async with _connect_websocket(
                ws_url=ws_url,
                ws_headers=ws_headers,
                connect_fn=connect_fn,
            ) as websocket:
                await websocket.send(subscribe_message)
                logger.info(
                    "Subscribed to Kalshi WebSocket market data",
                    extra={"market_tickers": market_tickers},
                )
                backoff_seconds = 1.0

                while True:
                    raw_message = await websocket.recv()
                    payload = _deserialize_websocket_message(raw_message)
                    await queue.put(payload)
        except asyncio.CancelledError:
            raise
        except Exception as exc:
            logger.warning(
                "Kalshi WebSocket reader disconnected; retrying",
                extra={"ws_url": ws_url, "backoff_seconds": backoff_seconds, "error": str(exc)},
            )
            await sleep_fn(backoff_seconds)
            backoff_seconds = min(backoff_seconds * 2, max_backoff_seconds)


async def queue_consumer(
    queue: asyncio.Queue[object],
    trade_repository: TradeRepository,
    orderbook_repository: OrderbookSnapshotRepository,
    market_repository: MarketRepository,
    event_repository: EventRepository,
) -> StreamStats:
    messages_processed = 0
    trades_upserted = 0
    orderbook_levels_inserted = 0

    while True:
        item = await queue.get()
        try:
            if item is STOP_SIGNAL:
                return StreamStats(
                    messages_read=messages_processed,
                    messages_processed=messages_processed,
                    trades_upserted=trades_upserted,
                    orderbook_levels_inserted=orderbook_levels_inserted,
                )

            processed_trade_count, processed_orderbook_count = _consume_supported_message(
                payload=item,
                trade_repository=trade_repository,
                orderbook_repository=orderbook_repository,
                market_repository=market_repository,
                event_repository=event_repository,
            )
            if processed_trade_count or processed_orderbook_count:
                messages_processed += 1
                trades_upserted += processed_trade_count
                orderbook_levels_inserted += processed_orderbook_count
        finally:
            queue.task_done()


def _consume_supported_message(
    payload: object,
    trade_repository: TradeRepository,
    orderbook_repository: OrderbookSnapshotRepository,
    market_repository: MarketRepository,
    event_repository: EventRepository,
) -> tuple[int, int]:
    if not isinstance(payload, dict):
        logger.debug("Ignoring non-object WebSocket payload")
        return 0, 0

    message_type = _extract_message_type(payload)
    if message_type is None:
        return 0, 0

    normalized_type = message_type.strip().lower()
    if normalized_type in SUPPORTED_TRADE_MESSAGE_TYPES:
        _consume_trade_message(
            payload=payload,
            trade_repository=trade_repository,
            market_repository=market_repository,
            event_repository=event_repository,
        )
        return 1, 0

    if normalized_type in SUPPORTED_ORDERBOOK_MESSAGE_TYPES:
        inserted_count = _consume_orderbook_message(
            payload=payload,
            orderbook_repository=orderbook_repository,
            market_repository=market_repository,
        )
        return 0, inserted_count

    return 0, 0


def _consume_trade_message(
    payload: dict[str, object],
    trade_repository: TradeRepository,
    market_repository: MarketRepository,
    event_repository: EventRepository,
) -> None:
    message_body = _extract_message_body(payload)
    market_ticker = _extract_market_ticker(message_body)
    market = market_repository.get(market_ticker)
    if market is None:
        raise ValueError(f"Market '{market_ticker}' must exist before streaming trades")

    event = event_repository.get(market.event_ticker)
    trade = _normalize_trade_payload(
        payload=message_body,
        market_ticker=market_ticker,
        event_status=event.status if event is not None else None,
        event_start_time=event.start_time if event is not None else None,
        event_settlement_time=event.settlement_time if event is not None else None,
    )
    trade_repository.upsert(trade)


def _consume_orderbook_message(
    payload: dict[str, object],
    orderbook_repository: OrderbookSnapshotRepository,
    market_repository: MarketRepository,
) -> int:
    message_body = _extract_message_body(payload)
    market_ticker = _extract_market_ticker(message_body)
    if market_repository.get(market_ticker) is None:
        raise ValueError(f"Market '{market_ticker}' must exist before streaming orderbooks")

    levels = flatten_orderbook_snapshot(payload=message_body, market_ticker=market_ticker)
    return orderbook_repository.insert_snapshot(levels)


def _extract_message_type(payload: dict[str, object]) -> str | None:
    raw_message_type = payload.get("type") or payload.get("msg_type")
    if raw_message_type is None:
        return None

    return str(raw_message_type)


def _extract_message_body(payload: dict[str, object]) -> dict[str, object]:
    for key in ("data", "msg", "message"):
        nested_payload = payload.get(key)
        if isinstance(nested_payload, dict):
            return nested_payload

    return payload


def _extract_market_ticker(payload: dict[str, object]) -> str:
    raw_market_ticker = payload.get("market_ticker") or payload.get("ticker")
    if raw_market_ticker is None:
        raise ValueError("Streaming message payload is missing market_ticker")

    return str(raw_market_ticker)


def _deserialize_websocket_message(raw_message: object) -> object:
    if isinstance(raw_message, bytes):
        raw_message = raw_message.decode("utf-8")

    if isinstance(raw_message, str):
        return json.loads(raw_message)

    return raw_message


def _connect_websocket(
    ws_url: str,
    ws_headers: dict[str, str] | None,
    connect_fn: WebSocketConnectFn | None,
) -> Any:
    if connect_fn is not None:
        return connect_fn(ws_url)

    import certifi
    import websockets

    ssl_context = ssl.create_default_context(cafile=certifi.where())
    return websockets.connect(
        ws_url,
        ssl=ssl_context,
        additional_headers=ws_headers,
    )
