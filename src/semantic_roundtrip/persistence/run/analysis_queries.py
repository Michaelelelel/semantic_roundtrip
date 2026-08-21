"""Read-only rows used by the reproducible analysis layer."""

from dataclasses import dataclass
from pathlib import Path

from semantic_roundtrip.config import PredictionInputKind
from semantic_roundtrip.persistence.run.schema import (
    connect_run_database,
    require_run_schema,
)


@dataclass(frozen=True, slots=True)
class StoredPrompt:
    item_key: str
    prompt_index: int
    prompt_id: int
    sampling_seed: int
    text: str


@dataclass(frozen=True, slots=True)
class StoredImage:
    item_key: str
    prompt_index: int
    prompt_id: int
    image_seed: int
    image_id: int
    path: str
    verification_passed: bool | None
    verification_reason: str | None
    description: str | None


@dataclass(frozen=True, slots=True)
class StoredPrediction:
    image_id: int
    input_kind: PredictionInputKind
    prediction_id: int
    title: str
    confidence: float | None
    confidence_type: str | None


@dataclass(frozen=True, slots=True)
class StoredStageError:
    error_id: int
    stage: str
    item_key: str | None
    prompt_id: int | None
    image_id: int | None
    seed: int | None
    attempt: int
    error_type: str
    message: str


@dataclass(frozen=True, slots=True)
class StoredTaskTiming:
    stage: str
    status: str
    attempt: int
    started_at: str | None
    finished_at: str | None


@dataclass(frozen=True, slots=True)
class StoredRuntimeEvent:
    stage: str
    backend_alias: str
    controller: str
    model_id: str | None
    action: str
    status: str
    started_at: str
    finished_at: str | None


@dataclass(frozen=True, slots=True)
class StoredAnalysisRows:
    prompts: tuple[StoredPrompt, ...]
    images: tuple[StoredImage, ...]
    predictions: tuple[StoredPrediction, ...]
    errors: tuple[StoredStageError, ...]
    tasks: tuple[StoredTaskTiming, ...]
    runtime_events: tuple[StoredRuntimeEvent, ...]


def read_analysis_rows(database_path: Path) -> StoredAnalysisRows:
    """Read all persisted rows needed to analyze one run."""
    connection = connect_run_database(database_path, read_only=True)
    try:
        require_run_schema(connection)
        prompt_rows = connection.execute(
            """
            SELECT
                items.item_key,
                prompts.prompt_index,
                prompts.prompt_id,
                prompts.sampling_seed,
                prompts.text
            FROM prompts
            JOIN dataset_items AS items
                ON items.item_id = prompts.item_id
            ORDER BY items.item_index, prompts.prompt_index
            """
        ).fetchall()
        image_rows = connection.execute(
            """
            SELECT
                items.item_key,
                prompts.prompt_index,
                prompts.prompt_id,
                images.seed AS image_seed,
                images.image_id,
                images.path,
                verifications.passed AS verification_passed,
                verifications.reason AS verification_reason,
                image_descriptions.text AS description
            FROM images
            JOIN prompts
                ON prompts.prompt_id = images.prompt_id
            JOIN dataset_items AS items
                ON items.item_id = prompts.item_id
            LEFT JOIN verifications
                ON verifications.image_id = images.image_id
            LEFT JOIN image_descriptions
                ON image_descriptions.image_id = images.image_id
            ORDER BY items.item_index, prompts.prompt_index, images.seed
            """
        ).fetchall()
        prediction_rows = connection.execute(
            """
            SELECT
                predictions.image_id,
                predictions.input_kind,
                predictions.prediction_id,
                predictions.title,
                predictions.confidence,
                predictions.confidence_type
            FROM predictions
            ORDER BY predictions.image_id, predictions.input_kind
            """
        ).fetchall()
        error_rows = connection.execute(
            """
            SELECT
                errors.error_id,
                errors.stage,
                items.item_key,
                errors.prompt_id,
                errors.image_id,
                tasks.seed,
                errors.attempt,
                errors.error_type,
                errors.message
            FROM stage_errors AS errors
            LEFT JOIN stage_tasks AS tasks
                ON tasks.task_id = errors.task_id
            LEFT JOIN dataset_items AS items
                ON items.item_id = errors.item_id
            ORDER BY errors.error_id
            """
        ).fetchall()
        task_rows = connection.execute(
            """
            SELECT stage, status, attempt, started_at, finished_at
            FROM stage_tasks
            ORDER BY stage, task_id
            """
        ).fetchall()
        runtime_rows = connection.execute(
            """
            SELECT
                stage,
                backend_alias,
                controller,
                model_id,
                action,
                status,
                started_at,
                finished_at
            FROM runtime_events
            ORDER BY runtime_event_id
            """
        ).fetchall()
    finally:
        connection.close()

    return StoredAnalysisRows(
        prompts=tuple(
            StoredPrompt(
                item_key=row["item_key"],
                prompt_index=int(row["prompt_index"]),
                prompt_id=int(row["prompt_id"]),
                sampling_seed=int(row["sampling_seed"]),
                text=row["text"],
            )
            for row in prompt_rows
        ),
        images=tuple(
            StoredImage(
                item_key=row["item_key"],
                prompt_index=int(row["prompt_index"]),
                prompt_id=int(row["prompt_id"]),
                image_seed=int(row["image_seed"]),
                image_id=int(row["image_id"]),
                path=row["path"],
                verification_passed=(
                    None
                    if row["verification_passed"] is None
                    else bool(row["verification_passed"])
                ),
                verification_reason=row["verification_reason"],
                description=row["description"],
            )
            for row in image_rows
        ),
        predictions=tuple(
            StoredPrediction(
                image_id=int(row["image_id"]),
                input_kind=row["input_kind"],
                prediction_id=int(row["prediction_id"]),
                title=row["title"],
                confidence=(
                    None if row["confidence"] is None else float(row["confidence"])
                ),
                confidence_type=row["confidence_type"],
            )
            for row in prediction_rows
        ),
        errors=tuple(
            StoredStageError(
                error_id=int(row["error_id"]),
                stage=row["stage"],
                item_key=row["item_key"],
                prompt_id=(None if row["prompt_id"] is None else int(row["prompt_id"])),
                image_id=(None if row["image_id"] is None else int(row["image_id"])),
                seed=None if row["seed"] is None else int(row["seed"]),
                attempt=int(row["attempt"]),
                error_type=row["error_type"],
                message=row["message"],
            )
            for row in error_rows
        ),
        tasks=tuple(
            StoredTaskTiming(
                stage=row["stage"],
                status=row["status"],
                attempt=int(row["attempt"]),
                started_at=row["started_at"],
                finished_at=row["finished_at"],
            )
            for row in task_rows
        ),
        runtime_events=tuple(
            StoredRuntimeEvent(
                stage=row["stage"],
                backend_alias=row["backend_alias"],
                controller=row["controller"],
                model_id=row["model_id"],
                action=row["action"],
                status=row["status"],
                started_at=row["started_at"],
                finished_at=row["finished_at"],
            )
            for row in runtime_rows
        ),
    )
