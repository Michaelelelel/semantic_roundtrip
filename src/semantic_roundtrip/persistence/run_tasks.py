"""Persistence for pipeline task state, retries, and errors."""

import sqlite3
from dataclasses import dataclass

from semantic_roundtrip.persistence.run_manager import RunContext
from semantic_roundtrip.persistence.sqlite import utc_now


@dataclass(frozen=True, slots=True)
class TaskRecord:
    task_id: int
    task_key: str
    stage: str
    status: str
    attempt: int
    expected_outputs: int
    completed_outputs: int


class RunTaskStore:
    """Read and update resumable stage tasks for one experiment run."""

    def __init__(
        self,
        connection: sqlite3.Connection,
        run_context: RunContext,
    ) -> None:
        self._connection = connection
        self._run_context = run_context

    def _insert(self, statement: str, parameters: tuple[object, ...]) -> int:
        with self._connection:
            cursor = self._connection.execute(statement, parameters)
        return int(cursor.lastrowid)

    def get_or_create(
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
        now = utc_now()
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

    def get(self, task_id: int) -> TaskRecord:
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

    def mark_running(self, task_id: int) -> int:
        now = utc_now()
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
        return self.get(task_id).attempt

    def mark_completed(self, task_id: int, completed_outputs: int) -> None:
        now = utc_now()
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

    def mark_failed(self, task_id: int) -> None:
        now = utc_now()
        with self._connection:
            self._connection.execute(
                """
                UPDATE stage_tasks
                SET status = 'failed', updated_at = ?, finished_at = ?
                WHERE task_id = ?
                """,
                (now, now, task_id),
            )

    def add_error(
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
                utc_now(),
            ),
        )
