from pathlib import Path
from urllib.parse import parse_qs, urlparse

import httpx
import pytest

from app.client import KalshiHttpClient
from app.ingest.markets import sync_markets
from app.storage.db import bootstrap_schema, get_sqlite_connection
from app.storage.repositories import CheckpointRepository, Market, MarketRepository


@pytest.fixture
def anyio_backend() -> str:
    return "asyncio"


def test_market_repository_upsert_inserts_and_updates_market(tmp_path: Path) -> None:
    db_path = tmp_path / "markets.sqlite3"

    first_market = Market(
        market_ticker="FED-2026-RATE-HIKE",
        event_ticker="FED-2026-RATE",
        title="Rate hike yes",
        status="active",
        close_time="2026-04-08T15:00:00Z",
        expiration_time=None,
        strike_type=None,
        yes_sub_title="Yes",
        no_sub_title="No",
        last_price=57,
        last_updated_ts="2026-04-08T12:00:00Z",
    )
    updated_market = Market(
        market_ticker="FED-2026-RATE-HIKE",
        event_ticker="FED-2026-RATE",
        title="Rate hike very likely",
        status="closed",
        close_time="2026-04-08T16:00:00Z",
        expiration_time="2026-04-08T16:05:00Z",
        strike_type="binary",
        yes_sub_title="Up",
        no_sub_title="Down",
        last_price=61,
        last_updated_ts="2026-04-08T13:00:00Z",
    )

    with get_sqlite_connection(db_path) as connection:
        bootstrap_schema(connection)
        repository = MarketRepository(connection)

        saved_market = repository.upsert(first_market)
        reloaded_market = repository.upsert(updated_market)

        event_row = connection.execute(
            "SELECT event_ticker, title FROM events WHERE event_ticker = ?",
            (first_market.event_ticker,),
        ).fetchone()

    assert saved_market == first_market
    assert reloaded_market == updated_market
    assert event_row is not None
    assert event_row["event_ticker"] == "FED-2026-RATE"
    assert event_row["title"] == "FED-2026-RATE"


@pytest.mark.anyio
async def test_sync_markets_paginates_and_updates_checkpoint(tmp_path: Path) -> None:
    db_path = tmp_path / "markets.sqlite3"
    requested_cursors: list[str | None] = []

    async def handler(request: httpx.Request) -> httpx.Response:
        query_params = parse_qs(urlparse(str(request.url)).query)
        cursor = query_params.get("cursor", [None])[0]
        assert request.url.path == "/trade-api/v2/markets"
        assert query_params["limit"] == ["100"]
        requested_cursors.append(cursor)

        if cursor is None:
            return httpx.Response(
                200,
                json={
                    "markets": [
                        {
                            "ticker": "FED-2026-RATE-HIKE",
                            "event_ticker": "FED-2026-RATE",
                            "title": "Rate hike yes",
                            "status": "active",
                            "last_price": 57,
                            "updated_time": "2026-04-08T12:00:00Z",
                        }
                    ],
                    "cursor": "cursor-002",
                },
            )

        assert cursor == "cursor-002"
        return httpx.Response(
            200,
            json={
                "markets": [
                    {
                        "ticker": "CPI-2026-HOT",
                        "event_ticker": "CPI-2026",
                        "title": "Hot CPI print",
                        "status": "active",
                        "last_price": 44,
                        "updated_time": "2026-04-08T12:05:00Z",
                    }
                ],
                "cursor": None,
            },
        )

    transport = httpx.MockTransport(handler)

    with get_sqlite_connection(db_path) as connection:
        bootstrap_schema(connection)
        market_repository = MarketRepository(connection)
        checkpoint_repository = CheckpointRepository(connection)

        async with KalshiHttpClient(
            base_url="https://demo-api.kalshi.co",
            transport=transport,
        ) as client:
            result = await sync_markets(
                client=client,
                market_repository=market_repository,
                checkpoint_repository=checkpoint_repository,
                page_size=100,
            )

        first_market = market_repository.get("FED-2026-RATE-HIKE")
        second_market = market_repository.get("CPI-2026-HOT")
        checkpoint = checkpoint_repository.get("markets_sync_cursor")

    assert requested_cursors == [None, "cursor-002"]
    assert result.pages_processed == 2
    assert result.markets_upserted == 2
    assert result.checkpoint_value == ""
    assert checkpoint is not None
    assert checkpoint.value == ""
    assert first_market is not None
    assert first_market.last_price == 57
    assert second_market is not None
    assert second_market.event_ticker == "CPI-2026"
