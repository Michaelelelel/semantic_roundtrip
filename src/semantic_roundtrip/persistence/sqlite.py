"""Shared low-level SQLite connection and timestamp helpers."""

import sqlite3
from datetime import UTC, datetime
from pathlib import Path

PERSISTENCE_ERRORS = (sqlite3.Error,)


def utc_now() -> str:
    """Return the current UTC timestamp in the persisted ISO format."""
    return datetime.now(UTC).isoformat()


def parse_datetime(value: str | None) -> datetime | None:
    """Parse an optional persisted ISO timestamp."""
    return None if value is None else datetime.fromisoformat(value)


def connect_sqlite(
    database_path: Path,
    *,
    label: str,
    create: bool = False,
    read_only: bool = False,
) -> sqlite3.Connection:
    """Open a consistently configured SQLite connection."""
    if create and read_only:
        raise ValueError("A database connection cannot create and be read-only.")
    if not create and not database_path.is_file():
        raise FileNotFoundError(f"{label} does not exist: {database_path}")

    if read_only:
        uri = f"{database_path.resolve().as_uri()}?mode=ro"
        connection = sqlite3.connect(uri, timeout=5, uri=True)
        connection.execute("PRAGMA query_only = ON")
    else:
        connection = sqlite3.connect(database_path, timeout=5)

    connection.row_factory = sqlite3.Row
    connection.execute("PRAGMA foreign_keys = ON")
    connection.execute("PRAGMA busy_timeout = 5000")
    return connection


def require_schema(
    connection: sqlite3.Connection,
    *,
    expected_version: int,
    label: str,
) -> None:
    """Reject databases that do not use the expected development schema."""
    version = int(connection.execute("PRAGMA user_version").fetchone()[0])
    if version != expected_version:
        raise ValueError(
            f"{label} schema version {version} is not supported; "
            f"expected version {expected_version}."
        )
