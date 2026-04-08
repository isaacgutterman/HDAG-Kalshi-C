from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime

from app.client import KalshiHttpClient
from app.dto import BalanceDTO, PositionDTO
from app.storage.repositories import (
    BalanceSnapshot,
    BalanceSnapshotRepository,
    MarketRepository,
    Position,
    PositionRepository,
)

BALANCE_PATH = "/trade-api/v2/portfolio/balance"
POSITIONS_PATH = "/trade-api/v2/portfolio/positions"


@dataclass(frozen=True)
class PortfolioSyncResult:
    balance_snapshots_inserted: int
    positions_upserted: int


async def sync_portfolio(
    client: KalshiHttpClient,
    balance_repository: BalanceSnapshotRepository,
    position_repository: PositionRepository,
    market_repository: MarketRepository,
) -> PortfolioSyncResult:
    balance_payload = await _get_json(client=client, path=BALANCE_PATH)
    balance_snapshot = _normalize_balance_payload(balance_payload)
    balance_repository.insert(balance_snapshot)

    positions_payload = await _get_json(client=client, path=POSITIONS_PATH)
    positions = _normalize_positions_payload(positions_payload)

    for position in positions:
        if market_repository.get(position.market_ticker) is None:
            raise ValueError(
                f"Market '{position.market_ticker}' must exist before syncing positions"
            )

    positions_upserted = position_repository.upsert_many(positions)

    return PortfolioSyncResult(
        balance_snapshots_inserted=1,
        positions_upserted=positions_upserted,
    )


async def _get_json(client: KalshiHttpClient, path: str) -> object:
    response = await client.get(path=path, authenticated=True)
    return response.json()


def _normalize_balance_payload(payload: object) -> BalanceSnapshot:
    snapshot_payload = _extract_balance_payload(payload)
    balance_dto = BalanceDTO.model_validate(
        {
            **snapshot_payload,
            "snapshot_ts": snapshot_payload.get("snapshot_ts") or _current_time_iso(),
        }
    )

    return BalanceSnapshot(
        balance_cents=balance_dto.balance_cents,
        available_cents=balance_dto.available_cents,
        reserved_cents=balance_dto.reserved_cents,
        snapshot_ts=balance_dto.snapshot_ts or _current_time_iso(),
    )


def _normalize_positions_payload(payload: object) -> list[Position]:
    positions_payload = _extract_positions_payload(payload)
    snapshot_ts = _extract_positions_snapshot_ts(payload)

    positions: list[Position] = []
    for item in positions_payload:
        if not isinstance(item, dict):
            raise ValueError("Each position payload must be a JSON object")

        position_dto = PositionDTO.model_validate(
            {
                **item,
                "snapshot_ts": item.get("snapshot_ts") or snapshot_ts,
            }
        )
        positions.append(
            Position(
                market_ticker=position_dto.market_ticker,
                position_side=position_dto.position_side,
                quantity=position_dto.quantity,
                average_price=position_dto.average_price,
                snapshot_ts=position_dto.snapshot_ts or snapshot_ts,
            )
        )

    return positions


def _extract_balance_payload(payload: object) -> dict[str, object]:
    if not isinstance(payload, dict):
        raise ValueError("Balance response payload must be a JSON object")

    nested_balance = payload.get("balance")
    if isinstance(nested_balance, dict):
        return nested_balance

    return payload


def _extract_positions_payload(payload: object) -> list[object]:
    if not isinstance(payload, dict):
        raise ValueError("Positions response payload must be a JSON object")

    positions = payload.get("market_positions")
    if positions is None:
        positions = payload.get("positions")

    if positions is None:
        return []

    if not isinstance(positions, list):
        raise ValueError("Positions response payload must include a list of positions")

    return positions


def _extract_positions_snapshot_ts(payload: object) -> str:
    if not isinstance(payload, dict):
        return _current_time_iso()

    raw_snapshot_ts = payload.get("snapshot_ts") or payload.get("ts")
    if raw_snapshot_ts is None:
        return _current_time_iso()

    return str(raw_snapshot_ts)


def _current_time_iso() -> str:
    return datetime.now(tz=UTC).replace(microsecond=0).isoformat().replace("+00:00", "Z")
