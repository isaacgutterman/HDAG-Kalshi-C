from pathlib import Path

import httpx
import pytest

from app.client import KalshiHttpClient
from app.ingest.portfolio import sync_portfolio
from app.storage.db import bootstrap_schema, get_sqlite_connection
from app.storage.repositories import (
    BalanceSnapshot,
    BalanceSnapshotRepository,
    Event,
    EventRepository,
    Market,
    MarketRepository,
    Position,
    PositionRepository,
)


class DummySigner:
    def build_auth_headers(self, method: str, url: str) -> dict[str, str]:
        return {
            "KALSHI-ACCESS-KEY": "test-key",
            "KALSHI-ACCESS-TIMESTAMP": "1703123456789",
            "KALSHI-ACCESS-SIGNATURE": f"{method}:{url}",
        }


@pytest.fixture
def anyio_backend() -> str:
    return "asyncio"


def test_balance_snapshot_insert_and_position_upsert(tmp_path: Path) -> None:
    db_path = tmp_path / "portfolio.sqlite3"

    with get_sqlite_connection(db_path) as connection:
        bootstrap_schema(connection)
        event_repository = EventRepository(connection)
        market_repository = MarketRepository(connection)
        balance_repository = BalanceSnapshotRepository(connection)
        position_repository = PositionRepository(connection)

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

        saved_balance = balance_repository.insert(
            BalanceSnapshot(
                balance_cents=125000,
                available_cents=120000,
                reserved_cents=5000,
                snapshot_ts="2026-04-08T12:00:00Z",
            )
        )
        position_repository.upsert(
            Position(
                market_ticker="FED-2026-RATE-HIKE",
                position_side="yes",
                quantity=7,
                average_price=52,
                snapshot_ts="2026-04-08T12:00:00Z",
            )
        )
        updated_position = position_repository.upsert(
            Position(
                market_ticker="FED-2026-RATE-HIKE",
                position_side="yes",
                quantity=9,
                average_price=53,
                snapshot_ts="2026-04-08T12:05:00Z",
            )
        )
        latest_balance = balance_repository.get_latest()
        positions = position_repository.list_all()
        row_count = connection.execute("SELECT COUNT(*) AS count FROM positions").fetchone()

    assert latest_balance == saved_balance
    assert updated_position.quantity == 9
    assert updated_position.average_price == 53
    assert len(positions) == 1
    assert row_count is not None
    assert row_count["count"] == 1


@pytest.mark.anyio
async def test_sync_portfolio_uses_authenticated_requests_and_persists_results(
    tmp_path: Path,
) -> None:
    db_path = tmp_path / "portfolio.sqlite3"
    requested_paths: list[str] = []

    async def handler(request: httpx.Request) -> httpx.Response:
        requested_paths.append(request.url.path)
        assert request.headers["KALSHI-ACCESS-KEY"] == "test-key"
        assert request.headers["KALSHI-ACCESS-TIMESTAMP"] == "1703123456789"
        assert "KALSHI-ACCESS-SIGNATURE" in request.headers

        if request.url.path == "/trade-api/v2/portfolio/balance":
            return httpx.Response(
                200,
                json={
                    "balance": {
                        "balance": 125000,
                        "available_balance": 120000,
                        "reserved_balance": 5000,
                        "snapshot_ts": "2026-04-08T12:00:00Z",
                    }
                },
            )

        assert request.url.path == "/trade-api/v2/portfolio/positions"
        return httpx.Response(
            200,
            json={
                "positions": [
                    {
                        "ticker": "FED-2026-RATE-HIKE",
                        "side": "yes",
                        "count": 7,
                        "average_price": 52,
                    }
                ],
                "snapshot_ts": "2026-04-08T12:00:00Z",
            },
        )

    transport = httpx.MockTransport(handler)

    with get_sqlite_connection(db_path) as connection:
        bootstrap_schema(connection)
        event_repository = EventRepository(connection)
        market_repository = MarketRepository(connection)
        balance_repository = BalanceSnapshotRepository(connection)
        position_repository = PositionRepository(connection)

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
            signer=DummySigner(),
            transport=transport,
        ) as client:
            result = await sync_portfolio(
                client=client,
                balance_repository=balance_repository,
                position_repository=position_repository,
                market_repository=market_repository,
            )

        latest_balance = balance_repository.get_latest()
        saved_position = position_repository.get("FED-2026-RATE-HIKE")

    assert requested_paths == [
        "/trade-api/v2/portfolio/balance",
        "/trade-api/v2/portfolio/positions",
    ]
    assert result.balance_snapshots_inserted == 1
    assert result.positions_upserted == 1
    assert latest_balance is not None
    assert latest_balance.balance_cents == 125000
    assert latest_balance.available_cents == 120000
    assert latest_balance.reserved_cents == 5000
    assert saved_position is not None
    assert saved_position.quantity == 7
    assert saved_position.average_price == 52
    assert saved_position.snapshot_ts == "2026-04-08T12:00:00Z"
