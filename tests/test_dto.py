from app.dto import (
    BalanceDTO,
    EventDTO,
    MarketDTO,
    OrderbookLevelDTO,
    OrderbookSnapshotDTO,
    PositionDTO,
    TradeDTO,
)


def test_event_and_market_dto_validate_representative_payloads() -> None:
    event = EventDTO.model_validate(
        {
            "ticker": "FED-2026-RATE",
            "title": "Fed decision",
            "category": "economics",
            "status": "open",
            "updated_time": "2026-04-08T12:00:00Z",
            "extra_field": "ignored",
        }
    )
    market = MarketDTO.model_validate(
        {
            "ticker": "FED-2026-RATE-HIKE",
            "event_ticker": "FED-2026-RATE",
            "title": "Rate hike yes",
            "status": "active",
            "close_time": "2026-04-08T15:00:00Z",
            "last_price": 57,
        }
    )

    assert event.event_ticker == "FED-2026-RATE"
    assert event.last_updated_ts == "2026-04-08T12:00:00Z"
    assert market.market_ticker == "FED-2026-RATE-HIKE"
    assert market.last_price == 57


def test_trade_dto_accepts_common_alias_fields() -> None:
    trade = TradeDTO.model_validate(
        {
            "ticker": "BTC-2026-ABOVE",
            "id": "trade-123",
            "side": "yes",
            "price": 61,
            "count": 3,
            "ts": "2026-04-08T12:01:00Z",
        }
    )

    assert trade.market_ticker == "BTC-2026-ABOVE"
    assert trade.trade_id == "trade-123"
    assert trade.count == 3
    assert trade.trade_ts == "2026-04-08T12:01:00Z"


def test_orderbook_snapshot_dto_validates_nested_levels() -> None:
    snapshot = OrderbookSnapshotDTO.model_validate(
        {
            "ticker": "INX-2026-ABOVE",
            "ts": "2026-04-08T12:02:00Z",
            "yes": [
                {"price": 60, "count": 10},
                {"price": 61, "quantity": 4},
            ],
            "no": [
                {"price": 39, "count": 8},
            ],
        }
    )

    assert snapshot.market_ticker == "INX-2026-ABOVE"
    assert snapshot.snapshot_ts == "2026-04-08T12:02:00Z"
    assert snapshot.yes_levels == [
        OrderbookLevelDTO(price=60, quantity=10),
        OrderbookLevelDTO(price=61, quantity=4),
    ]
    assert snapshot.no_levels == [OrderbookLevelDTO(price=39, quantity=8)]


def test_balance_and_position_dto_allow_optional_fields() -> None:
    balance = BalanceDTO.model_validate({"balance": 125000})
    position = PositionDTO.model_validate(
        {
            "ticker": "INX-2026-ABOVE",
            "count": 7,
            "average_price": 52,
        }
    )

    assert balance.balance_cents == 125000
    assert balance.available_cents is None
    assert position.market_ticker == "INX-2026-ABOVE"
    assert position.quantity == 7
    assert position.position_side is None
