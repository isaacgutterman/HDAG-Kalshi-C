from __future__ import annotations

import sqlite3
from pathlib import Path

from app.config import settings


SCHEMA_PATH = Path(__file__).with_name("schema.sql")


def get_sqlite_connection(db_path: str | Path | None = None) -> sqlite3.Connection:
    resolved_path = Path(db_path) if db_path is not None else settings.sqlite_db_path
    resolved_path.parent.mkdir(parents=True, exist_ok=True)

    connection = sqlite3.connect(resolved_path)
    connection.row_factory = sqlite3.Row
    connection.execute("PRAGMA foreign_keys = ON;")

    return connection


def enable_wal_mode(connection: sqlite3.Connection) -> str:
    cursor = connection.execute("PRAGMA journal_mode = WAL;")
    row = cursor.fetchone()
    cursor.close()

    connection.execute("PRAGMA synchronous = NORMAL;")

    if row is None:
        raise RuntimeError("Failed to set SQLite journal mode to WAL")

    return str(row[0])


def bootstrap_schema(
    connection: sqlite3.Connection,
    schema_path: str | Path | None = None,
) -> None:
    resolved_schema_path = Path(schema_path) if schema_path is not None else SCHEMA_PATH
    schema_sql = resolved_schema_path.read_text(encoding="utf-8")

    enable_wal_mode(connection)
    connection.executescript(schema_sql)
    connection.commit()
