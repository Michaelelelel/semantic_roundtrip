"""Provider-independent orchestration of semantic round-trip experiments."""

from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from typing import TypeVar

from semantic_roundtrip.adapters.factory import AdapterBundle
from semantic_roundtrip.config import AppConfig
from semantic_roundtrip.domain import BenchmarkItem, GeneratedPrompt
from semantic_roundtrip.evaluation import (
    EVALUATION_METHOD,
    apply_verification_policy,
    title_exact_match,
)
from semantic_roundtrip.persistence.database import RunDatabase, TaskRecord
from semantic_roundtrip.persistence.run_manager import RunContext


ResultType = TypeVar("ResultType")


class PauseRequested(Exception):
    """Stop at a safe boundary before starting another adapter call."""


@dataclass(frozen=True, slots=True)
class PipelineSummary:
    """Current database counts and final status of one pipeline invocation."""

    status: str
    dataset_items: int
    prompts: int
    images: int
    verifications: int
    predictions: int
    evaluations: int


def _summary(database: RunDatabase, status: str) -> PipelineSummary:
    counts = database.result_counts()
    return PipelineSummary(
        status=status,
        dataset_items=counts.dataset_items,
        prompts=counts.prompts,
        images=counts.images,
        verifications=counts.verifications,
        predictions=counts.predictions,
        evaluations=counts.evaluations,
    )


def _run_task(
    operation: Callable[[int], ResultType],
    *,
    database: RunDatabase,
    task: TaskRecord,
    retry_limit: int,
    output_count: Callable[[ResultType], int],
    item_id: int | None = None,
    prompt_id: int | None = None,
    image_id: int | None = None,
) -> ResultType:
    """Run one adapter task, recording attempts and provider errors."""
    for retry in range(retry_limit + 1):
        if database.pause_requested():
            raise PauseRequested

        attempt = database.mark_task_running(task.task_id)
        try:
            result = operation(attempt)
        except Exception as error:
            raw_response = getattr(error, "raw_response", None)
            database.add_stage_error(
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
                database.mark_task_failed(task.task_id)
                raise
        else:
            database.mark_task_completed(task.task_id, output_count(result))
            return result

    raise RuntimeError("Task retry loop ended unexpectedly.")


def _load_or_run_single(
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
) -> tuple[int, ResultType]:
    """Reuse one stored result or execute and persist its adapter task."""
    task = database.get_or_create_task(
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
            database.mark_task_completed(task.task_id, 1)
        return existing

    if task.status == "completed":
        raise RuntimeError(f"Task {task.task_key} is completed but has no result.")

    def execute(_: int) -> tuple[int, ResultType]:
        result = operation()
        return save(result), result

    return _run_task(
        execute,
        database=database,
        task=task,
        retry_limit=retry_limit,
        output_count=lambda _: 1,
        item_id=item_id,
        prompt_id=prompt_id,
        image_id=image_id,
    )


def _load_or_generate_prompts(
    *,
    database: RunDatabase,
    adapters: AdapterBundle,
    config: AppConfig,
    item: BenchmarkItem,
    item_index: int,
    item_id: int,
) -> list[tuple[int, GeneratedPrompt]]:
    task = database.get_or_create_task(
        task_key=f"prompt_generation:{item_index}",
        stage="prompt_generation",
        expected_outputs=config.experiment.prompts_per_title,
        item_id=item_id,
    )
    prompts = database.get_prompts(item_id)

    if database.has_prompt_batch(item_id):
        if task.status != "completed":
            database.mark_task_completed(task.task_id, len(prompts))
        return prompts

    if task.status == "completed":
        raise RuntimeError(f"Task {task.task_key} is completed but has no batch.")

    def generate(attempt: int) -> list[tuple[int, GeneratedPrompt]]:
        batch = adapters.prompt_generator.generate_prompts(
            title=item.title,
            domain=item.domain,
            count=config.experiment.prompts_per_title,
        )
        return database.add_prompt_batch(item_id, batch, attempt)

    return _run_task(
        generate,
        database=database,
        task=task,
        retry_limit=config.experiment.retry_limit,
        output_count=len,
        item_id=item_id,
    )


def _execute(
    *,
    config: AppConfig,
    database: RunDatabase,
    images_directory: Path,
    adapters: AdapterBundle,
) -> None:
    """Execute all missing work in dataset, prompt, and seed order."""
    retry_limit = config.experiment.retry_limit

    for item_index, configured_item in enumerate(config.dataset.items):
        item = BenchmarkItem(
            domain=configured_item.domain,
            title=configured_item.title,
        )
        item_id = database.get_or_add_dataset_item(item_index, item)
        prompts = _load_or_generate_prompts(
            database=database,
            adapters=adapters,
            config=config,
            item=item,
            item_index=item_index,
            item_id=item_id,
        )

        for prompt_id, prompt in prompts:
            for seed in config.experiment.seeds:
                task_suffix = f"{item_index}:{prompt.index}:{seed}"

                image_id, image = _load_or_run_single(
                    database=database,
                    stage="image_generation",
                    task_suffix=task_suffix,
                    existing=database.get_image(prompt_id, seed),
                    operation=lambda: adapters.image_generator.generate_image(
                        prompt=prompt.text,
                        seed=seed,
                        output_directory=images_directory / f"prompt_{prompt_id}",
                    ),
                    save=lambda result: database.add_image(prompt_id, result),
                    retry_limit=retry_limit,
                    item_id=item_id,
                    prompt_id=prompt_id,
                    seed=seed,
                )

                verification_id, verification = _load_or_run_single(
                    database=database,
                    stage="verification",
                    task_suffix=task_suffix,
                    existing=database.get_verification(image_id),
                    operation=lambda: adapters.image_verifier.verify_image(
                        image_path=image.path
                    ),
                    save=lambda result: database.add_verification(image_id, result),
                    retry_limit=retry_limit,
                    item_id=item_id,
                    prompt_id=prompt_id,
                    seed=seed,
                    image_id=image_id,
                )

                prediction_id, prediction = _load_or_run_single(
                    database=database,
                    stage="title_guessing",
                    task_suffix=task_suffix,
                    existing=database.get_prediction(image_id),
                    operation=lambda: adapters.title_guesser.guess_title(
                        image_path=image.path,
                        domain=item.domain,
                    ),
                    save=lambda result: database.add_prediction(image_id, result),
                    retry_limit=retry_limit,
                    item_id=item_id,
                    prompt_id=prompt_id,
                    seed=seed,
                    image_id=image_id,
                )

                title_matches = title_exact_match(item.title, prediction.title)
                included, score = apply_verification_policy(
                    title_matches=title_matches,
                    verification_passed=verification.passed,
                    failed_verification=config.evaluation.failed_verification,
                )
                database.add_evaluation_if_missing(
                    verification_id=verification_id,
                    prediction_id=prediction_id,
                    title_exact_match=title_matches,
                    included=included,
                    score=score,
                    method=EVALUATION_METHOD,
                )


def run_pipeline(
    *,
    config: AppConfig,
    run_context: RunContext,
    database_path: Path,
    images_directory: Path,
    adapters: AdapterBundle,
    resume: bool = False,
) -> PipelineSummary:
    """Run a new experiment or continue a paused, interrupted, or failed run."""
    with RunDatabase(database_path, run_context) as database:
        if resume:
            database.clear_pause_request()
        database.update_run_status("running")

        try:
            _execute(
                config=config,
                database=database,
                images_directory=images_directory,
                adapters=adapters,
            )
        except PauseRequested:
            database.update_run_status("paused")
            return _summary(database, "paused")
        except KeyboardInterrupt:
            database.update_run_status("interrupted")
            raise
        except Exception:
            database.update_run_status("failed")
            raise

        database.update_run_status("completed")
        return _summary(database, "completed")
