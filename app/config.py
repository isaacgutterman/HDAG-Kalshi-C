from __future__ import annotations

import os
from pathlib import Path

from dotenv import load_dotenv
from pydantic import BaseModel, Field, field_validator


class Settings(BaseModel):
    env: str = Field(default="demo", alias="KALSHI_ENV")
    base_url: str = Field(default="https://demo-api.kalshi.co", alias="KALSHI_BASE_URL")
    ws_url: str = Field(
        default="wss://demo-api.kalshi.co/trade-api/ws/v2",
        alias="KALSHI_WS_URL",
    )
    api_key_id: str = Field(default="", alias="KALSHI_API_KEY_ID")
    private_key_path: Path = Field(
        default=Path("secrets/kalshi-demo-key.pem"),
        alias="KALSHI_PRIVATE_KEY_PATH",
    )
    sqlite_db_path: Path = Field(
        default=Path("data/kalshi_markets.sqlite3"),
        alias="SQLITE_DB_PATH",
    )
    watch_tickers: list[str] = Field(default_factory=list, alias="WATCH_TICKERS")
    log_level: str = Field(default="INFO", alias="LOG_LEVEL")

    @field_validator("watch_tickers", mode="before")
    @classmethod
    def parse_watch_tickers(cls, value: str | list[str]) -> list[str]:
        if isinstance(value, list):
            return value

        return [ticker.strip() for ticker in value.split(",") if ticker.strip()]


def load_settings(env_file: str | Path | None = None) -> Settings:
    load_dotenv(dotenv_path=env_file, override=False)

    return Settings.model_validate(os.environ)


settings = load_settings()
