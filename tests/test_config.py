from pathlib import Path

from app.config import load_settings

def test_load_settings_from_env_file(tmp_path: Path, monkeypatch) -> None:
    env_file = tmp_path / ".env"
    env_file.write_text(
        "\n".join(
            [
                "KALSHI_ENV=demo",
                "KALSHI_BASE_URL=https://demo-api.kalshi.co",
                "KALSHI_WS_URL=wss://demo-api.kalshi.co/trade-api/ws/v2",
                "KALSHI_API_KEY_ID=test-key-id",
                "KALSHI_PRIVATE_KEY_PATH=secrets/test-key.pem",
                "SQLITE_DB_PATH=data/test.sqlite3",
                "WATCH_TICKERS=INX-TEST-ONE,BTC-TEST-TWO",
                "LOG_LEVEL=DEBUG",
            ]
        ),
        encoding="utf-8",
    )

    for key in [
        "KALSHI_ENV",
        "KALSHI_BASE_URL",
        "KALSHI_WS_URL",
        "KALSHI_API_KEY_ID",
        "KALSHI_PRIVATE_KEY_PATH",
        "SQLITE_DB_PATH",
        "WATCH_TICKERS",
        "LOG_LEVEL",
    ]:
        monkeypatch.delenv(key, raising=False)

    loaded = load_settings(env_file=env_file)

    assert loaded.env == "demo"
    assert loaded.base_url == "https://demo-api.kalshi.co"
    assert loaded.ws_url == "wss://demo-api.kalshi.co/trade-api/ws/v2"
    assert loaded.api_key_id == "test-key-id"
    assert loaded.private_key_path == Path("secrets/test-key.pem")
    assert loaded.sqlite_db_path == Path("data/test.sqlite3")
    assert loaded.watch_tickers == ["INX-TEST-ONE", "BTC-TEST-TWO"]
    assert loaded.log_level == "DEBUG"
