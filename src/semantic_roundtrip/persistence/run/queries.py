"""Typed read-only queries for persisted experiment runs."""

from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

from semantic_roundtrip.persistence.run.schema import (
    connect_run_database,
    require_run_schema,
)
from semantic_roundtrip.persistence.sqlite import parse_datetime


@dataclass(frozen=True, slots=True)
class RunRecord:
    """Persisted lifecycle metadata for one run."""

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
    """Aggregated persisted task progress for one stage."""

    stage: str
    pending: int
    running: int
    completed: int
    failed: int
    produced_outputs: int
    imported_tasks: int


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
                SUM(completed_outputs) AS produced_outputs,
                SUM(CASE WHEN execution_origin = 'imported' THEN 1 ELSE 0 END)
                    AS imported_tasks
            FROM stage_tasks
            GROUP BY stage
            ORDER BY stage
            """
        ).fetchall()
    finally:
        connection.close()

    return [
        StageProgress(
            stage=row["stage"],
            pending=int(row["pending"]),
            running=int(row["running"]),
            completed=int(row["completed"]),
            failed=int(row["failed"]),
            produced_outputs=int(row["produced_outputs"]),
            imported_tasks=int(row["imported_tasks"]),
        )
        for row in rows
    ]


def read_completed_task_durations(
    database_path: Path,
    stage: str,
) -> list[float]:
    """Read clean first-attempt task durations for one stage."""
    connection = connect_run_database(database_path, read_only=True)
    try:
        require_run_schema(connection)
        rows = connection.execute(
            """
            SELECT started_at, finished_at
            FROM stage_tasks
            WHERE stage = ?
              AND status = 'completed'
              AND execution_origin = 'local'
              AND attempt = 1
              AND started_at IS NOT NULL
              AND finished_at IS NOT NULL
            """,
            (stage,),
        ).fetchall()
    finally:
        connection.close()

    durations: list[float] = []
    for row in rows:
        started_at = parse_datetime(row["started_at"])
        finished_at = parse_datetime(row["finished_at"])
        if started_at is None or finished_at is None:
            continue
        duration = (finished_at - started_at).total_seconds()
        if duration >= 0:
            durations.append(duration)
    return durations


def read_active_runtime_action(database_path: Path) -> str | None:
    """Read the newest unfinished model-runtime action, if one exists."""
    connection = connect_run_database(database_path, read_only=True)
    try:
        require_run_schema(connection)
        row = connection.execute(
            """
            SELECT action
            FROM runtime_events
            WHERE status = 'started' AND execution_origin = 'local'
            ORDER BY runtime_event_id DESC
            LIMIT 1
            """
        ).fetchone()
    finally:
        connection.close()
    return None if row is None else str(row["action"])


def read_stage_runtime_model(database_path: Path, stage: str) -> str | None:
    """Read the model identity persisted for one local or imported stage."""
    connection = connect_run_database(database_path, read_only=True)
    try:
        require_run_schema(connection)
        row = connection.execute(
            """
            SELECT model_id, backend_alias
            FROM runtime_events
            WHERE stage = ?
              AND action IN ('load', 'reuse')
            ORDER BY runtime_event_id DESC
            LIMIT 1
            """,
            (stage,),
        ).fetchone()
    finally:
        connection.close()
    if row is None:
        return None
    model_id = row["model_id"]
    return str(row["backend_alias"] if model_id is None else model_id)


def read_latest_stage_error(database_path: Path) -> str | None:
    """Read the newest persisted adapter error, if one exists."""
    connection = connect_run_database(database_path, read_only=True)
    try:
        require_run_schema(connection)
        row = connection.execute(
            """
            SELECT error_type, message
            FROM stage_errors
            ORDER BY error_id DESC
            LIMIT 1
            """
        ).fetchone()
    finally:
        connection.close()
    if row is None:
        return None
    return f"{row['error_type']}: {row['message']}"
