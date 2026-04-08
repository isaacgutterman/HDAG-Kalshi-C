from __future__ import annotations

import argparse
import asyncio

from app.client import KalshiHttpClient
from app.config import settings
from app.ingest.orderbooks import poll_orderbooks
from app.logging_config import initialize_logging
from app.storage.db import bootstrap_schema, get_sqlite_connection
from app.storage.repositories import MarketRepository, OrderbookSnapshotRepository


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Poll Kalshi orderbook snapshots")
    parser.add_argument(
        "--poll-interval-seconds",
        type=float,
        default=5.0,
        help="Seconds to wait between polls",
    )
    parser.add_argument(
        "--max-polls",
        type=int,
        default=1,
        help="Number of polling passes to run",
    )
    return parser.parse_args()


async def _run() -> None:
    args = _parse_args()
    initialize_logging()

    with get_sqlite_connection() as connection:
        bootstrap_schema(connection)
        market_repository = MarketRepository(connection)
        orderbook_repository = OrderbookSnapshotRepository(connection)

        async with KalshiHttpClient(base_url=settings.base_url) as client:
            result = await poll_orderbooks(
                client=client,
                orderbook_repository=orderbook_repository,
                market_repository=market_repository,
                market_tickers=settings.watch_tickers,
                poll_interval_seconds=args.poll_interval_seconds,
                max_polls=args.max_polls,
            )

    print(
        "Polled orderbooks "
        f"(polls_completed={result.polls_completed}, "
        f"markets_processed={result.markets_processed}, "
        f"levels_inserted={result.levels_inserted})"
    )


def main() -> None:
    asyncio.run(_run())


if __name__ == "__main__":
    main()
