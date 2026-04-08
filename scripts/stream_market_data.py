from __future__ import annotations

import asyncio

from app.auth import KalshiSigner
from app.config import settings
from app.ingest.websocket_consumer import stream_market_data
from app.logging_config import initialize_logging
from app.storage.db import bootstrap_schema, get_sqlite_connection
from app.storage.repositories import (
    EventRepository,
    MarketRepository,
    OrderbookSnapshotRepository,
    TradeRepository,
)


async def _run() -> None:
    initialize_logging()
    ws_headers: dict[str, str] | None = None
    if settings.api_key_id and settings.private_key_path.exists():
        signer = KalshiSigner(
            api_key_id=settings.api_key_id,
            private_key_path=settings.private_key_path,
        )
        ws_headers = signer.build_auth_headers(method="GET", url=settings.ws_url)

    with get_sqlite_connection() as connection:
        bootstrap_schema(connection)
        trade_repository = TradeRepository(connection)
        orderbook_repository = OrderbookSnapshotRepository(connection)
        market_repository = MarketRepository(connection)
        event_repository = EventRepository(connection)

        await stream_market_data(
            ws_url=settings.ws_url,
            market_tickers=settings.watch_tickers,
            trade_repository=trade_repository,
            orderbook_repository=orderbook_repository,
            market_repository=market_repository,
            event_repository=event_repository,
            ws_headers=ws_headers,
        )


def main() -> None:
    asyncio.run(_run())


if __name__ == "__main__":
    main()
