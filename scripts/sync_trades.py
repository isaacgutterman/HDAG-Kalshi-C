from __future__ import annotations

import asyncio

from app.client import KalshiHttpClient
from app.config import settings
from app.ingest.trades import sync_trades
from app.logging_config import initialize_logging
from app.storage.db import bootstrap_schema, get_sqlite_connection
from app.storage.repositories import (
    CheckpointRepository,
    EventRepository,
    MarketRepository,
    TradeRepository,
)


async def _run() -> None:
    initialize_logging()

    with get_sqlite_connection() as connection:
        bootstrap_schema(connection)
        trade_repository = TradeRepository(connection)
        checkpoint_repository = CheckpointRepository(connection)
        market_repository = MarketRepository(connection)
        event_repository = EventRepository(connection)

        async with KalshiHttpClient(base_url=settings.base_url) as client:
            result = await sync_trades(
                client=client,
                trade_repository=trade_repository,
                checkpoint_repository=checkpoint_repository,
                market_repository=market_repository,
                event_repository=event_repository,
                market_tickers=settings.watch_tickers,
            )

    print(
        "Synced trades "
        f"(markets_processed={result.markets_processed}, "
        f"trades_upserted={result.trades_upserted})"
    )


def main() -> None:
    asyncio.run(_run())


if __name__ == "__main__":
    main()
