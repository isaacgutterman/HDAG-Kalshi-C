from app.services.phase_tagging import PhaseTaggingInput, derive_market_phase


def test_derive_market_phase_returns_pre_game_before_event_start() -> None:
    phase = derive_market_phase(
        PhaseTaggingInput(
            trade_ts="2026-04-08T12:59:59Z",
            event_status="open",
            event_start_time="2026-04-08T13:00:00Z",
            event_settlement_time="2026-04-08T15:00:00Z",
        )
    )

    assert phase == "pre_game"


def test_derive_market_phase_returns_live_at_or_after_event_start() -> None:
    phase = derive_market_phase(
        PhaseTaggingInput(
            trade_ts="2026-04-08T13:00:00Z",
            event_status="open",
            event_start_time="2026-04-08T13:00:00Z",
            event_settlement_time="2026-04-08T15:00:00Z",
        )
    )

    assert phase == "live"


def test_derive_market_phase_returns_final_for_final_like_event_status() -> None:
    phase = derive_market_phase(
        PhaseTaggingInput(
            trade_ts="2026-04-08T13:10:00Z",
            event_status="settled",
            event_start_time="2026-04-08T13:00:00Z",
            event_settlement_time="2026-04-08T15:00:00Z",
        )
    )

    assert phase == "final"


def test_derive_market_phase_returns_final_at_or_after_settlement_time() -> None:
    phase = derive_market_phase(
        PhaseTaggingInput(
            trade_ts="2026-04-08T15:00:00Z",
            event_status="open",
            event_start_time="2026-04-08T13:00:00Z",
            event_settlement_time="2026-04-08T15:00:00Z",
        )
    )

    assert phase == "final"


def test_derive_market_phase_defaults_to_pre_game_when_start_time_is_missing() -> None:
    phase = derive_market_phase(
        PhaseTaggingInput(
            trade_ts="2026-04-08T13:10:00Z",
            event_status="open",
            event_start_time=None,
            event_settlement_time=None,
        )
    )

    assert phase == "pre_game"
