"""Persistence primitives for model load, reuse, and unload events."""

import sqlite3
from typing import Literal

from semantic_roundtrip.persistence.run_manager import RunContext
from semantic_roundtrip.persistence.sqlite import utc_now


RuntimeAction = Literal["load", "reuse", "unload"]


class RuntimeEventStore:
    """Record runtime lifecycle transitions for one experiment run."""

    def __init__(
        self,
        connection: sqlite3.Connection,
        run_context: RunContext,
    ) -> None:
        self._connection = connection
        self._run_context = run_context

    def begin(
        self,
        *,
        stage: str,
        backend_alias: str,
        controller: str,
        resource_group: str,
        model_id: str | None,
        action: RuntimeAction,
    ) -> int:
        """Create one in-progress runtime event."""
        now = utc_now()
        with self._connection:
            cursor = self._connection.execute(
                """
                INSERT INTO runtime_events (
                    run_id,
                    stage,
                    backend_alias,
                    controller,
                    resource_group,
                    model_id,
                    action,
                    status,
                    started_at
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, 'started', ?)
                """,
                (
                    self._run_context.run_id,
                    stage,
                    backend_alias,
                    controller,
                    resource_group,
                    model_id,
                    action,
                    now,
                ),
            )
            self._connection.execute(
                """
                UPDATE run_metadata
                SET heartbeat_at = ?
                WHERE run_id = ?
                """,
                (now, self._run_context.run_id),
            )
        return int(cursor.lastrowid)

    def complete(self, runtime_event_id: int) -> None:
        """Mark one runtime operation as successfully completed."""
        self._finish(
            runtime_event_id,
            status="completed",
            error=None,
        )

    def fail(self, runtime_event_id: int, error: BaseException) -> None:
        """Mark one runtime operation as failed."""
        self._finish(
            runtime_event_id,
            status="failed",
            error=error,
        )

    def _finish(
        self,
        runtime_event_id: int,
        *,
        status: Literal["completed", "failed"],
        error: BaseException | None,
    ) -> None:
        now = utc_now()
        with self._connection:
            cursor = self._connection.execute(
                """
                UPDATE runtime_events
                SET status = ?,
                    finished_at = ?,
                    error_type = ?,
                    error_message = ?
                WHERE runtime_event_id = ? AND status = 'started'
                """,
                (
                    status,
                    now,
                    None if error is None else type(error).__name__,
                    None if error is None else str(error),
                    runtime_event_id,
                ),
            )
            self._connection.execute(
                """
                UPDATE run_metadata
                SET heartbeat_at = ?
                WHERE run_id = ?
                """,
                (now, self._run_context.run_id),
            )
        if cursor.rowcount != 1:
            raise ValueError(
                f"Runtime event {runtime_event_id} is missing or already finished."
            )
