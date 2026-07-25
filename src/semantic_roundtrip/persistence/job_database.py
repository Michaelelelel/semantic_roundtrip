"""Read and update persisted job orchestration state."""

import sqlite3
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from types import TracebackType
from typing import Literal

from semantic_roundtrip.job import JobContext
from semantic_roundtrip.persistence.job_schema import (
    connect_job_database,
    require_job_schema,
)
from semantic_roundtrip.persistence.sqlite import parse_datetime, utc_now


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


def _job_record(row: sqlite3.Row) -> JobRecord:
    return JobRecord(
        job_id=row["job_id"],
        name=row["name"],
        created_at=datetime.fromisoformat(row["created_at"]),
        heartbeat_at=parse_datetime(row["heartbeat_at"]),
        finished_at=parse_datetime(row["finished_at"]),
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
        started_at=parse_datetime(row["started_at"]),
        finished_at=parse_datetime(row["finished_at"]),
        error_type=row["error_type"],
        error_message=row["error_message"],
    )


def read_job_record(database_path: Path) -> JobRecord:
    """Read job metadata without requiring write permission."""
    connection = connect_job_database(database_path, read_only=True)
    try:
        require_job_schema(connection)
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
    connection = connect_job_database(database_path, read_only=True)
    try:
        require_job_schema(connection)
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
        self._connection = connect_job_database(database_path)
        require_job_schema(self._connection)

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
        now = utc_now()
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

    def mark_entry_running(self, entry_index: int) -> None:
        now = utc_now()
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
        now = utc_now()
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
