"""Schema creation and connection rules for persisted job databases."""

import sqlite3
from pathlib import Path

from semantic_roundtrip.job import JOB_DATABASE_FILENAME, JobContext, ResolvedJobConfig
from semantic_roundtrip.persistence.sqlite import (
    connect_sqlite,
    require_schema,
    utc_now,
)


JOB_DATABASE_SCHEMA_VERSION = 3


def job_database_path(job_directory: Path) -> Path:
    """Return the expected SQLite path for a persisted job."""
    return job_directory / JOB_DATABASE_FILENAME


def connect_job_database(
    database_path: Path,
    *,
    create: bool = False,
    read_only: bool = False,
) -> sqlite3.Connection:
    """Open a job database with the project's SQLite settings."""
    return connect_sqlite(
        database_path,
        label="Job database",
        create=create,
        read_only=read_only,
    )


def require_job_schema(connection: sqlite3.Connection) -> None:
    """Require the current job-database schema."""
    require_schema(
        connection,
        expected_version=JOB_DATABASE_SCHEMA_VERSION,
        label="Job database",
    )


def _relative_path(path: Path, directory: Path) -> str:
    return path.resolve().relative_to(directory.resolve()).as_posix()


def initialize_job_database(
    context: JobContext,
    config: ResolvedJobConfig,
    input_config_path: Path,
    effective_config_path: Path,
    run_directories: list[Path],
) -> Path:
    """Create the state database for a new job."""
    if len(run_directories) != len(config.entries):
        raise ValueError("Every job entry requires one prepared child run.")

    database_path = job_database_path(context.directory)
    if database_path.exists():
        raise FileExistsError(f"Job database already exists: {database_path}")

    connection = connect_job_database(database_path, create=True)
    try:
        connection.execute("PRAGMA journal_mode = WAL")
        connection.execute(f"PRAGMA user_version = {JOB_DATABASE_SCHEMA_VERSION}")
        connection.executescript(
            """
            CREATE TABLE job_metadata (
                job_id TEXT PRIMARY KEY,
                name TEXT NOT NULL,
                created_at TEXT NOT NULL,
                started_at TEXT,
                heartbeat_at TEXT,
                finished_at TEXT,
                status TEXT NOT NULL CHECK (
                    status IN (
                        'created',
                        'running',
                        'paused',
                        'completed',
                        'failed',
                        'interrupted'
                    )
                ),
                continue_on_error INTEGER NOT NULL
                    CHECK (continue_on_error IN (0, 1)),
                input_config_path TEXT NOT NULL,
                effective_config_path TEXT NOT NULL
            );

            CREATE TABLE job_entries (
                entry_id INTEGER PRIMARY KEY,
                job_id TEXT NOT NULL REFERENCES job_metadata(job_id)
                    ON DELETE CASCADE,
                entry_index INTEGER NOT NULL,
                run_directory TEXT NOT NULL,
                status TEXT NOT NULL CHECK (
                    status IN (
                        'pending',
                        'running',
                        'paused',
                        'completed',
                        'failed',
                        'interrupted'
                    )
                ),
                started_at TEXT,
                finished_at TEXT,
                error_type TEXT,
                error_message TEXT,
                UNIQUE (job_id, entry_index)
            );
            """
        )
        now = utc_now()
        connection.execute(
            """
            INSERT INTO job_metadata (
                job_id,
                name,
                created_at,
                heartbeat_at,
                status,
                continue_on_error,
                input_config_path,
                effective_config_path
            )
            VALUES (?, ?, ?, ?, 'created', ?, ?, ?)
            """,
            (
                context.job_id,
                config.job.name,
                context.created_at.isoformat(),
                now,
                int(config.job.continue_on_error),
                _relative_path(input_config_path, context.directory),
                _relative_path(effective_config_path, context.directory),
            ),
        )

        for entry in config.entries:
            connection.execute(
                """
                INSERT INTO job_entries (
                    job_id,
                    entry_index,
                    run_directory,
                    status
                )
                VALUES (?, ?, ?, 'pending')
                """,
                (
                    context.job_id,
                    entry.index,
                    run_directories[entry.index].as_posix(),
                ),
            )
        connection.commit()
    except Exception:
        connection.rollback()
        raise
    finally:
        connection.close()

    return database_path
