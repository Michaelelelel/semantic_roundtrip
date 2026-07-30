"""Run lifecycle, progress queries, and the writable database session."""

from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from types import TracebackType
from typing import Literal

from semantic_roundtrip.persistence.run_manager import RunContext
from semantic_roundtrip.persistence.run_results import RunResultStore
from semantic_roundtrip.persistence.run_schema import (
    connect_run_database,
    database_path_for_run,
    require_run_schema,
)
from semantic_roundtrip.persistence.run_tasks import RunTaskStore
from semantic_roundtrip.persistence.runtime_events import RuntimeEventStore
from semantic_roundtrip.persistence.sqlite import parse_datetime, utc_now


RunStatus = Literal[
    "created",
    "running",
    "pausing",
    "paused",
    "completed",
    "failed",
    "interrupted",
]


@dataclass(frozen=True, slots=True)
class RunRecord:
    run_id: str
    name: str
    created_at: datetime
    started_at: datetime | None
    status: str
    pause_requested: bool
    heartbeat_at: datetime | None
    finished_at: datetime | None


@dataclass(frozen=True, slots=True)
class StageProgress:
    stage: str
    pending: int
    running: int
    completed: int
    failed: int
    produced_outputs: int


def read_run_record(database_path: Path) -> RunRecord:
    """Read the single run metadata record."""
    connection = connect_run_database(database_path, read_only=True)
    try:
        require_run_schema(connection)
        row = connection.execute("SELECT * FROM run_metadata").fetchone()
        if row is None:
            raise ValueError(f"No run metadata found in {database_path}")
        return RunRecord(
            run_id=row["run_id"],
            name=row["name"],
            created_at=datetime.fromisoformat(row["created_at"]),
            started_at=parse_datetime(row["started_at"]),
            status=row["status"],
            pause_requested=bool(row["pause_requested"]),
            heartbeat_at=parse_datetime(row["heartbeat_at"]),
            finished_at=parse_datetime(row["finished_at"]),
        )
    finally:
        connection.close()


def load_run_context(run_directory: Path) -> RunContext:
    """Reconstruct a run context from an existing schema-v5 database."""
    record = read_run_record(database_path_for_run(run_directory))
    return RunContext(
        run_id=record.run_id,
        directory=run_directory,
        created_at=record.created_at,
    )


def read_stage_progress(database_path: Path) -> list[StageProgress]:
    """Aggregate task progress for status displays."""
    connection = connect_run_database(database_path, read_only=True)
    try:
        require_run_schema(connection)
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
    connection = connect_run_database(database_path)
    try:
        require_run_schema(connection)
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
                    (utc_now(),),
                )
        elif status not in {"pausing", "paused"}:
            raise ValueError(f"Cannot pause a run with status '{status}'.")
    finally:
        connection.close()

    return read_run_record(database_path)


class RunDatabase:
    """Writable lifecycle, task, and result stores for one experiment run."""

    def __init__(self, database_path: Path, run_context: RunContext) -> None:
        self._run_context = run_context
        self._connection = connect_run_database(database_path)
        require_run_schema(self._connection)
        self.results = RunResultStore(self._connection, run_context)
        self.tasks = RunTaskStore(self._connection, run_context)
        self.runtime_events = RuntimeEventStore(self._connection, run_context)

    def __enter__(self) -> "RunDatabase":
        return self

    def __exit__(
        self,
        exception_type: type[BaseException] | None,
        exception: BaseException | None,
        traceback: TracebackType | None,
    ) -> None:
        self._connection.close()

    def update_status(self, status: RunStatus) -> None:
        """Update lifecycle state and heartbeat."""
        now = utc_now()
        finished_at = now if status in {"completed", "failed", "interrupted"} else None
        with self._connection:
            self._connection.execute(
                """
                UPDATE run_metadata
                SET status = ?,
                    started_at = CASE
                        WHEN ? = 'running' THEN COALESCE(started_at, ?)
                        ELSE started_at
                    END,
                    finished_at = ?,
                    heartbeat_at = ?
                WHERE run_id = ?
                """,
                (
                    status,
                    status,
                    now,
                    finished_at,
                    now,
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
                (utc_now(), self._run_context.run_id),
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
