from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Literal

MarketPhase = Literal["pre_game", "live", "final"]

FINAL_EVENT_STATUSES = frozenset({"final", "settled", "closed", "expired", "resolved"})


@dataclass(frozen=True)
class PhaseTaggingInput:
    trade_ts: str
    event_status: str | None = None
    event_start_time: str | None = None
    event_settlement_time: str | None = None


def derive_market_phase(inputs: PhaseTaggingInput) -> MarketPhase:
    """Derive a conservative market phase from explicit event/trade timing.

    Rules are intentionally simple and deterministic:
    - Return `final` when event status is explicitly final-like.
    - Return `final` when a settlement time exists and the trade is at/after it.
    - Return `pre_game` when a start time exists and the trade is before it.
    - Return `live` when a start time exists and the trade is at/after it.
    - Otherwise default to `pre_game` when timing evidence is incomplete.
    """

    trade_time = _parse_utc_timestamp(inputs.trade_ts)
    normalized_status = _normalize_status(inputs.event_status)

    if normalized_status in FINAL_EVENT_STATUSES:
        return "final"

    settlement_time = _parse_optional_utc_timestamp(inputs.event_settlement_time)
    if settlement_time is not None and trade_time >= settlement_time:
        return "final"

    start_time = _parse_optional_utc_timestamp(inputs.event_start_time)
    if start_time is not None and trade_time < start_time:
        return "pre_game"

    if start_time is not None and trade_time >= start_time:
        return "live"

    return "pre_game"


def _normalize_status(value: str | None) -> str | None:
    if value is None:
        return None

    return value.strip().lower()


def _parse_optional_utc_timestamp(value: str | None) -> datetime | None:
    if value is None:
        return None

    return _parse_utc_timestamp(value)


def _parse_utc_timestamp(value: str) -> datetime:
    normalized_value = value.strip()
    if normalized_value.endswith("Z"):
        normalized_value = normalized_value[:-1] + "+00:00"

    parsed_value = datetime.fromisoformat(normalized_value)
    if parsed_value.tzinfo is None:
        return parsed_value.replace(tzinfo=UTC)

    return parsed_value.astimezone(UTC)
