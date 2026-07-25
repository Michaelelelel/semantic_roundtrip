"""SQLite state for a job containing several independent experiment runs."""

import sqlite3
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from types import TracebackType
from typing import Literal

from semantic_roundtrip.job import JOB_DATABASE_FILENAME, JobContext, ResolvedJobConfig


JOB_DATABASE_SCHEMA_VERSION = 2

JobStatus = Literal[
    "created",
    "running",
    "paused",
    "completed",
    "failed",
    "interrupted",
]
JobEntryStatus = Literal[
    "pending",
    "running",
    "paused",
    "completed",
    "failed",
    "interrupted",
]


@dataclass(frozen=True, slots=True)
class JobRecord:
    job_id: str
    name: str
    created_at: datetime
    heartbeat_at: datetime | None
    finished_at: datetime | None
    status: str
    continue_on_error: bool
    max_parallel_experiments: int


@dataclass(frozen=True, slots=True)
class JobEntryRecord:
    entry_id: int
    entry_index: int
    run_directory: Path
    status: str
    started_at: datetime | None
    finished_at: datetime | None
    error_type: str | None
    error_message: str | None


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _parse_datetime(value: str | None) -> datetime | None:
    return None if value is None else datetime.fromisoformat(value)


def _connect(
    database_path: Path,
    *,
    create: bool = False,
    read_only: bool = False,
) -> sqlite3.Connection:
    if create and read_only:
        raise ValueError("A database connection cannot create and be read-only.")
    if not create and not database_path.is_file():
        raise FileNotFoundError(f"Job database does not exist: {database_path}")

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


def _require_current_schema(connection: sqlite3.Connection) -> None:
    version = int(connection.execute("PRAGMA user_version").fetchone()[0])
    if version != JOB_DATABASE_SCHEMA_VERSION:
        raise ValueError(
            f"Job database schema version {version} is not supported; "
            f"expected version {JOB_DATABASE_SCHEMA_VERSION}."
        )


def job_database_path(job_directory: Path) -> Path:
    """Return the expected SQLite path for a persisted job."""
    return job_directory / JOB_DATABASE_FILENAME


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

    connection = _connect(database_path, create=True)
    try:
        connection.execute("PRAGMA journal_mode = WAL")
        connection.execute(f"PRAGMA user_version = {JOB_DATABASE_SCHEMA_VERSION}")
        connection.executescript(
            """
            CREATE TABLE job_metadata (
                job_id TEXT PRIMARY KEY,
                name TEXT NOT NULL,
                created_at TEXT NOT NULL,
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
                max_parallel_experiments INTEGER NOT NULL
                    CHECK (max_parallel_experiments = 1),
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
        now = _utc_now()
        connection.execute(
            """
            INSERT INTO job_metadata (
                job_id,
                name,
                created_at,
                heartbeat_at,
                status,
                continue_on_error,
                max_parallel_experiments,
                input_config_path,
                effective_config_path
            )
            VALUES (?, ?, ?, ?, 'created', ?, ?, ?, ?)
            """,
            (
                context.job_id,
                config.job.name,
                context.created_at.isoformat(),
                now,
                int(config.job.continue_on_error),
                config.execution.max_parallel_experiments,
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


def _job_record(row: sqlite3.Row) -> JobRecord:
    return JobRecord(
        job_id=row["job_id"],
        name=row["name"],
        created_at=datetime.fromisoformat(row["created_at"]),
        heartbeat_at=_parse_datetime(row["heartbeat_at"]),
        finished_at=_parse_datetime(row["finished_at"]),
        status=row["status"],
        continue_on_error=bool(row["continue_on_error"]),
        max_parallel_experiments=int(row["max_parallel_experiments"]),
    )


def _entry_record(row: sqlite3.Row, job_directory: Path) -> JobEntryRecord:
    return JobEntryRecord(
        entry_id=int(row["entry_id"]),
        entry_index=int(row["entry_index"]),
        run_directory=job_directory / row["run_directory"],
        status=row["status"],
        started_at=_parse_datetime(row["started_at"]),
        finished_at=_parse_datetime(row["finished_at"]),
        error_type=row["error_type"],
        error_message=row["error_message"],
    )


def read_job_record(database_path: Path) -> JobRecord:
    """Read job metadata without requiring write permission."""
    connection = _connect(database_path, read_only=True)
    try:
        _require_current_schema(connection)
        row = connection.execute("SELECT * FROM job_metadata").fetchone()
        if row is None:
            raise ValueError(f"No job metadata found in {database_path}")
        return _job_record(row)
    finally:
        connection.close()


def read_job_entries(
    database_path: Path,
    job_directory: Path,
) -> list[JobEntryRecord]:
    """Read all job entries in execution order."""
    connection = _connect(database_path, read_only=True)
    try:
        _require_current_schema(connection)
        rows = connection.execute(
            "SELECT * FROM job_entries ORDER BY entry_index"
        ).fetchall()
        return [_entry_record(row, job_directory) for row in rows]
    finally:
        connection.close()


class JobDatabase:
    """Read and update one job's orchestration state."""

    def __init__(self, database_path: Path, context: JobContext) -> None:
        self._context = context
        self._connection = _connect(database_path)
        _require_current_schema(self._connection)

    def __enter__(self) -> "JobDatabase":
        return self

    def __exit__(
        self,
        exception_type: type[BaseException] | None,
        exception: BaseException | None,
        traceback: TracebackType | None,
    ) -> None:
        self._connection.close()

    def update_job_status(self, status: JobStatus) -> None:
        """Persist job lifecycle state and heartbeat."""
        now = _utc_now()
        finished_at = now if status in {"completed", "failed"} else None
        with self._connection:
            self._connection.execute(
                """
                UPDATE job_metadata
                SET status = ?, heartbeat_at = ?, finished_at = ?
                WHERE job_id = ?
                """,
                (status, now, finished_at, self._context.job_id),
            )

    def get_entry(self, entry_index: int) -> JobEntryRecord:
        row = self._connection.execute(
            """
            SELECT *
            FROM job_entries
            WHERE job_id = ? AND entry_index = ?
            """,
            (self._context.job_id, entry_index),
        ).fetchone()
        if row is None:
            raise ValueError(f"Unknown job entry index: {entry_index}")
        return _entry_record(row, self._context.directory)

    def entries(self) -> list[JobEntryRecord]:
        rows = self._connection.execute(
            """
            SELECT *
            FROM job_entries
            WHERE job_id = ?
            ORDER BY entry_index
            """,
            (self._context.job_id,),
        ).fetchall()
        return [_entry_record(row, self._context.directory) for row in rows]

    def mark_entry_running(
        self,
        entry_index: int,
    ) -> None:
        now = _utc_now()
        with self._connection:
            self._connection.execute(
                """
                UPDATE job_entries
                SET status = 'running',
                    started_at = COALESCE(started_at, ?),
                    finished_at = NULL
                WHERE job_id = ? AND entry_index = ?
                """,
                (
                    now,
                    self._context.job_id,
                    entry_index,
                ),
            )
            self._connection.execute(
                """
                UPDATE job_metadata
                SET heartbeat_at = ?
                WHERE job_id = ?
                """,
                (now, self._context.job_id),
            )

    def mark_entry_status(
        self,
        entry_index: int,
        status: JobEntryStatus,
        *,
        error: BaseException | None = None,
    ) -> None:
        now = _utc_now()
        error_type = None if error is None else type(error).__name__
        error_message = None if error is None else str(error)
        with self._connection:
            self._connection.execute(
                """
                UPDATE job_entries
                SET status = ?,
                    finished_at = ?,
                    error_type = ?,
                    error_message = ?
                WHERE job_id = ? AND entry_index = ?
                """,
                (
                    status,
                    now,
                    error_type,
                    error_message,
                    self._context.job_id,
                    entry_index,
                ),
            )
            self._connection.execute(
                """
                UPDATE job_metadata
                SET heartbeat_at = ?
                WHERE job_id = ?
                """,
                (now, self._context.job_id),
            )
