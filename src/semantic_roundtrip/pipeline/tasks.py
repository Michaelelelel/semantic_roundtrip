"""Resumable adapter-task execution shared by pipeline stages."""

from collections.abc import Callable

from semantic_roundtrip.adapters.errors import AdapterError
from semantic_roundtrip.persistence.run.database import RunDatabase
from semantic_roundtrip.persistence.run.tasks import TaskRecord


class PauseRequested(Exception):
    """Stop at a safe boundary before starting another adapter call."""


def raise_if_pause_requested(database: RunDatabase) -> None:
    """Stop before another adapter call when a cooperative pause was requested."""
    if database.pause_requested():
        raise PauseRequested


def run_task[ResultType](
    operation: Callable[[], ResultType],
    *,
    database: RunDatabase,
    task: TaskRecord,
    retry_limit: int,
    item_id: int | None = None,
    prompt_id: int | None = None,
    image_id: int | None = None,
) -> ResultType:
    """Run one adapter task, recording attempts and provider errors."""
    for retry in range(retry_limit + 1):
        raise_if_pause_requested(database)

        attempt = database.tasks.mark_running(task.task_id)
        try:
            result = operation()
        except Exception as error:
            raw_response = getattr(error, "raw_response", None)
            database.tasks.add_error(
                task_id=task.task_id,
                stage=task.stage,
                attempt=attempt,
                error=error,
                item_id=item_id,
                prompt_id=prompt_id,
                image_id=image_id,
                raw_response=(raw_response if isinstance(raw_response, str) else None),
            )
            if retry == retry_limit:
                database.tasks.mark_failed(task.task_id)
                raise
        else:
            database.tasks.mark_completed(task.task_id, 1)
            return result

    raise RuntimeError("Task retry loop ended unexpectedly.")


def load_or_run_single[ResultType](
    *,
    database: RunDatabase,
    stage: str,
    task_suffix: str,
    existing: tuple[int, ResultType] | None,
    operation: Callable[[], ResultType],
    save: Callable[[ResultType], int],
    retry_limit: int,
    item_id: int,
    prompt_id: int,
    seed: int,
    image_id: int | None = None,
) -> tuple[int, ResultType] | None:
    """Reuse a result, skip an exhausted task, or execute and persist it."""
    raise_if_pause_requested(database)
    task = database.tasks.get_or_create(
        task_key=f"{stage}:{task_suffix}",
        stage=stage,
        expected_outputs=1,
        item_id=item_id,
        prompt_id=prompt_id,
        image_id=image_id,
        seed=seed,
    )

    if existing is not None:
        if task.status != "completed":
            database.tasks.mark_completed(task.task_id, 1)
        return existing

    if task.status == "completed":
        raise RuntimeError(f"Task {task.task_key} is completed but has no result.")
    if task.status == "failed":
        return None

    def execute() -> tuple[int, ResultType]:
        result = operation()
        return save(result), result

    try:
        return run_task(
            execute,
            database=database,
            task=task,
            retry_limit=retry_limit,
            item_id=item_id,
            prompt_id=prompt_id,
            image_id=image_id,
        )
    except AdapterError:
        return None
