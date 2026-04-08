from pathlib import Path

import httpx
import pytest

from app.client import KalshiHttpClient
from app.ingest.orderbooks import flatten_orderbook_snapshot, poll_orderbooks
from app.storage.db import bootstrap_schema, get_sqlite_connection
from app.storage.repositories import (
    Event,
    EventRepository,
    Market,
    MarketRepository,
    OrderbookSnapshotRepository,
)


@pytest.fixture
def anyio_backend() -> str:
    return "asyncio"


def test_flatten_orderbook_snapshot_creates_one_row_per_side_and_price_level() -> None:
    levels = flatten_orderbook_snapshot(
        payload={
            "orderbook": {
                "snapshot_ts": 1_712_580_000_123,
                "yes": [[61, 14], {"price": 62, "quantity": 9}],
                "no": [{"price": 38, "count": 7}],
            }
        },
        market_ticker="FED-2026-RATE-HIKE",
        collected_ts_ms=1_712_580_000_999,
    )

    assert len(levels) == 3
    assert levels[0].market_ticker == "FED-2026-RATE-HIKE"
    assert levels[0].snapshot_ts_ms == 1_712_580_000_123
    assert levels[0].side == "yes"
    assert levels[0].price == 61
    assert levels[0].quantity == 14
    assert levels[0].collected_ts_ms == 1_712_580_000_999
    assert levels[1].side == "yes"
    assert levels[1].price == 62
    assert levels[1].quantity == 9
    assert levels[2].side == "no"
    assert levels[2].price == 38
    assert levels[2].quantity == 7


@pytest.mark.anyio
async def test_poll_orderbooks_persists_flattened_snapshot_rows(tmp_path: Path) -> None:
    db_path = tmp_path / "orderbooks.sqlite3"

    async def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.path == "/trade-api/v2/markets/FED-2026-RATE-HIKE/orderbook"
        return httpx.Response(
            200,
            json={
                "orderbook": {
                    "snapshot_ts": 1_712_580_100_000,
                    "yes": [
                        [61, 14],
                        [62, 9],
                    ],
                    "no": [
                        [38, 7],
                    ],
                }
            },
        )

    transport = httpx.MockTransport(handler)

    with get_sqlite_connection(db_path) as connection:
        bootstrap_schema(connection)
        event_repository = EventRepository(connection)
        market_repository = MarketRepository(connection)
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

        async with KalshiHttpClient(
            base_url="https://demo-api.kalshi.co",
            transport=transport,
        ) as client:
            result = await poll_orderbooks(
                client=client,
                orderbook_repository=orderbook_repository,
                market_repository=market_repository,
                market_tickers=["FED-2026-RATE-HIKE"],
                poll_interval_seconds=0.0,
                max_polls=1,
            )

        rows = orderbook_repository.list_for_snapshot(
            market_ticker="FED-2026-RATE-HIKE",
            snapshot_ts_ms=1_712_580_100_000,
        )

    assert result.polls_completed == 1
    assert result.markets_processed == 1
    assert result.levels_inserted == 3
    assert [(row.side, row.price, row.quantity) for row in rows] == [
        ("no", 38, 7),
        ("yes", 61, 14),
        ("yes", 62, 9),
    ]
    assert all(row.collected_ts_ms > 0 for row in rows)
