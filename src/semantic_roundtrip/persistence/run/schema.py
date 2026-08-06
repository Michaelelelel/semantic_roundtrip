"""Schema creation and connection rules for experiment-run databases."""

import sqlite3
from pathlib import Path

from semantic_roundtrip.persistence.run.manager import RunContext
from semantic_roundtrip.persistence.sqlite import (
    connect_sqlite,
    require_schema,
    utc_now,
)


DATABASE_FILENAME = "pipeline_state.sqlite"
DATABASE_SCHEMA_VERSION = 8


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
    """Create a schema-v7 database for a new experiment run."""
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
                started_at TEXT,
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
                item_key TEXT NOT NULL,
                domain TEXT NOT NULL,
                title TEXT NOT NULL,
                UNIQUE (run_id, item_index),
                UNIQUE (run_id, item_key)
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

            CREATE TABLE image_descriptions (
                description_id INTEGER PRIMARY KEY,
                image_id INTEGER NOT NULL UNIQUE REFERENCES images(image_id)
                    ON DELETE CASCADE,
                text TEXT NOT NULL CHECK (length(text) > 0),
                backend_request_id TEXT,
                raw_response TEXT NOT NULL CHECK (length(raw_response) > 0),
                created_at TEXT NOT NULL,
                UNIQUE (description_id, image_id)
            );

            CREATE TABLE predictions (
                prediction_id INTEGER PRIMARY KEY,
                image_id INTEGER NOT NULL REFERENCES images(image_id)
                    ON DELETE CASCADE,
                description_id INTEGER,
                input_kind TEXT NOT NULL
                    CHECK (input_kind IN ('image', 'description')),
                title TEXT NOT NULL,
                confidence REAL,
                confidence_type TEXT,
                raw_response TEXT NOT NULL CHECK (length(raw_response) > 0),
                CHECK (
                    (input_kind = 'image' AND description_id IS NULL)
                    OR
                    (input_kind = 'description' AND description_id IS NOT NULL)
                ),
                FOREIGN KEY (description_id, image_id)
                    REFERENCES image_descriptions(description_id, image_id)
                    ON DELETE CASCADE,
                UNIQUE (image_id, input_kind)
            );

            CREATE TABLE evaluations (
                evaluation_id INTEGER PRIMARY KEY,
                verification_id INTEGER NOT NULL
                    REFERENCES verifications(verification_id) ON DELETE CASCADE,
                prediction_id INTEGER NOT NULL UNIQUE
                    REFERENCES predictions(prediction_id) ON DELETE CASCADE,
                exact_match INTEGER NOT NULL
                    CHECK (exact_match IN (0, 1)),
                exact_method TEXT NOT NULL
            );

            CREATE TABLE runtime_events (
                runtime_event_id INTEGER PRIMARY KEY,
                run_id TEXT NOT NULL REFERENCES run_metadata(run_id)
                    ON DELETE CASCADE,
                stage TEXT NOT NULL,
                backend_alias TEXT NOT NULL,
                controller TEXT NOT NULL,
                resource_group TEXT NOT NULL,
                model_id TEXT,
                action TEXT NOT NULL
                    CHECK (action IN ('load', 'reuse', 'unload')),
                status TEXT NOT NULL
                    CHECK (status IN ('started', 'completed', 'failed')),
                started_at TEXT NOT NULL,
                finished_at TEXT,
                error_type TEXT,
                error_message TEXT
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
            CREATE INDEX predictions_image_id_idx ON predictions(image_id);
            CREATE INDEX evaluations_verification_id_idx
                ON evaluations(verification_id);
            CREATE INDEX stage_tasks_run_stage_status_idx
                ON stage_tasks(run_id, stage, status);
            CREATE INDEX stage_errors_run_stage_idx
                ON stage_errors(run_id, stage);
            CREATE INDEX runtime_events_run_stage_idx
                ON runtime_events(run_id, stage, runtime_event_id);
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
