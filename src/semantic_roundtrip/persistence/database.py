"""SQLite initialization for experiment runs."""

import sqlite3
from pathlib import Path

from semantic_roundtrip.persistence.run_manager import RunContext


DATABASE_FILENAME = "pipeline_state.sqlite"
DATABASE_SCHEMA_VERSION = 1


def _relative_path(path: Path, run_directory: Path) -> str:
    return path.relative_to(run_directory).as_posix()


def initialize_database(
    run_context: RunContext,
    run_name: str,
    input_config_path: Path,
    effective_config_path: Path,
) -> Path:
    """Create the run database and insert its initial metadata record."""
    database_path = run_context.directory / DATABASE_FILENAME

    if database_path.exists():
        raise FileExistsError(f"Database already exists: {database_path}")

    connection = sqlite3.connect(database_path)

    try:
        connection.execute("PRAGMA foreign_keys = ON")
        connection.execute(
            f"PRAGMA user_version = {DATABASE_SCHEMA_VERSION}"
        )
        connection.execute(
            """
            CREATE TABLE run_metadata (
                run_id TEXT PRIMARY KEY,
                name TEXT NOT NULL,
                created_at TEXT NOT NULL,
                status TEXT NOT NULL CHECK (
                    status IN ('created', 'running', 'completed', 'failed')
                ),
                input_config_path TEXT NOT NULL,
                effective_config_path TEXT NOT NULL
            )
            """
        )
        connection.execute(
            """
            INSERT INTO run_metadata (
                run_id,
                name,
                created_at,
                status,
                input_config_path,
                effective_config_path
            )
            VALUES (?, ?, ?, ?, ?, ?)
            """,
            (
                run_context.run_id,
                run_name,
                run_context.created_at.isoformat(),
                "created",
                _relative_path(input_config_path, run_context.directory),
                _relative_path(effective_config_path, run_context.directory),
            ),
        )
        connection.commit()
    except Exception:
        connection.rollback()
        raise
    finally:
        connection.close()

    return database_path
