"""SQLite persistence, progress tracking, and run control."""

import sqlite3
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from types import TracebackType
from typing import Literal

from semantic_roundtrip.domain import (
    BenchmarkItem,
    GeneratedPrompt,
    ImageArtifact,
    PromptResponse,
    TitlePrediction,
    VerificationResult,
)
from semantic_roundtrip.persistence.run_manager import RunContext


DATABASE_FILENAME = "pipeline_state.sqlite"
DATABASE_SCHEMA_VERSION = 3

RunStatus = Literal[
    "created",
    "running",
    "pausing",
    "paused",
    "completed",
    "failed",
    "interrupted",
]
TaskStatus = Literal["pending", "running", "completed", "failed"]


@dataclass(frozen=True, slots=True)
class RunRecord:
    run_id: str
    name: str
    created_at: datetime
    status: str
    pause_requested: bool
    heartbeat_at: datetime | None
    finished_at: datetime | None


@dataclass(frozen=True, slots=True)
class TaskRecord:
    task_id: int
    task_key: str
    stage: str
    status: str
    attempt: int
    expected_outputs: int
    completed_outputs: int


@dataclass(frozen=True, slots=True)
class StageProgress:
    stage: str
    pending: int
    running: int
    completed: int
    failed: int
    produced_outputs: int


@dataclass(frozen=True, slots=True)
class ResultCounts:
    dataset_items: int
    prompts: int
    images: int
    verifications: int
    predictions: int
    evaluations: int


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _parse_datetime(value: str | None) -> datetime | None:
    return None if value is None else datetime.fromisoformat(value)


def _relative_path(path: Path, run_directory: Path) -> str:
    return path.relative_to(run_directory).as_posix()


def database_path_for_run(run_directory: Path) -> Path:
    """Return the expected database path for an existing run."""
    return run_directory / DATABASE_FILENAME


def _connect(
    database_path: Path,
    *,
    create: bool = False,
) -> sqlite3.Connection:
    if not create and not database_path.is_file():
        raise FileNotFoundError(f"Run database does not exist: {database_path}")

    connection = sqlite3.connect(database_path, timeout=5)
    connection.row_factory = sqlite3.Row
    connection.execute("PRAGMA foreign_keys = ON")
    connection.execute("PRAGMA busy_timeout = 5000")
    return connection


def _require_current_schema(connection: sqlite3.Connection) -> None:
    version = int(connection.execute("PRAGMA user_version").fetchone()[0])
    if version != DATABASE_SCHEMA_VERSION:
        raise ValueError(
            f"Database schema version {version} is not supported; "
            f"expected version {DATABASE_SCHEMA_VERSION}."
        )


def initialize_database(
    run_context: RunContext,
    run_name: str,
    input_config_path: Path,
    effective_config_path: Path,
) -> Path:
    """Create a schema-v3 database for a new experiment run."""
    database_path = run_context.directory / DATABASE_FILENAME

    if database_path.exists():
        raise FileExistsError(f"Database already exists: {database_path}")

    connection = _connect(database_path, create=True)

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

            CREATE TABLE prompt_batches (
                batch_id INTEGER PRIMARY KEY,
                item_id INTEGER NOT NULL REFERENCES dataset_items(item_id)
                    ON DELETE CASCADE,
                attempt INTEGER NOT NULL CHECK (attempt > 0),
                requested_count INTEGER NOT NULL CHECK (requested_count > 0),
                returned_count INTEGER NOT NULL CHECK (returned_count >= 0),
                stored_count INTEGER NOT NULL CHECK (stored_count >= 0),
                format_valid INTEGER NOT NULL CHECK (format_valid IN (0, 1)),
                parser_version TEXT NOT NULL,
                parser_error TEXT,
                backend_request_id TEXT,
                raw_response TEXT NOT NULL CHECK (length(raw_response) > 0),
                created_at TEXT NOT NULL
            );

            CREATE TABLE prompts (
                prompt_id INTEGER PRIMARY KEY,
                batch_id INTEGER NOT NULL REFERENCES prompt_batches(batch_id)
                    ON DELETE CASCADE,
                item_id INTEGER NOT NULL REFERENCES dataset_items(item_id)
                    ON DELETE CASCADE,
                prompt_index INTEGER NOT NULL,
                text TEXT NOT NULL,
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

            CREATE INDEX prompt_batches_item_id_idx
                ON prompt_batches(item_id);
            CREATE INDEX prompts_item_id_idx ON prompts(item_id);
            CREATE INDEX images_prompt_id_idx ON images(prompt_id);
            CREATE INDEX stage_tasks_run_stage_status_idx
                ON stage_tasks(run_id, stage, status);
            CREATE INDEX stage_errors_run_stage_idx
                ON stage_errors(run_id, stage);
            """
        )
        now = _utc_now()
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


def read_run_record(database_path: Path) -> RunRecord:
    """Read the single run metadata record."""
    connection = _connect(database_path)
    try:
        _require_current_schema(connection)
        row = connection.execute("SELECT * FROM run_metadata").fetchone()
        if row is None:
            raise ValueError(f"No run metadata found in {database_path}")
        return RunRecord(
            run_id=row["run_id"],
            name=row["name"],
            created_at=datetime.fromisoformat(row["created_at"]),
            status=row["status"],
            pause_requested=bool(row["pause_requested"]),
            heartbeat_at=_parse_datetime(row["heartbeat_at"]),
            finished_at=_parse_datetime(row["finished_at"]),
        )
    finally:
        connection.close()


def load_run_context(run_directory: Path) -> RunContext:
    """Reconstruct a run context from an existing schema-v3 database."""
    record = read_run_record(database_path_for_run(run_directory))
    return RunContext(
        run_id=record.run_id,
        directory=run_directory,
        created_at=record.created_at,
    )


def read_stage_progress(database_path: Path) -> list[StageProgress]:
    """Aggregate task progress for status displays."""
    connection = _connect(database_path)
    try:
        _require_current_schema(connection)
        rows = connection.execute(
            """
            SELECT
                stage,
                SUM(CASE WHEN status = 'pending' THEN 1 ELSE 0 END) AS pending,
                SUM(CASE WHEN status = 'running' THEN 1 ELSE 0 END) AS running,
                SUM(CASE WHEN status = 'completed' THEN 1 ELSE 0 END) AS completed,
                SUM(CASE WHEN status = 'failed' THEN 1 ELSE 0 END) AS failed,
                SUM(completed_outputs) AS produced_outputs
            FROM stage_tasks
            GROUP BY stage
            ORDER BY stage
            """
        ).fetchall()
        return [
            StageProgress(
                stage=row["stage"],
                pending=int(row["pending"]),
                running=int(row["running"]),
                completed=int(row["completed"]),
                failed=int(row["failed"]),
                produced_outputs=int(row["produced_outputs"]),
            )
            for row in rows
        ]
    finally:
        connection.close()


def request_run_pause(database_path: Path) -> RunRecord:
    """Request a cooperative pause from another process."""
    connection = _connect(database_path)
    try:
        _require_current_schema(connection)
        row = connection.execute("SELECT status FROM run_metadata").fetchone()
        if row is None:
            raise ValueError("Run metadata is missing.")

        status = row["status"]
        if status == "running":
            with connection:
                connection.execute(
                    """
                    UPDATE run_metadata
                    SET pause_requested = 1, status = 'pausing',
                        heartbeat_at = ?
                    """,
                    (_utc_now(),),
                )
        elif status not in {"pausing", "paused"}:
            raise ValueError(f"Cannot pause a run with status '{status}'.")
    finally:
        connection.close()

    return read_run_record(database_path)


class RunDatabase:
    """Read and write one experiment's schema-v3 SQLite database."""

    def __init__(self, database_path: Path, run_context: RunContext) -> None:
        self._run_context = run_context
        self._connection = _connect(database_path)
        _require_current_schema(self._connection)

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
        """Update lifecycle state and heartbeat."""
        finished_at = _utc_now() if status in {"completed", "failed"} else None
        with self._connection:
            self._connection.execute(
                """
                UPDATE run_metadata
                SET status = ?, finished_at = ?, heartbeat_at = ?
                WHERE run_id = ?
                """,
                (
                    status,
                    finished_at,
                    _utc_now(),
                    self._run_context.run_id,
                ),
            )

    def clear_pause_request(self) -> None:
        with self._connection:
            self._connection.execute(
                """
                UPDATE run_metadata
                SET pause_requested = 0, heartbeat_at = ?
                WHERE run_id = ?
                """,
                (_utc_now(), self._run_context.run_id),
            )

    def pause_requested(self) -> bool:
        row = self._connection.execute(
            """
            SELECT pause_requested
            FROM run_metadata
            WHERE run_id = ?
            """,
            (self._run_context.run_id,),
        ).fetchone()
        return bool(row["pause_requested"])

    def get_or_add_dataset_item(
        self,
        item_index: int,
        item: BenchmarkItem,
    ) -> int:
        row = self._connection.execute(
            """
            SELECT item_id, domain, title
            FROM dataset_items
            WHERE run_id = ? AND item_index = ?
            """,
            (self._run_context.run_id, item_index),
        ).fetchone()
        if row is not None:
            if row["domain"] != item.domain or row["title"] != item.title:
                raise ValueError(
                    f"Stored dataset item {item_index} differs from the snapshot."
                )
            return int(row["item_id"])

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

    def get_prompt(
        self,
        item_id: int,
        prompt_index: int,
    ) -> tuple[int, GeneratedPrompt] | None:
        row = self._connection.execute(
            """
            SELECT prompt_id, prompt_index, text
            FROM prompts
            WHERE item_id = ? AND prompt_index = ?
            """,
            (item_id, prompt_index),
        ).fetchone()
        if row is None:
            return None
        return (
            int(row["prompt_id"]),
            GeneratedPrompt(index=int(row["prompt_index"]), text=row["text"]),
        )

    def add_prompt_response(
        self,
        item_id: int,
        prompt: GeneratedPrompt,
        response: PromptResponse,
        attempt: int,
    ) -> int:
        """Persist one prompt response using the temporary schema-v3 table."""
        with self._connection:
            cursor = self._connection.execute(
                """
                INSERT INTO prompt_batches (
                    item_id,
                    attempt,
                    requested_count,
                    returned_count,
                    stored_count,
                    format_valid,
                    parser_version,
                    parser_error,
                    backend_request_id,
                    raw_response,
                    created_at
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    item_id,
                    attempt,
                    1,
                    1,
                    1,
                    1,
                    "single_plain_text_v1",
                    None,
                    response.backend_request_id,
                    response.raw_response,
                    _utc_now(),
                ),
            )
            batch_id = int(cursor.lastrowid)
            prompt_cursor = self._connection.execute(
                """
                INSERT INTO prompts (
                    batch_id,
                    item_id,
                    prompt_index,
                    text
                )
                VALUES (?, ?, ?, ?)
                """,
                (batch_id, item_id, prompt.index, prompt.text),
            )
        return int(prompt_cursor.lastrowid)

    def get_image(
        self,
        prompt_id: int,
        seed: int,
    ) -> tuple[int, ImageArtifact] | None:
        row = self._connection.execute(
            """
            SELECT image_id, path, seed, raw_response, backend_job_id
            FROM images
            WHERE prompt_id = ? AND seed = ?
            """,
            (prompt_id, seed),
        ).fetchone()
        if row is None:
            return None
        return (
            int(row["image_id"]),
            ImageArtifact(
                path=self._run_context.directory / row["path"],
                seed=int(row["seed"]),
                raw_response=row["raw_response"],
                backend_job_id=row["backend_job_id"],
            ),
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

    def get_verification(
        self,
        image_id: int,
    ) -> tuple[int, VerificationResult] | None:
        row = self._connection.execute(
            """
            SELECT verification_id, passed, reason, raw_response
            FROM verifications
            WHERE image_id = ?
            """,
            (image_id,),
        ).fetchone()
        if row is None:
            return None
        return (
            int(row["verification_id"]),
            VerificationResult(
                passed=bool(row["passed"]),
                reason=row["reason"],
                raw_response=row["raw_response"],
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

    def get_prediction(
        self,
        image_id: int,
    ) -> tuple[int, TitlePrediction] | None:
        row = self._connection.execute(
            """
            SELECT
                prediction_id,
                title,
                confidence,
                confidence_type,
                raw_response
            FROM predictions
            WHERE image_id = ?
            """,
            (image_id,),
        ).fetchone()
        if row is None:
            return None
        return (
            int(row["prediction_id"]),
            TitlePrediction(
                title=row["title"],
                confidence=row["confidence"],
                confidence_type=row["confidence_type"],
                raw_response=row["raw_response"],
            ),
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

    def add_evaluation_if_missing(
        self,
        *,
        verification_id: int,
        prediction_id: int,
        title_exact_match: bool,
        included: bool,
        score: bool | None,
        method: str,
    ) -> int:
        row = self._connection.execute(
            """
            SELECT evaluation_id
            FROM evaluations
            WHERE prediction_id = ?
            """,
            (prediction_id,),
        ).fetchone()
        if row is not None:
            return int(row["evaluation_id"])

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

    def get_or_create_task(
        self,
        *,
        task_key: str,
        stage: str,
        expected_outputs: int,
        item_id: int | None = None,
        prompt_id: int | None = None,
        image_id: int | None = None,
        seed: int | None = None,
    ) -> TaskRecord:
        now = _utc_now()
        with self._connection:
            self._connection.execute(
                """
                INSERT OR IGNORE INTO stage_tasks (
                    run_id,
                    task_key,
                    stage,
                    status,
                    item_id,
                    prompt_id,
                    image_id,
                    seed,
                    expected_outputs,
                    created_at,
                    updated_at
                )
                VALUES (?, ?, ?, 'pending', ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    self._run_context.run_id,
                    task_key,
                    stage,
                    item_id,
                    prompt_id,
                    image_id,
                    seed,
                    expected_outputs,
                    now,
                    now,
                ),
            )
        row = self._connection.execute(
            """
            SELECT *
            FROM stage_tasks
            WHERE run_id = ? AND task_key = ?
            """,
            (self._run_context.run_id, task_key),
        ).fetchone()
        if row is None:
            raise RuntimeError(f"Could not create stage task {task_key}")
        return self._task_from_row(row)

    def get_task(self, task_id: int) -> TaskRecord:
        row = self._connection.execute(
            "SELECT * FROM stage_tasks WHERE task_id = ?",
            (task_id,),
        ).fetchone()
        if row is None:
            raise ValueError(f"Unknown task ID: {task_id}")
        return self._task_from_row(row)

    @staticmethod
    def _task_from_row(row: sqlite3.Row) -> TaskRecord:
        return TaskRecord(
            task_id=int(row["task_id"]),
            task_key=row["task_key"],
            stage=row["stage"],
            status=row["status"],
            attempt=int(row["attempt"]),
            expected_outputs=int(row["expected_outputs"]),
            completed_outputs=int(row["completed_outputs"]),
        )

    def mark_task_running(self, task_id: int) -> int:
        now = _utc_now()
        with self._connection:
            self._connection.execute(
                """
                UPDATE stage_tasks
                SET status = 'running',
                    attempt = attempt + 1,
                    started_at = COALESCE(started_at, ?),
                    updated_at = ?,
                    finished_at = NULL
                WHERE task_id = ?
                """,
                (now, now, task_id),
            )
            self._connection.execute(
                """
                UPDATE run_metadata
                SET heartbeat_at = ?
                WHERE run_id = ?
                """,
                (now, self._run_context.run_id),
            )
        return self.get_task(task_id).attempt

    def mark_task_completed(self, task_id: int, completed_outputs: int) -> None:
        now = _utc_now()
        with self._connection:
            self._connection.execute(
                """
                UPDATE stage_tasks
                SET status = 'completed',
                    completed_outputs = ?,
                    updated_at = ?,
                    finished_at = ?
                WHERE task_id = ?
                """,
                (completed_outputs, now, now, task_id),
            )
            self._connection.execute(
                """
                UPDATE run_metadata
                SET heartbeat_at = ?
                WHERE run_id = ?
                """,
                (now, self._run_context.run_id),
            )

    def mark_task_failed(self, task_id: int) -> None:
        now = _utc_now()
        with self._connection:
            self._connection.execute(
                """
                UPDATE stage_tasks
                SET status = 'failed', updated_at = ?, finished_at = ?
                WHERE task_id = ?
                """,
                (now, now, task_id),
            )

    def add_stage_error(
        self,
        *,
        task_id: int,
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
                task_id,
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
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                self._run_context.run_id,
                task_id,
                stage,
                item_id,
                prompt_id,
                image_id,
                attempt,
                type(error).__name__,
                str(error),
                raw_response,
                _utc_now(),
            ),
        )

    def result_counts(self) -> ResultCounts:
        row = self._connection.execute(
            """
            SELECT
                (SELECT COUNT(*) FROM dataset_items) AS dataset_items,
                (SELECT COUNT(*) FROM prompts) AS prompts,
                (SELECT COUNT(*) FROM images) AS images,
                (SELECT COUNT(*) FROM verifications) AS verifications,
                (SELECT COUNT(*) FROM predictions) AS predictions,
                (SELECT COUNT(*) FROM evaluations) AS evaluations
            """
        ).fetchone()
        return ResultCounts(
            dataset_items=int(row["dataset_items"]),
            prompts=int(row["prompts"]),
            images=int(row["images"]),
            verifications=int(row["verifications"]),
            predictions=int(row["predictions"]),
            evaluations=int(row["evaluations"]),
        )
