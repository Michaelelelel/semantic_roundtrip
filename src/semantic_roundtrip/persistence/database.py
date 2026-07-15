"""SQLite persistence for experiment runs and pipeline results."""

import sqlite3
from datetime import datetime, timezone
from pathlib import Path
from types import TracebackType
from typing import Literal

from semantic_roundtrip.domain import (
    BenchmarkItem,
    GeneratedPrompt,
    ImageArtifact,
    TitlePrediction,
    VerificationResult,
)
from semantic_roundtrip.persistence.run_manager import RunContext


DATABASE_FILENAME = "pipeline_state.sqlite"
DATABASE_SCHEMA_VERSION = 2

RunStatus = Literal["created", "running", "completed", "failed"]


def _relative_path(path: Path, run_directory: Path) -> str:
    return path.relative_to(run_directory).as_posix()


def initialize_database(
    run_context: RunContext,
    run_name: str,
    input_config_path: Path,
    effective_config_path: Path,
) -> Path:
    """Create the run database and all tables needed by the pipeline."""
    database_path = run_context.directory / DATABASE_FILENAME

    if database_path.exists():
        raise FileExistsError(f"Database already exists: {database_path}")

    connection = sqlite3.connect(database_path)

    try:
        connection.execute("PRAGMA foreign_keys = ON")
        connection.execute(f"PRAGMA user_version = {DATABASE_SCHEMA_VERSION}")
        connection.executescript(
            """
            CREATE TABLE run_metadata (
                run_id TEXT PRIMARY KEY,
                name TEXT NOT NULL,
                created_at TEXT NOT NULL,
                finished_at TEXT,
                status TEXT NOT NULL CHECK (
                    status IN ('created', 'running', 'completed', 'failed')
                ),
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
                text TEXT NOT NULL,
                raw_response TEXT NOT NULL,
                UNIQUE (item_id, prompt_index)
            );

            CREATE TABLE images (
                image_id INTEGER PRIMARY KEY,
                prompt_id INTEGER NOT NULL REFERENCES prompts(prompt_id)
                    ON DELETE CASCADE,
                seed INTEGER NOT NULL,
                path TEXT NOT NULL UNIQUE,
                backend_job_id TEXT,
                raw_response TEXT NOT NULL,
                UNIQUE (prompt_id, seed)
            );

            CREATE TABLE verifications (
                verification_id INTEGER PRIMARY KEY,
                image_id INTEGER NOT NULL UNIQUE REFERENCES images(image_id)
                    ON DELETE CASCADE,
                passed INTEGER NOT NULL CHECK (passed IN (0, 1)),
                reason TEXT,
                raw_response TEXT NOT NULL
            );

            CREATE TABLE predictions (
                prediction_id INTEGER PRIMARY KEY,
                image_id INTEGER NOT NULL UNIQUE REFERENCES images(image_id)
                    ON DELETE CASCADE,
                title TEXT NOT NULL,
                confidence REAL,
                confidence_type TEXT,
                raw_response TEXT NOT NULL
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

            CREATE TABLE stage_errors (
                error_id INTEGER PRIMARY KEY,
                run_id TEXT NOT NULL REFERENCES run_metadata(run_id)
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
            CREATE INDEX stage_errors_run_stage_idx
                ON stage_errors(run_id, stage);
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


class RunDatabase:
    """Write one experiment's structured results to its SQLite database."""

    def __init__(self, database_path: Path, run_context: RunContext) -> None:
        self._run_context = run_context
        self._connection = sqlite3.connect(database_path)
        self._connection.execute("PRAGMA foreign_keys = ON")

    def __enter__(self) -> "RunDatabase":
        return self

    def __exit__(
        self,
        exception_type: type[BaseException] | None,
        exception: BaseException | None,
        traceback: TracebackType | None,
    ) -> None:
        self._connection.close()

    def _insert(self, statement: str, parameters: tuple[object, ...]) -> int:
        with self._connection:
            cursor = self._connection.execute(statement, parameters)
        return int(cursor.lastrowid)

    def update_run_status(self, status: RunStatus) -> None:
        """Update the run lifecycle state."""
        finished_at = None
        if status in {"completed", "failed"}:
            finished_at = datetime.now(timezone.utc).isoformat()

        with self._connection:
            self._connection.execute(
                """
                UPDATE run_metadata
                SET status = ?, finished_at = ?
                WHERE run_id = ?
                """,
                (status, finished_at, self._run_context.run_id),
            )

    def add_dataset_item(self, item_index: int, item: BenchmarkItem) -> int:
        return self._insert(
            """
            INSERT INTO dataset_items (run_id, item_index, domain, title)
            VALUES (?, ?, ?, ?)
            """,
            (
                self._run_context.run_id,
                item_index,
                item.domain,
                item.title,
            ),
        )

    def add_prompt(self, item_id: int, prompt: GeneratedPrompt) -> int:
        return self._insert(
            """
            INSERT INTO prompts (item_id, prompt_index, text, raw_response)
            VALUES (?, ?, ?, ?)
            """,
            (item_id, prompt.index, prompt.text, prompt.raw_response),
        )

    def add_image(self, prompt_id: int, image: ImageArtifact) -> int:
        return self._insert(
            """
            INSERT INTO images (
                prompt_id,
                seed,
                path,
                backend_job_id,
                raw_response
            )
            VALUES (?, ?, ?, ?, ?)
            """,
            (
                prompt_id,
                image.seed,
                _relative_path(image.path, self._run_context.directory),
                image.backend_job_id,
                image.raw_response,
            ),
        )

    def add_verification(
        self,
        image_id: int,
        result: VerificationResult,
    ) -> int:
        return self._insert(
            """
            INSERT INTO verifications (image_id, passed, reason, raw_response)
            VALUES (?, ?, ?, ?)
            """,
            (image_id, int(result.passed), result.reason, result.raw_response),
        )

    def add_prediction(self, image_id: int, prediction: TitlePrediction) -> int:
        return self._insert(
            """
            INSERT INTO predictions (
                image_id,
                title,
                confidence,
                confidence_type,
                raw_response
            )
            VALUES (?, ?, ?, ?, ?)
            """,
            (
                image_id,
                prediction.title,
                prediction.confidence,
                prediction.confidence_type,
                prediction.raw_response,
            ),
        )

    def add_evaluation(
        self,
        *,
        verification_id: int,
        prediction_id: int,
        title_exact_match: bool,
        included: bool,
        score: bool | None,
        method: str,
    ) -> int:
        stored_score = None if score is None else int(score)
        return self._insert(
            """
            INSERT INTO evaluations (
                verification_id,
                prediction_id,
                title_exact_match,
                included,
                score,
                method
            )
            VALUES (?, ?, ?, ?, ?, ?)
            """,
            (
                verification_id,
                prediction_id,
                int(title_exact_match),
                int(included),
                stored_score,
                method,
            ),
        )

    def add_stage_error(
        self,
        *,
        stage: str,
        attempt: int,
        error: Exception,
        item_id: int | None = None,
        prompt_id: int | None = None,
        image_id: int | None = None,
        raw_response: str | None = None,
    ) -> int:
        return self._insert(
            """
            INSERT INTO stage_errors (
                run_id,
                stage,
                item_id,
                prompt_id,
                image_id,
                attempt,
                error_type,
                message,
                raw_response,
                created_at
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                self._run_context.run_id,
                stage,
                item_id,
                prompt_id,
                image_id,
                attempt,
                type(error).__name__,
                str(error),
                raw_response,
                datetime.now(timezone.utc).isoformat(),
            ),
        )
