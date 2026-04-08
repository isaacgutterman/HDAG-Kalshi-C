from __future__ import annotations

import asyncio

from app.auth import KalshiSigner
from app.client import KalshiHttpClient
from app.config import settings
from app.ingest.portfolio import sync_portfolio
from app.logging_config import initialize_logging
from app.storage.db import bootstrap_schema, get_sqlite_connection
from app.storage.repositories import (
    BalanceSnapshotRepository,
    MarketRepository,
    PositionRepository,
)


async def _run() -> None:
    initialize_logging()
    signer = KalshiSigner(
        api_key_id=settings.api_key_id,
        private_key_path=settings.private_key_path,
    )

    with get_sqlite_connection() as connection:
        bootstrap_schema(connection)
        balance_repository = BalanceSnapshotRepository(connection)
        position_repository = PositionRepository(connection)
        market_repository = MarketRepository(connection)

        async with KalshiHttpClient(
            base_url=settings.base_url,
            signer=signer,
        ) as client:
            result = await sync_portfolio(
                client=client,
                balance_repository=balance_repository,
                position_repository=position_repository,
                market_repository=market_repository,
            )

    print(
        "Synced portfolio "
        f"(balance_snapshots_inserted={result.balance_snapshots_inserted}, "
        f"positions_upserted={result.positions_upserted})"
    )


def main() -> None:
    asyncio.run(_run())


if __name__ == "__main__":
    main()
