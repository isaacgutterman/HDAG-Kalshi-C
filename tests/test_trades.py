from pathlib import Path
from urllib.parse import parse_qs, urlparse

import httpx
import pytest

from app.client import KalshiHttpClient
from app.ingest.trades import sync_trades
from app.storage.db import bootstrap_schema, get_sqlite_connection
from app.storage.repositories import (
    CheckpointRepository,
    Event,
    EventRepository,
    Market,
    MarketRepository,
    Trade,
    TradeRepository,
)


@pytest.fixture
def anyio_backend() -> str:
    return "asyncio"


def test_trade_repository_upsert_deduplicates_existing_trade(tmp_path: Path) -> None:
    db_path = tmp_path / "trades.sqlite3"

    with get_sqlite_connection(db_path) as connection:
        bootstrap_schema(connection)
        event_repository = EventRepository(connection)
        market_repository = MarketRepository(connection)
        repository = TradeRepository(connection)

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

        first_trade = Trade(
            market_ticker="FED-2026-RATE-HIKE",
            trade_id="trade-001",
            side="yes",
            price=57,
            count=3,
            trade_ts="2026-04-08T12:59:00Z",
            phase="pre_game",
            collected_ts="2026-04-08T13:00:00Z",
        )
        updated_trade = Trade(
            market_ticker="FED-2026-RATE-HIKE",
            trade_id="trade-001",
            side="yes",
            price=58,
            count=4,
            trade_ts="2026-04-08T13:00:00Z",
            phase="live",
            collected_ts="2026-04-08T13:01:00Z",
        )

        saved_trade = repository.upsert(first_trade)
        reloaded_trade = repository.upsert(updated_trade)
        row_count = connection.execute("SELECT COUNT(*) AS count FROM trades").fetchone()

    assert saved_trade == first_trade
    assert reloaded_trade == updated_trade
    assert row_count is not None
    assert row_count["count"] == 1


@pytest.mark.anyio
async def test_sync_trades_paginates_tags_phase_and_updates_checkpoint(tmp_path: Path) -> None:
    db_path = tmp_path / "trades.sqlite3"
    requested_cursors: list[str | None] = []

    async def handler(request: httpx.Request) -> httpx.Response:
        query_params = parse_qs(urlparse(str(request.url)).query)
        cursor = query_params.get("cursor", [None])[0]
        assert request.url.path == "/trade-api/v2/markets/FED-2026-RATE-HIKE/trades"
        assert query_params["limit"] == ["100"]
        requested_cursors.append(cursor)

        if cursor is None:
            return httpx.Response(
                200,
                json={
                    "trades": [
                        {
                            "id": "trade-001",
                            "side": "yes",
                            "price": 57,
                            "count": 2,
                            "created_time": "2026-04-08T12:59:00Z",
                        }
                    ],
                    "cursor": "cursor-002",
                },
            )

        return httpx.Response(
            200,
            json={
                "trades": [
                    {
                        "id": "trade-002",
                        "side": "no",
                        "price": 42,
                        "count": 1,
                        "created_time": "2026-04-08T13:01:00Z",
                    }
                ],
                "cursor": None,
            },
        )

    transport = httpx.MockTransport(handler)

    with get_sqlite_connection(db_path) as connection:
        bootstrap_schema(connection)
        event_repository = EventRepository(connection)
        market_repository = MarketRepository(connection)
        trade_repository = TradeRepository(connection)
        checkpoint_repository = CheckpointRepository(connection)

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
            result = await sync_trades(
                client=client,
                trade_repository=trade_repository,
                checkpoint_repository=checkpoint_repository,
                market_repository=market_repository,
                event_repository=event_repository,
                market_tickers=["FED-2026-RATE-HIKE"],
                page_size=100,
            )

        first_trade = trade_repository.get("FED-2026-RATE-HIKE", "trade-001")
        second_trade = trade_repository.get("FED-2026-RATE-HIKE", "trade-002")
        checkpoint = checkpoint_repository.get("trades_sync_cursor:FED-2026-RATE-HIKE")

    assert requested_cursors == [None, "cursor-002"]
    assert result.markets_processed == 1
    assert result.trades_upserted == 2
    assert first_trade is not None
    assert first_trade.phase == "pre_game"
    assert second_trade is not None
    assert second_trade.phase == "live"
    assert checkpoint is not None
    assert checkpoint.value == ""
