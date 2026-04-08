from __future__ import annotations

from app.config import settings
from app.storage.db import bootstrap_schema, get_sqlite_connection


def main() -> None:
    with get_sqlite_connection() as connection:
        bootstrap_schema(connection)

    print(f"Bootstrapped SQLite schema at {settings.sqlite_db_path}")


if __name__ == "__main__":
    main()
