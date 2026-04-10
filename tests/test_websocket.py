import asyncio
import json
from pathlib import Path

import pytest

from app.ingest.websocket_consumer import STOP_SIGNAL, queue_consumer, websocket_reader
from app.storage.db import bootstrap_schema, get_sqlite_connection
from app.storage.repositories import (
    Event,
    EventRepository,
    Market,
    MarketRepository,
    OrderbookSnapshotRepository,
    TradeRepository,
)


class FakeWebSocket:
    def __init__(self, messages: list[object]) -> None:
        self._messages = messages
        self._index = 0
        self.sent_messages: list[str] = []

    async def send(self, message: str) -> None:
        self.sent_messages.append(message)

    async def recv(self) -> object:
        if self._index >= len(self._messages):
            await asyncio.Future[None]()

        message = self._messages[self._index]
        self._index += 1
        return message


class FakeWebSocketContext:
    def __init__(self, websocket: FakeWebSocket) -> None:
        self.websocket = websocket

    async def __aenter__(self) -> FakeWebSocket:
        return self.websocket

    async def __aexit__(self, exc_type: object, exc: object, tb: object) -> None:
        return None


@pytest.fixture
def anyio_backend() -> str:
    return "asyncio"


@pytest.mark.anyio
async def test_queue_consumer_processes_supported_messages_and_ignores_malformed_items(
    tmp_path: Path,
) -> None:
    db_path = tmp_path / "stream.sqlite3"
    queue: asyncio.Queue[object] = asyncio.Queue()

    with get_sqlite_connection(db_path) as connection:
        bootstrap_schema(connection)
        event_repository = EventRepository(connection)
        market_repository = MarketRepository(connection)
        trade_repository = TradeRepository(connection)
        orderbook_repository = OrderbookSnapshotRepository(connection)

        event_repository.upsert(
            Event(
                event_ticker="FED-2026-RATE",
                title="Fed decision",
                category="economics",
                status="open",
                start_time="2026-04-08T13:00:00Z",
                settlement_time="2026-04-08T15:00:00Z",
                last_updated_ts="2026-04-08T12:00:00Z",
            )
        )
        market_repository.upsert(
            Market(
                market_ticker="FED-2026-RATE-HIKE",
                event_ticker="FED-2026-RATE",
                title="Rate hike yes",
                status="active",
                close_time=None,
                expiration_time=None,
                strike_type=None,
                yes_sub_title=None,
                no_sub_title=None,
                last_price=None,
                last_updated_ts="2026-04-08T12:00:00Z",
            )
        )

        await queue.put(
            {
                "type": "trade",
                "data": {
                    "ticker": "FED-2026-RATE-HIKE",
                    "id": "trade-001",
                    "side": "yes",
                    "price": 57,
                    "count": 2,
                    "created_time": "2026-04-08T12:59:00Z",
                },
            }
        )
        await queue.put(["not", "a", "message", "object"])
        await queue.put({"data": {"ticker": "FED-2026-RATE-HIKE"}})
        await queue.put(
            {
                "type": "orderbook_snapshot",
                "data": {
                    "ticker": "FED-2026-RATE-HIKE",
                    "snapshot_ts": 1_712_580_100_000,
                    "yes": [[61, 14]],
                    "no": [[38, 7]],
                },
            }
        )
        await queue.put(STOP_SIGNAL)

        stats = await queue_consumer(
            queue=queue,
            trade_repository=trade_repository,
            orderbook_repository=orderbook_repository,
            market_repository=market_repository,
            event_repository=event_repository,
        )

        saved_trade = trade_repository.get("FED-2026-RATE-HIKE", "trade-001")
        saved_levels = orderbook_repository.list_for_snapshot(
            market_ticker="FED-2026-RATE-HIKE",
            snapshot_ts_ms=1_712_580_100_000,
        )

    assert stats.messages_read == 2
    assert stats.messages_processed == 2
    assert stats.trades_upserted == 1
    assert stats.orderbook_levels_inserted == 2
    assert saved_trade is not None
    assert saved_trade.phase == "pre_game"
    assert [(level.side, level.price, level.quantity) for level in saved_levels] == [
        ("no", 38, 7),
        ("yes", 61, 14),
    ]


@pytest.mark.anyio
async def test_websocket_reader_retries_after_malformed_json_message() -> None:
    queue: asyncio.Queue[object] = asyncio.Queue()
    sleep_calls: list[float] = []
    attempts = 0
    first_websocket = FakeWebSocket(messages=['{"type": "trade",'])
    second_websocket = FakeWebSocket(messages=[])

    async def sleep_fn(delay_seconds: float) -> None:
        sleep_calls.append(delay_seconds)

    def connect_fn(ws_url: str) -> FakeWebSocketContext:
        nonlocal attempts
        attempts += 1
        assert ws_url == "wss://demo-api.kalshi.co/trade-api/ws/v2"
        if attempts == 1:
            return FakeWebSocketContext(first_websocket)
        return FakeWebSocketContext(second_websocket)

    task = asyncio.create_task(
        websocket_reader(
            queue=queue,
            ws_url="wss://demo-api.kalshi.co/trade-api/ws/v2",
            market_tickers=["FED-2026-RATE-HIKE"],
            connect_fn=connect_fn,
            sleep_fn=sleep_fn,
        )
    )

    await asyncio.sleep(0)
    await asyncio.sleep(0)
    task.cancel()
    await asyncio.gather(task, return_exceptions=True)

    assert queue.empty()
    assert attempts >= 2
    assert sleep_calls == [1.0]
    assert first_websocket.sent_messages == [
        json.dumps(
            {
                "id": 1,
                "cmd": "subscribe",
                "params": {
                    "channels": ["trade", "orderbook_snapshot"],
                    "market_tickers": ["FED-2026-RATE-HIKE"],
                },
            }
        )
    ]
    assert second_websocket.sent_messages == first_websocket.sent_messages


@pytest.mark.anyio
async def test_websocket_reader_caps_reconnect_backoff() -> None:
    queue: asyncio.Queue[object] = asyncio.Queue()
    sleep_calls: list[float] = []

    async def sleep_fn(delay_seconds: float) -> None:
        sleep_calls.append(delay_seconds)
        if len(sleep_calls) == 4:
            raise asyncio.CancelledError

    def connect_fn(ws_url: str) -> FakeWebSocketContext:
        raise RuntimeError(f"failed to connect to {ws_url}")

    with pytest.raises(asyncio.CancelledError):
        await websocket_reader(
            queue=queue,
            ws_url="wss://demo-api.kalshi.co/trade-api/ws/v2",
            market_tickers=["FED-2026-RATE-HIKE"],
            connect_fn=connect_fn,
            sleep_fn=sleep_fn,
            max_backoff_seconds=3.0,
        )

    assert sleep_calls == [1.0, 2.0, 3.0, 3.0]
