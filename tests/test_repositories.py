from pathlib import Path

from app.storage.db import bootstrap_schema, get_sqlite_connection
from app.storage.repositories import CheckpointRepository


def test_checkpoint_repository_get_returns_none_when_missing(tmp_path: Path) -> None:
    db_path = tmp_path / "checkpoints.sqlite3"

    with get_sqlite_connection(db_path) as connection:
        bootstrap_schema(connection)
        repository = CheckpointRepository(connection)

        checkpoint = repository.get("historical_markets")

    assert checkpoint is None


def test_checkpoint_repository_set_inserts_and_gets_checkpoint(tmp_path: Path) -> None:
    db_path = tmp_path / "checkpoints.sqlite3"

    with get_sqlite_connection(db_path) as connection:
        bootstrap_schema(connection)
        repository = CheckpointRepository(connection)

        saved_checkpoint = repository.set("historical_markets", "cursor-001")
        loaded_checkpoint = repository.get("historical_markets")

    assert loaded_checkpoint == saved_checkpoint
    assert loaded_checkpoint is not None
    assert loaded_checkpoint.job_name == "historical_markets"
    assert loaded_checkpoint.value == "cursor-001"
    assert loaded_checkpoint.updated_ts_ms > 0


def test_checkpoint_repository_set_updates_existing_checkpoint(tmp_path: Path) -> None:
    db_path = tmp_path / "checkpoints.sqlite3"

    with get_sqlite_connection(db_path) as connection:
        bootstrap_schema(connection)
        repository = CheckpointRepository(connection)

        first_checkpoint = repository.set("live_trades", "cursor-001")
        second_checkpoint = repository.set("live_trades", "cursor-002")
        loaded_checkpoint = repository.get("live_trades")

    assert loaded_checkpoint == second_checkpoint
    assert loaded_checkpoint is not None
    assert loaded_checkpoint.value == "cursor-002"
    assert loaded_checkpoint.updated_ts_ms >= first_checkpoint.updated_ts_ms
