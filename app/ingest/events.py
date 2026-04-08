from __future__ import annotations

import logging
from dataclasses import dataclass
from urllib.parse import quote

from app.client import KalshiHttpClient
from app.dto import EventDTO
from app.storage.repositories import Event, EventRepository

logger = logging.getLogger(__name__)

EVENTS_PATH_PREFIX = "/trade-api/v2/events"


@dataclass(frozen=True)
class EventSyncResult:
    event_tickers_requested: int
    events_upserted: int


async def sync_events(
    client: KalshiHttpClient,
    event_repository: EventRepository,
    event_tickers: list[str],
) -> EventSyncResult:
    events_upserted = 0

    for event_ticker in event_tickers:
        path = build_event_path(event_ticker)
        logger.info(
            "Requesting Kalshi event",
            extra={"path": path, "event_ticker": event_ticker},
        )
        response = await client.get(path=path, authenticated=False)
        payload = _extract_event_payload(response.json())
        event = _event_from_dto(EventDTO.model_validate(payload))
        event_repository.upsert(event)
        events_upserted += 1

        logger.info(
            "Processed Kalshi event",
            extra={
                "path": path,
                "event_ticker": event.event_ticker,
                "status": event.status,
                "start_time": event.start_time,
            },
        )

    return EventSyncResult(
        event_tickers_requested=len(event_tickers),
        events_upserted=events_upserted,
    )


def build_event_path(event_ticker: str) -> str:
    encoded_ticker = quote(event_ticker, safe="")
    return f"{EVENTS_PATH_PREFIX}/{encoded_ticker}"


def _extract_event_payload(payload: object) -> dict[str, object]:
    if not isinstance(payload, dict):
        raise ValueError("Event response payload must be a JSON object")

    nested_event = payload.get("event")
    if isinstance(nested_event, dict):
        return nested_event

    return payload


def _event_from_dto(event: EventDTO) -> Event:
    return Event(
        event_ticker=event.event_ticker,
        title=event.title,
        category=event.category,
        status=event.status,
        start_time=event.start_time,
        settlement_time=event.settlement_time,
        last_updated_ts=event.last_updated_ts or "",
    )
