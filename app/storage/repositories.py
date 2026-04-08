from __future__ import annotations

import sqlite3
import time
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Sequence


@dataclass(frozen=True)
class Checkpoint:
    job_name: str
    value: str
    updated_ts_ms: int


@dataclass(frozen=True)
class Market:
    market_ticker: str
    event_ticker: str
    title: str
    status: str | None
    close_time: str | None
    expiration_time: str | None
    strike_type: str | None
    yes_sub_title: str | None
    no_sub_title: str | None
    last_price: int | None
    last_updated_ts: str


@dataclass(frozen=True)
class Event:
    event_ticker: str
    title: str
    category: str | None
    status: str | None
    start_time: str | None
    settlement_time: str | None
    last_updated_ts: str


@dataclass(frozen=True)
class Trade:
    market_ticker: str
    trade_id: str
    side: str | None
    price: int | None
    count: int | None
    trade_ts: str
    phase: str
    collected_ts: str


@dataclass(frozen=True)
class OrderbookLevel:
    market_ticker: str
    snapshot_ts_ms: int
    side: str
    price: int
    quantity: int
    collected_ts_ms: int


@dataclass(frozen=True)
class BalanceSnapshot:
    balance_cents: int
    available_cents: int | None
    reserved_cents: int | None
    snapshot_ts: str


@dataclass(frozen=True)
class Position:
    market_ticker: str
    position_side: str | None
    quantity: int
    average_price: int | None
    snapshot_ts: str


class CheckpointRepository:
    def __init__(self, connection: sqlite3.Connection) -> None:
        self._connection = connection

    def get(self, job_name: str) -> Checkpoint | None:
        row = self._connection.execute(
            """
            SELECT checkpoint_key, checkpoint_value, updated_ts
            FROM checkpoints
            WHERE checkpoint_key = ?
            """,
            (job_name,),
        ).fetchone()

        if row is None:
            return None

        return Checkpoint(
            job_name=str(row["checkpoint_key"]),
            value=str(row["checkpoint_value"]),
            updated_ts_ms=int(row["updated_ts"]),
        )

    def set(self, job_name: str, value: str) -> Checkpoint:
        updated_ts_ms = _current_time_ms()

        self._connection.execute(
            """
            INSERT INTO checkpoints (checkpoint_key, checkpoint_value, updated_ts)
            VALUES (?, ?, ?)
            ON CONFLICT(checkpoint_key) DO UPDATE SET
                checkpoint_value = excluded.checkpoint_value,
                updated_ts = excluded.updated_ts
            """,
            (job_name, value, updated_ts_ms),
        )
        self._connection.commit()

        checkpoint = self.get(job_name)
        if checkpoint is None:
            raise RuntimeError(f"Failed to persist checkpoint for job '{job_name}'")

        return checkpoint


class EventRepository:
    def __init__(self, connection: sqlite3.Connection) -> None:
        self._connection = connection

    def get(self, event_ticker: str) -> Event | None:
        row = self._connection.execute(
            """
            SELECT
                event_ticker,
                title,
                category,
                status,
                start_time,
                settlement_time,
                last_updated_ts
            FROM events
            WHERE event_ticker = ?
            """,
            (event_ticker,),
        ).fetchone()

        if row is None:
            return None

        return Event(
            event_ticker=str(row["event_ticker"]),
            title=str(row["title"]),
            category=_optional_text(row["category"]),
            status=_optional_text(row["status"]),
            start_time=_optional_text(row["start_time"]),
            settlement_time=_optional_text(row["settlement_time"]),
            last_updated_ts=str(row["last_updated_ts"]),
        )

    def upsert(self, event: Event) -> Event:
        self.upsert_many([event])

        saved_event = self.get(event.event_ticker)
        if saved_event is None:
            raise RuntimeError(f"Failed to persist event '{event.event_ticker}'")

        return saved_event

    def upsert_many(self, events: Sequence[Event]) -> int:
        if not events:
            return 0

        self._connection.executemany(
            """
            INSERT INTO events (
                event_ticker,
                title,
                category,
                status,
                start_time,
                settlement_time,
                last_updated_ts
            )
            VALUES (?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(event_ticker) DO UPDATE SET
                title = excluded.title,
                category = excluded.category,
                status = excluded.status,
                start_time = excluded.start_time,
                settlement_time = excluded.settlement_time,
                last_updated_ts = excluded.last_updated_ts
            """,
            [
                (
                    event.event_ticker,
                    event.title,
                    event.category,
                    event.status,
                    event.start_time,
                    event.settlement_time,
                    event.last_updated_ts,
                )
                for event in events
            ],
        )
        self._connection.commit()

        return len(events)


class TradeRepository:
    def __init__(self, connection: sqlite3.Connection) -> None:
        self._connection = connection

    def get(self, market_ticker: str, trade_id: str) -> Trade | None:
        row = self._connection.execute(
            """
            SELECT
                market_ticker,
                trade_id,
                side,
                price,
                count,
                trade_ts,
                phase,
                collected_ts
            FROM trades
            WHERE market_ticker = ? AND trade_id = ?
            """,
            (market_ticker, trade_id),
        ).fetchone()

        if row is None:
            return None

        return Trade(
            market_ticker=str(row["market_ticker"]),
            trade_id=str(row["trade_id"]),
            side=_optional_text(row["side"]),
            price=_optional_int(row["price"]),
            count=_optional_int(row["count"]),
            trade_ts=str(row["trade_ts"]),
            phase=str(row["phase"]),
            collected_ts=str(row["collected_ts"]),
        )

    def upsert(self, trade: Trade) -> Trade:
        self.upsert_many([trade])

        saved_trade = self.get(trade.market_ticker, trade.trade_id)
        if saved_trade is None:
            raise RuntimeError(
                f"Failed to persist trade '{trade.trade_id}' for market '{trade.market_ticker}'"
            )

        return saved_trade

    def upsert_many(self, trades: Sequence[Trade]) -> int:
        if not trades:
            return 0

        self._connection.executemany(
            """
            INSERT INTO trades (
                market_ticker,
                trade_id,
                side,
                price,
                count,
                trade_ts,
                phase,
                collected_ts
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(market_ticker, trade_id) DO UPDATE SET
                side = excluded.side,
                price = excluded.price,
                count = excluded.count,
                trade_ts = excluded.trade_ts,
                phase = excluded.phase,
                collected_ts = excluded.collected_ts
            """,
            [
                (
                    trade.market_ticker,
                    trade.trade_id,
                    trade.side,
                    trade.price,
                    trade.count,
                    trade.trade_ts,
                    trade.phase,
                    trade.collected_ts,
                )
                for trade in trades
            ],
        )
        self._connection.commit()

        return len(trades)


class OrderbookSnapshotRepository:
    def __init__(self, connection: sqlite3.Connection) -> None:
        self._connection = connection

    def insert_snapshot(self, levels: Sequence[OrderbookLevel]) -> int:
        return self.insert_many(levels)

    def insert_many(self, levels: Sequence[OrderbookLevel]) -> int:
        if not levels:
            return 0

        self._connection.executemany(
            """
            INSERT INTO orderbook_snapshots (
                market_ticker,
                snapshot_ts_ms,
                side,
                price,
                quantity,
                collected_ts_ms
            )
            VALUES (?, ?, ?, ?, ?, ?)
            """,
            [
                (
                    level.market_ticker,
                    level.snapshot_ts_ms,
                    level.side,
                    level.price,
                    level.quantity,
                    level.collected_ts_ms,
                )
                for level in levels
            ],
        )
        self._connection.commit()

        return len(levels)

    def list_for_snapshot(
        self,
        market_ticker: str,
        snapshot_ts_ms: int,
    ) -> list[OrderbookLevel]:
        rows = self._connection.execute(
            """
            SELECT
                market_ticker,
                snapshot_ts_ms,
                side,
                price,
                quantity,
                collected_ts_ms
            FROM orderbook_snapshots
            WHERE market_ticker = ? AND snapshot_ts_ms = ?
            ORDER BY side, price
            """,
            (market_ticker, snapshot_ts_ms),
        ).fetchall()

        return [
            OrderbookLevel(
                market_ticker=str(row["market_ticker"]),
                snapshot_ts_ms=int(row["snapshot_ts_ms"]),
                side=str(row["side"]),
                price=int(row["price"]),
                quantity=int(row["quantity"]),
                collected_ts_ms=int(row["collected_ts_ms"]),
            )
            for row in rows
        ]


class BalanceSnapshotRepository:
    def __init__(self, connection: sqlite3.Connection) -> None:
        self._connection = connection

    def insert(self, snapshot: BalanceSnapshot) -> BalanceSnapshot:
        self._connection.execute(
            """
            INSERT INTO balance_snapshots (
                balance_cents,
                available_cents,
                reserved_cents,
                snapshot_ts
            )
            VALUES (?, ?, ?, ?)
            """,
            (
                snapshot.balance_cents,
                snapshot.available_cents,
                snapshot.reserved_cents,
                snapshot.snapshot_ts,
            ),
        )
        self._connection.commit()

        return snapshot

    def get_latest(self) -> BalanceSnapshot | None:
        row = self._connection.execute(
            """
            SELECT
                balance_cents,
                available_cents,
                reserved_cents,
                snapshot_ts
            FROM balance_snapshots
            ORDER BY id DESC
            LIMIT 1
            """
        ).fetchone()

        if row is None:
            return None

        return BalanceSnapshot(
            balance_cents=int(row["balance_cents"]),
            available_cents=_optional_int(row["available_cents"]),
            reserved_cents=_optional_int(row["reserved_cents"]),
            snapshot_ts=str(row["snapshot_ts"]),
        )


class PositionRepository:
    def __init__(self, connection: sqlite3.Connection) -> None:
        self._connection = connection

    def get(self, market_ticker: str) -> Position | None:
        row = self._connection.execute(
            """
            SELECT
                market_ticker,
                position_side,
                quantity,
                average_price,
                snapshot_ts
            FROM positions
            WHERE market_ticker = ?
            """,
            (market_ticker,),
        ).fetchone()

        if row is None:
            return None

        return Position(
            market_ticker=str(row["market_ticker"]),
            position_side=_optional_text(row["position_side"]),
            quantity=int(row["quantity"]),
            average_price=_optional_int(row["average_price"]),
            snapshot_ts=str(row["snapshot_ts"]),
        )

    def upsert(self, position: Position) -> Position:
        self.upsert_many([position])

        saved_position = self.get(position.market_ticker)
        if saved_position is None:
            raise RuntimeError(
                f"Failed to persist position for market '{position.market_ticker}'"
            )

        return saved_position

    def upsert_many(self, positions: Sequence[Position]) -> int:
        if not positions:
            return 0

        self._connection.executemany(
            """
            INSERT INTO positions (
                market_ticker,
                position_side,
                quantity,
                average_price,
                snapshot_ts
            )
            VALUES (?, ?, ?, ?, ?)
            ON CONFLICT(market_ticker) DO UPDATE SET
                position_side = excluded.position_side,
                quantity = excluded.quantity,
                average_price = excluded.average_price,
                snapshot_ts = excluded.snapshot_ts
            """,
            [
                (
                    position.market_ticker,
                    position.position_side,
                    position.quantity,
                    position.average_price,
                    position.snapshot_ts,
                )
                for position in positions
            ],
        )
        self._connection.commit()

        return len(positions)

    def list_all(self) -> list[Position]:
        rows = self._connection.execute(
            """
            SELECT
                market_ticker,
                position_side,
                quantity,
                average_price,
                snapshot_ts
            FROM positions
            ORDER BY market_ticker
            """
        ).fetchall()

        return [
            Position(
                market_ticker=str(row["market_ticker"]),
                position_side=_optional_text(row["position_side"]),
                quantity=int(row["quantity"]),
                average_price=_optional_int(row["average_price"]),
                snapshot_ts=str(row["snapshot_ts"]),
            )
            for row in rows
        ]


class MarketRepository:
    def __init__(self, connection: sqlite3.Connection) -> None:
        self._connection = connection

    def get(self, market_ticker: str) -> Market | None:
        row = self._connection.execute(
            """
            SELECT
                market_ticker,
                event_ticker,
                title,
                status,
                close_time,
                expiration_time,
                strike_type,
                yes_sub_title,
                no_sub_title,
                last_price,
                last_updated_ts
            FROM markets
            WHERE market_ticker = ?
            """,
            (market_ticker,),
        ).fetchone()

        if row is None:
            return None

        return Market(
            market_ticker=str(row["market_ticker"]),
            event_ticker=str(row["event_ticker"]),
            title=str(row["title"]),
            status=_optional_text(row["status"]),
            close_time=_optional_text(row["close_time"]),
            expiration_time=_optional_text(row["expiration_time"]),
            strike_type=_optional_text(row["strike_type"]),
            yes_sub_title=_optional_text(row["yes_sub_title"]),
            no_sub_title=_optional_text(row["no_sub_title"]),
            last_price=_optional_int(row["last_price"]),
            last_updated_ts=str(row["last_updated_ts"]),
        )

    def upsert(self, market: Market) -> Market:
        self.upsert_many([market])

        saved_market = self.get(market.market_ticker)
        if saved_market is None:
            raise RuntimeError(f"Failed to persist market '{market.market_ticker}'")

        return saved_market

    def upsert_many(self, markets: Sequence[Market]) -> int:
        if not markets:
            return 0

        self._ensure_events_exist(markets)
        self._connection.executemany(
            """
            INSERT INTO markets (
                market_ticker,
                event_ticker,
                title,
                status,
                close_time,
                expiration_time,
                strike_type,
                yes_sub_title,
                no_sub_title,
                last_price,
                last_updated_ts
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(market_ticker) DO UPDATE SET
                event_ticker = excluded.event_ticker,
                title = excluded.title,
                status = excluded.status,
                close_time = excluded.close_time,
                expiration_time = excluded.expiration_time,
                strike_type = excluded.strike_type,
                yes_sub_title = excluded.yes_sub_title,
                no_sub_title = excluded.no_sub_title,
                last_price = excluded.last_price,
                last_updated_ts = excluded.last_updated_ts
            """,
            [
                (
                    market.market_ticker,
                    market.event_ticker,
                    market.title,
                    market.status,
                    market.close_time,
                    market.expiration_time,
                    market.strike_type,
                    market.yes_sub_title,
                    market.no_sub_title,
                    market.last_price,
                    market.last_updated_ts,
                )
                for market in markets
            ],
        )
        self._connection.commit()

        return len(markets)

    def _ensure_events_exist(self, markets: Sequence[Market]) -> None:
        placeholder_updated_ts = _current_time_iso()

        self._connection.executemany(
            """
            INSERT INTO events (event_ticker, title, last_updated_ts)
            VALUES (?, ?, ?)
            ON CONFLICT(event_ticker) DO NOTHING
            """,
            # Market sync lands before event sync, so we create minimal event shells
            # to satisfy the existing foreign key constraint.
            [
                (market.event_ticker, market.event_ticker, placeholder_updated_ts)
                for market in markets
            ],
        )


def _current_time_ms() -> int:
    return time.time_ns() // 1_000_000


def _current_time_iso() -> str:
    return datetime.now(tz=UTC).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def _optional_text(value: object) -> str | None:
    if value is None:
        return None

    return str(value)


def _optional_int(value: object) -> int | None:
    if value is None:
        return None

    return int(value)
