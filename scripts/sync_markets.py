from __future__ import annotations

import asyncio

from app.client import KalshiHttpClient
from app.config import settings
from app.ingest.markets import sync_markets
from app.logging_config import initialize_logging
from app.storage.db import bootstrap_schema, get_sqlite_connection
from app.storage.repositories import CheckpointRepository, MarketRepository


async def _run() -> None:
    initialize_logging()

    with get_sqlite_connection() as connection:
        bootstrap_schema(connection)
        market_repository = MarketRepository(connection)
        checkpoint_repository = CheckpointRepository(connection)

        async with KalshiHttpClient(base_url=settings.base_url) as client:
            result = await sync_markets(
                client=client,
                market_repository=market_repository,
                checkpoint_repository=checkpoint_repository,
            )

    print(
        "Synced markets "
        f"(pages_processed={result.pages_processed}, "
        f"markets_upserted={result.markets_upserted}, "
        f"checkpoint='{result.checkpoint_value}')"
    )


def main() -> None:
    asyncio.run(_run())


if __name__ == "__main__":
    main()
