import sqlite3
from pathlib import Path

from app.storage.db import bootstrap_schema, get_sqlite_connection


def test_bootstrap_schema_creates_expected_tables(tmp_path: Path) -> None:
    db_path = tmp_path / "test.sqlite3"

    with get_sqlite_connection(db_path) as connection:
        bootstrap_schema(connection)

        table_rows = connection.execute(
            """
            SELECT name
            FROM sqlite_master
            WHERE type = 'table'
            ORDER BY name
            """
        ).fetchall()

        journal_mode = connection.execute("PRAGMA journal_mode;").fetchone()[0]

    table_names = {row["name"] for row in table_rows}

    assert {
        "balance_snapshots",
        "checkpoints",
        "events",
        "markets",
        "orderbook_snapshots",
        "positions",
        "sqlite_sequence",
        "trades",
    }.issubset(table_names)
    assert journal_mode == "wal"


def test_get_sqlite_connection_enables_foreign_keys(tmp_path: Path) -> None:
    db_path = tmp_path / "foreign_keys.sqlite3"

    with get_sqlite_connection(db_path) as connection:
        foreign_keys_enabled = connection.execute("PRAGMA foreign_keys;").fetchone()[0]

    assert foreign_keys_enabled == 1
