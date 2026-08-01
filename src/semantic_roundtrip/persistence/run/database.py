"""Writable lifecycle session for one persisted experiment run."""

from pathlib import Path
from types import TracebackType
from typing import Literal

from semantic_roundtrip.persistence.run.manager import RunContext
from semantic_roundtrip.persistence.run.queries import RunRecord, read_run_record
from semantic_roundtrip.persistence.run.results import RunResultStore
from semantic_roundtrip.persistence.run.schema import (
    connect_run_database,
    database_path_for_run,
    require_run_schema,
)
from semantic_roundtrip.persistence.run.runtime_events import RuntimeEventStore
from semantic_roundtrip.persistence.run.tasks import RunTaskStore
from semantic_roundtrip.persistence.sqlite import utc_now


RunStatus = Literal[
    "created",
    "running",
    "pausing",
    "paused",
    "completed",
    "failed",
    "interrupted",
]


def load_run_context(run_directory: Path) -> RunContext:
    """Reconstruct a run context from an existing schema-v5 database."""
    record = read_run_record(database_path_for_run(run_directory))
    return RunContext(
        run_id=record.run_id,
        directory=run_directory,
        created_at=record.created_at,
    )


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
