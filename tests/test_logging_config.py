import logging

from app.config import Settings
from app import logging_config


def test_initialize_logging_uses_settings_log_level(monkeypatch) -> None:
    monkeypatch.setattr(
        logging_config,
        "settings",
        Settings(
            KALSHI_ENV="demo",
            KALSHI_BASE_URL="https://demo-api.kalshi.co",
            KALSHI_WS_URL="wss://demo-api.kalshi.co/trade-api/ws/v2",
            KALSHI_API_KEY_ID="test-key-id",
            KALSHI_PRIVATE_KEY_PATH="secrets/test-key.pem",
            SQLITE_DB_PATH="data/test.sqlite3",
            WATCH_TICKERS="INX-TEST-ONE,BTC-TEST-TWO",
            LOG_LEVEL="debug",
        ),
    )

    logging_config.initialize_logging()

    root_logger = logging.getLogger()

    assert root_logger.getEffectiveLevel() == logging.DEBUG
    assert root_logger.handlers
    assert root_logger.handlers[0].formatter._fmt == logging_config.LOG_FORMAT
