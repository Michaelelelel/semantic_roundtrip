"""Schema creation and connection rules for experiment-run databases."""

import sqlite3
from pathlib import Path

from semantic_roundtrip.persistence.run_manager import RunContext
from semantic_roundtrip.persistence.sqlite import (
    connect_sqlite,
    require_schema,
    utc_now,
)


DATABASE_FILENAME = "pipeline_state.sqlite"
DATABASE_SCHEMA_VERSION = 4


def database_path_for_run(run_directory: Path) -> Path:
    """Return the expected database path for an existing run."""
    return run_directory / DATABASE_FILENAME


def connect_run_database(
    database_path: Path,
    *,
    create: bool = False,
    read_only: bool = False,
) -> sqlite3.Connection:
    """Open a run database with the project's SQLite settings."""
    return connect_sqlite(
        database_path,
        label="Run database",
        create=create,
        read_only=read_only,
    )


def require_run_schema(connection: sqlite3.Connection) -> None:
    """Require the current run-database schema."""
    require_schema(
        connection,
        expected_version=DATABASE_SCHEMA_VERSION,
        label="Database",
    )


def _relative_path(path: Path, run_directory: Path) -> str:
    return path.relative_to(run_directory).as_posix()


def initialize_database(
    run_context: RunContext,
    run_name: str,
    input_config_path: Path,
    effective_config_path: Path,
) -> Path:
    """Create a schema-v4 database for a new experiment run."""
    database_path = database_path_for_run(run_context.directory)
    if database_path.exists():
        raise FileExistsError(f"Database already exists: {database_path}")

    connection = connect_run_database(database_path, create=True)
    try:
        connection.execute("PRAGMA journal_mode = WAL")
        connection.execute(f"PRAGMA user_version = {DATABASE_SCHEMA_VERSION}")
        connection.executescript(
            """
            CREATE TABLE run_metadata (
                run_id TEXT PRIMARY KEY,
                name TEXT NOT NULL,
                created_at TEXT NOT NULL,
                heartbeat_at TEXT,
                finished_at TEXT,
                status TEXT NOT NULL CHECK (
                    status IN (
                        'created',
                        'running',
                        'pausing',
                        'paused',
                        'completed',
                        'failed',
                        'interrupted'
                    )
                ),
                pause_requested INTEGER NOT NULL DEFAULT 0
                    CHECK (pause_requested IN (0, 1)),
                input_config_path TEXT NOT NULL,
                effective_config_path TEXT NOT NULL
            );

            CREATE TABLE dataset_items (
                item_id INTEGER PRIMARY KEY,
                run_id TEXT NOT NULL REFERENCES run_metadata(run_id)
                    ON DELETE CASCADE,
                item_index INTEGER NOT NULL,
                domain TEXT NOT NULL,
                title TEXT NOT NULL,
                UNIQUE (run_id, item_index)
            );

            CREATE TABLE prompts (
                prompt_id INTEGER PRIMARY KEY,
                item_id INTEGER NOT NULL REFERENCES dataset_items(item_id)
                    ON DELETE CASCADE,
                prompt_index INTEGER NOT NULL,
                sampling_seed INTEGER NOT NULL CHECK (sampling_seed >= 0),
                text TEXT NOT NULL CHECK (length(text) > 0),
                backend_request_id TEXT,
                raw_response TEXT NOT NULL CHECK (length(raw_response) > 0),
                created_at TEXT NOT NULL,
                UNIQUE (item_id, prompt_index)
            );

            CREATE TABLE images (
                image_id INTEGER PRIMARY KEY,
                prompt_id INTEGER NOT NULL REFERENCES prompts(prompt_id)
                    ON DELETE CASCADE,
                seed INTEGER NOT NULL,
                path TEXT NOT NULL UNIQUE,
                backend_job_id TEXT,
                raw_response TEXT NOT NULL CHECK (length(raw_response) > 0),
                UNIQUE (prompt_id, seed)
            );

            CREATE TABLE verifications (
                verification_id INTEGER PRIMARY KEY,
                image_id INTEGER NOT NULL UNIQUE REFERENCES images(image_id)
                    ON DELETE CASCADE,
                passed INTEGER NOT NULL CHECK (passed IN (0, 1)),
                reason TEXT,
                raw_response TEXT NOT NULL CHECK (length(raw_response) > 0)
            );

            CREATE TABLE predictions (
                prediction_id INTEGER PRIMARY KEY,
                image_id INTEGER NOT NULL UNIQUE REFERENCES images(image_id)
                    ON DELETE CASCADE,
                title TEXT NOT NULL,
                confidence REAL,
                confidence_type TEXT,
                raw_response TEXT NOT NULL CHECK (length(raw_response) > 0)
            );

            CREATE TABLE evaluations (
                evaluation_id INTEGER PRIMARY KEY,
                verification_id INTEGER NOT NULL UNIQUE
                    REFERENCES verifications(verification_id) ON DELETE CASCADE,
                prediction_id INTEGER NOT NULL UNIQUE
                    REFERENCES predictions(prediction_id) ON DELETE CASCADE,
                title_exact_match INTEGER NOT NULL
                    CHECK (title_exact_match IN (0, 1)),
                included INTEGER NOT NULL CHECK (included IN (0, 1)),
                score INTEGER CHECK (score IS NULL OR score IN (0, 1)),
                method TEXT NOT NULL
            );

            CREATE TABLE stage_tasks (
                task_id INTEGER PRIMARY KEY,
                run_id TEXT NOT NULL REFERENCES run_metadata(run_id)
                    ON DELETE CASCADE,
                task_key TEXT NOT NULL,
                stage TEXT NOT NULL,
                status TEXT NOT NULL CHECK (
                    status IN ('pending', 'running', 'completed', 'failed')
                ),
                item_id INTEGER REFERENCES dataset_items(item_id)
                    ON DELETE CASCADE,
                prompt_id INTEGER REFERENCES prompts(prompt_id)
                    ON DELETE CASCADE,
                image_id INTEGER REFERENCES images(image_id)
                    ON DELETE CASCADE,
                seed INTEGER,
                attempt INTEGER NOT NULL DEFAULT 0 CHECK (attempt >= 0),
                expected_outputs INTEGER NOT NULL DEFAULT 1
                    CHECK (expected_outputs >= 0),
                completed_outputs INTEGER NOT NULL DEFAULT 0
                    CHECK (completed_outputs >= 0),
                created_at TEXT NOT NULL,
                started_at TEXT,
                updated_at TEXT NOT NULL,
                finished_at TEXT,
                UNIQUE (run_id, task_key)
            );

            CREATE TABLE stage_errors (
                error_id INTEGER PRIMARY KEY,
                run_id TEXT NOT NULL REFERENCES run_metadata(run_id)
                    ON DELETE CASCADE,
                task_id INTEGER REFERENCES stage_tasks(task_id)
                    ON DELETE CASCADE,
                stage TEXT NOT NULL,
                item_id INTEGER REFERENCES dataset_items(item_id)
                    ON DELETE CASCADE,
                prompt_id INTEGER REFERENCES prompts(prompt_id)
                    ON DELETE CASCADE,
                image_id INTEGER REFERENCES images(image_id)
                    ON DELETE CASCADE,
                attempt INTEGER NOT NULL CHECK (attempt > 0),
                error_type TEXT NOT NULL,
                message TEXT NOT NULL,
                raw_response TEXT,
                created_at TEXT NOT NULL
            );

            CREATE INDEX prompts_item_id_idx ON prompts(item_id);
            CREATE INDEX images_prompt_id_idx ON images(prompt_id);
            CREATE INDEX stage_tasks_run_stage_status_idx
                ON stage_tasks(run_id, stage, status);
            CREATE INDEX stage_errors_run_stage_idx
                ON stage_errors(run_id, stage);
            """
        )
        now = utc_now()
        connection.execute(
            """
            INSERT INTO run_metadata (
                run_id,
                name,
                created_at,
                heartbeat_at,
                status,
                input_config_path,
                effective_config_path
            )
            VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            (
                run_context.run_id,
                run_name,
                run_context.created_at.isoformat(),
                now,
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
