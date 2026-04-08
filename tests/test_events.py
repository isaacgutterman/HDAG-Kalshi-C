from pathlib import Path

import httpx
import pytest

from app.client import KalshiHttpClient
from app.ingest.events import build_event_path, sync_events
from app.storage.db import bootstrap_schema, get_sqlite_connection
from app.storage.repositories import Event, EventRepository


@pytest.fixture
def anyio_backend() -> str:
    return "asyncio"


def test_event_repository_upsert_inserts_and_updates_event(tmp_path: Path) -> None:
    db_path = tmp_path / "events.sqlite3"
    first_event = Event(
        event_ticker="FED-2026-RATE",
        title="Fed decision",
        category="economics",
        status="open",
        start_time="2026-04-08T13:00:00Z",
        settlement_time="2026-04-08T14:00:00Z",
        last_updated_ts="2026-04-08T12:00:00Z",
    )
    updated_event = Event(
        event_ticker="FED-2026-RATE",
        title="Fed decision updated",
        category="macro",
        status="closed",
        start_time="2026-04-08T13:30:00Z",
        settlement_time="2026-04-08T14:05:00Z",
        last_updated_ts="2026-04-08T12:10:00Z",
    )

    with get_sqlite_connection(db_path) as connection:
        bootstrap_schema(connection)
        repository = EventRepository(connection)

        saved_event = repository.upsert(first_event)
        reloaded_event = repository.upsert(updated_event)

    assert saved_event == first_event
    assert reloaded_event == updated_event


def test_build_event_path_url_encodes_event_ticker() -> None:
    assert build_event_path("FED 2026/RATE") == "/trade-api/v2/events/FED%202026%2FRATE"


@pytest.mark.anyio
async def test_sync_events_fetches_explicit_event_tickers_and_upserts(tmp_path: Path) -> None:
    db_path = tmp_path / "events.sqlite3"
    requested_paths: list[str] = []

    async def handler(request: httpx.Request) -> httpx.Response:
        requested_paths.append(request.url.path)

        if request.url.path.endswith("/FED-2026-RATE"):
            return httpx.Response(
                200,
                json={
                    "event": {
                        "ticker": "FED-2026-RATE",
                        "title": "Fed decision",
                        "category": "economics",
                        "status": "open",
                        "event_start_time": "2026-04-08T13:00:00Z",
                        "settlement_time": "2026-04-08T14:00:00Z",
                        "updated_time": "2026-04-08T12:00:00Z",
                    }
                },
            )

        return httpx.Response(
            200,
            json={
                "event": {
                    "ticker": "CPI-2026",
                    "title": "CPI release",
                    "category": "economics",
                    "status": "settled",
                    "start_time": "2026-04-09T12:30:00Z",
                    "settlement_time": "2026-04-09T12:31:00Z",
                    "updated_time": "2026-04-09T12:35:00Z",
                }
            },
        )

    transport = httpx.MockTransport(handler)

    with get_sqlite_connection(db_path) as connection:
        bootstrap_schema(connection)
        repository = EventRepository(connection)

        async with KalshiHttpClient(
            base_url="https://demo-api.kalshi.co",
            transport=transport,
        ) as client:
            result = await sync_events(
                client=client,
                event_repository=repository,
                event_tickers=["FED-2026-RATE", "CPI-2026"],
            )

        fed_event = repository.get("FED-2026-RATE")
        cpi_event = repository.get("CPI-2026")

    assert requested_paths == [
        "/trade-api/v2/events/FED-2026-RATE",
        "/trade-api/v2/events/CPI-2026",
    ]
    assert result.event_tickers_requested == 2
    assert result.events_upserted == 2
    assert fed_event is not None
    assert fed_event.start_time == "2026-04-08T13:00:00Z"
    assert fed_event.status == "open"
    assert cpi_event is not None
    assert cpi_event.start_time == "2026-04-09T12:30:00Z"
    assert cpi_event.status == "settled"
