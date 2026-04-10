from __future__ import annotations

import asyncio
import argparse
import time

from app.client import KalshiHttpClient
from app.config import settings
from app.ingest.markets import sync_markets
from app.logging_config import initialize_logging
from app.storage.db import bootstrap_schema, get_sqlite_connection
from app.storage.repositories import CheckpointRepository, MarketRepository

DEFAULT_DISCOVERY_LOOKAHEAD_DAYS = 30


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Sync Kalshi markets in bounded discovery mode or watchlist-only mode."
    )
    parser.add_argument(
        "--watchlist-only",
        action="store_true",
        help="Only refresh markets listed in WATCH_TICKERS.",
    )
    return parser.parse_args()


async def _run(watchlist_only: bool) -> None:
    initialize_logging()
    now_ts = int(time.time())
    max_close_ts = now_ts + (DEFAULT_DISCOVERY_LOOKAHEAD_DAYS * 24 * 60 * 60)

    with get_sqlite_connection() as connection:
        bootstrap_schema(connection)
        market_repository = MarketRepository(connection)
        checkpoint_repository = CheckpointRepository(connection)

        async with KalshiHttpClient(base_url=settings.base_url) as client:
            result = await sync_markets(
                client=client,
                market_repository=market_repository,
                checkpoint_repository=checkpoint_repository,
                status=None if watchlist_only else "open",
                min_close_ts=None if watchlist_only else now_ts,
                max_close_ts=None if watchlist_only else max_close_ts,
                watchlist_tickers=settings.watch_tickers if watchlist_only else None,
            )

    print(
        "Synced markets "
        f"(pages_processed={result.pages_processed}, "
        f"markets_upserted={result.markets_upserted}, "
        f"checkpoint='{result.checkpoint_value}')"
    )


def main() -> None:
    args = _parse_args()
    asyncio.run(_run(watchlist_only=args.watchlist_only))


if __name__ == "__main__":
    main()
