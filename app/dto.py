from __future__ import annotations

from pydantic import AliasChoices, BaseModel, ConfigDict, Field


class BaseDTO(BaseModel):
    model_config = ConfigDict(extra="ignore", populate_by_name=True)


class EventDTO(BaseDTO):
    event_ticker: str = Field(validation_alias=AliasChoices("event_ticker", "ticker"))
    title: str
    category: str | None = None
    status: str | None = None
    start_time: str | None = Field(
        default=None,
        validation_alias=AliasChoices("start_time", "event_start_time", "start_date"),
    )
    settlement_time: str | None = None
    last_updated_ts: str | None = Field(
        default=None,
        validation_alias=AliasChoices("last_updated_ts", "updated_time"),
    )


class MarketDTO(BaseDTO):
    market_ticker: str = Field(validation_alias=AliasChoices("market_ticker", "ticker"))
    event_ticker: str
    title: str
    status: str | None = None
    close_time: str | None = None
    expiration_time: str | None = None
    strike_type: str | None = None
    yes_sub_title: str | None = None
    no_sub_title: str | None = None
    last_price: int | None = None
    last_updated_ts: str | None = Field(
        default=None,
        validation_alias=AliasChoices("last_updated_ts", "updated_time"),
    )


class TradeDTO(BaseDTO):
    market_ticker: str = Field(validation_alias=AliasChoices("market_ticker", "ticker"))
    trade_id: str = Field(validation_alias=AliasChoices("trade_id", "id"))
    side: str | None = None
    price: int | None = None
    count: int | None = None
    trade_ts: str | None = Field(
        default=None,
        validation_alias=AliasChoices("trade_ts", "ts", "created_time"),
    )
    collected_ts: str | None = None


class OrderbookLevelDTO(BaseDTO):
    price: int
    quantity: int = Field(validation_alias=AliasChoices("quantity", "count"))


class OrderbookSnapshotDTO(BaseDTO):
    market_ticker: str = Field(validation_alias=AliasChoices("market_ticker", "ticker"))
    snapshot_ts: str = Field(validation_alias=AliasChoices("snapshot_ts", "ts"))
    yes_levels: list[OrderbookLevelDTO] = Field(
        default_factory=list,
        validation_alias=AliasChoices("yes_levels", "yes"),
    )
    no_levels: list[OrderbookLevelDTO] = Field(
        default_factory=list,
        validation_alias=AliasChoices("no_levels", "no"),
    )
    collected_ts: str | None = None


class BalanceDTO(BaseDTO):
    balance_cents: int = Field(validation_alias=AliasChoices("balance_cents", "balance"))
    available_cents: int | None = Field(
        default=None,
        validation_alias=AliasChoices("available_cents", "available_balance"),
    )
    reserved_cents: int | None = Field(
        default=None,
        validation_alias=AliasChoices("reserved_cents", "reserved_balance"),
    )
    snapshot_ts: str | None = Field(
        default=None,
        validation_alias=AliasChoices("snapshot_ts", "ts"),
    )


class PositionDTO(BaseDTO):
    market_ticker: str = Field(validation_alias=AliasChoices("market_ticker", "ticker"))
    position_side: str | None = Field(
        default=None,
        validation_alias=AliasChoices("position_side", "side"),
    )
    quantity: int = Field(validation_alias=AliasChoices("quantity", "count"))
    average_price: int | None = None
    snapshot_ts: str | None = Field(
        default=None,
        validation_alias=AliasChoices("snapshot_ts", "ts"),
    )
