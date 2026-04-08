from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import UTC, datetime
from urllib.parse import quote

from app.client import KalshiHttpClient
from app.dto import TradeDTO
from app.services.phase_tagging import PhaseTaggingInput, derive_market_phase
from app.storage.repositories import (
    CheckpointRepository,
    EventRepository,
    MarketRepository,
    Trade,
    TradeRepository,
)

logger = logging.getLogger(__name__)

TRADES_PATH_PREFIX = "/trade-api/v2/markets"


@dataclass(frozen=True)
class TradesSyncResult:
    markets_processed: int
    trades_upserted: int


async def sync_trades(
    client: KalshiHttpClient,
    trade_repository: TradeRepository,
    checkpoint_repository: CheckpointRepository,
    market_repository: MarketRepository,
    event_repository: EventRepository,
    market_tickers: list[str],
    page_size: int = 200,
) -> TradesSyncResult:
    trades_upserted = 0

    for market_ticker in market_tickers:
        market = market_repository.get(market_ticker)
        if market is None:
            raise ValueError(f"Market '{market_ticker}' must exist before syncing trades")

        event = event_repository.get(market.event_ticker)
        cursor = _load_trade_cursor(checkpoint_repository, market_ticker)

        while True:
            path = build_trades_path(market_ticker)
            params = _build_trade_params(limit=page_size, cursor=cursor)
            logger.info(
                "Requesting Kalshi trades page",
                extra={"path": path, "market_ticker": market_ticker, "params": params},
            )
            response = await client.get(path=path, params=params, authenticated=False)
            payload = response.json()

            trade_payloads = _extract_trade_payloads(payload)
            trades = [
                _normalize_trade_payload(
                    payload=item,
                    market_ticker=market_ticker,
                    event_status=event.status if event is not None else None,
                    event_start_time=event.start_time if event is not None else None,
                    event_settlement_time=event.settlement_time if event is not None else None,
                )
                for item in trade_payloads
            ]
            upserted_count = trade_repository.upsert_many(trades)
            trades_upserted += upserted_count

            next_cursor = _normalize_cursor(payload.get("cursor"))
            checkpoint_repository.set(_trade_checkpoint_key(market_ticker), next_cursor)

            logger.info(
                "Processed Kalshi trades page",
                extra={
                    "path": path,
                    "market_ticker": market_ticker,
                    "trade_count": upserted_count,
                    "next_cursor": next_cursor or None,
                },
            )

            if not next_cursor:
                break

            cursor = next_cursor

    return TradesSyncResult(
        markets_processed=len(market_tickers),
        trades_upserted=trades_upserted,
    )


def build_trades_path(market_ticker: str) -> str:
    encoded_ticker = quote(market_ticker, safe="")
    return f"{TRADES_PATH_PREFIX}/{encoded_ticker}/trades"


def _build_trade_params(limit: int, cursor: str) -> dict[str, str | int]:
    params: dict[str, str | int] = {"limit": limit}
    if cursor:
        params["cursor"] = cursor

    return params


def _trade_checkpoint_key(market_ticker: str) -> str:
    return f"trades_sync_cursor:{market_ticker}"


def _load_trade_cursor(
    checkpoint_repository: CheckpointRepository,
    market_ticker: str,
) -> str:
    checkpoint = checkpoint_repository.get(_trade_checkpoint_key(market_ticker))
    if checkpoint is None:
        return ""

    return checkpoint.value


def _extract_trade_payloads(payload: object) -> list[dict[str, object]]:
    if not isinstance(payload, dict):
        raise ValueError("Trade response payload must be a JSON object")

    trades = payload.get("trades")
    if not isinstance(trades, list):
        raise ValueError("Trade response payload must include a trades list")

    normalized_trades: list[dict[str, object]] = []
    for item in trades:
        if not isinstance(item, dict):
            raise ValueError("Each trade payload must be a JSON object")
        normalized_trades.append(item)

    return normalized_trades


def _normalize_trade_payload(
    payload: dict[str, object],
    market_ticker: str,
    event_status: str | None,
    event_start_time: str | None,
    event_settlement_time: str | None,
) -> Trade:
    trade_dto = TradeDTO.model_validate(
        {
            **payload,
            "market_ticker": market_ticker,
            "collected_ts": payload.get("collected_ts") or _current_time_iso(),
        }
    )
    if trade_dto.trade_ts is None:
        raise ValueError(f"Trade payload for market '{market_ticker}' is missing trade_ts")

    phase = derive_market_phase(
        PhaseTaggingInput(
            trade_ts=trade_dto.trade_ts,
            event_status=event_status,
            event_start_time=event_start_time,
            event_settlement_time=event_settlement_time,
        )
    )

    return Trade(
        market_ticker=market_ticker,
        trade_id=trade_dto.trade_id,
        side=trade_dto.side,
        price=trade_dto.price,
        count=trade_dto.count,
        trade_ts=trade_dto.trade_ts,
        phase=phase,
        collected_ts=trade_dto.collected_ts or _current_time_iso(),
    )


def _normalize_cursor(value: object) -> str:
    if value is None:
        return ""

    return str(value)


def _current_time_iso() -> str:
    return datetime.now(tz=UTC).replace(microsecond=0).isoformat().replace("+00:00", "Z")
