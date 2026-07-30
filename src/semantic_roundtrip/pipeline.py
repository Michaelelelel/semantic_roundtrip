"""Provider-independent orchestration of semantic round-trip experiments."""

from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from typing import TypeVar

from semantic_roundtrip.adapters.factory import AdapterBundle
from semantic_roundtrip.config import ResolvedAppConfig, StageName
from semantic_roundtrip.config_resolution import expected_stage_outputs
from semantic_roundtrip.domain import BenchmarkItem, GeneratedPrompt
from semantic_roundtrip.evaluation import (
    CONTAINS_MATCH_METHOD,
    EXACT_MATCH_METHOD,
    apply_verification_policy,
    title_casefold_contains_match,
    title_exact_match,
)
from semantic_roundtrip.persistence.run_database import RunDatabase
from semantic_roundtrip.persistence.run_manager import RunContext
from semantic_roundtrip.persistence.run_results import ImageWorkItem
from semantic_roundtrip.persistence.run_tasks import TaskRecord
from semantic_roundtrip.prompting import PromptProfile, render_prompt_profile
from semantic_roundtrip.runtime import RuntimeSession


ResultType = TypeVar("ResultType")
StageOperation = Callable[[], None]

_STAGE_RESULT_FIELDS: dict[StageName, str] = {
    "prompt_generation": "prompts",
    "image_generation": "images",
    "verification": "verifications",
    "image_description": "image_descriptions",
    "title_guessing": "predictions",
}


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
    image_descriptions: int
    predictions: int
    evaluations: int


def _summary(database: RunDatabase, status: str) -> PipelineSummary:
    counts = database.results.counts()
    return PipelineSummary(
        status=status,
        dataset_items=counts.dataset_items,
        prompts=counts.prompts,
        images=counts.images,
        verifications=counts.verifications,
        image_descriptions=counts.image_descriptions,
        predictions=counts.predictions,
        evaluations=counts.evaluations,
    )


def _raise_if_pause_requested(database: RunDatabase) -> None:
    if database.pause_requested():
        raise PauseRequested


def _run_task(
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
        _raise_if_pause_requested(database)

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
    _raise_if_pause_requested(database)
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

    def execute() -> tuple[int, ResultType]:
        result = operation()
        return save(result), result

    return _run_task(
        execute,
        database=database,
        task=task,
        retry_limit=retry_limit,
        item_id=item_id,
        prompt_id=prompt_id,
        image_id=image_id,
    )


def _load_or_generate_prompt(
    *,
    database: RunDatabase,
    adapters: AdapterBundle,
    prompt_profile: PromptProfile,
    item: BenchmarkItem,
    item_index: int,
    item_id: int,
    prompt_index: int,
    sampling_seed: int,
    retry_limit: int,
) -> tuple[int, GeneratedPrompt]:
    _raise_if_pause_requested(database)
    task = database.tasks.get_or_create(
        task_key=f"prompt_generation:{item_index}:{prompt_index}",
        stage="prompt_generation",
        expected_outputs=1,
        item_id=item_id,
        seed=sampling_seed,
    )
    existing = database.results.get_prompt(item_id, prompt_index)

    if existing is not None:
        if task.status != "completed":
            database.tasks.mark_completed(task.task_id, 1)
        return existing

    if task.status == "completed":
        raise RuntimeError(f"Task {task.task_key} is completed but has no prompt.")

    messages = render_prompt_profile(
        prompt_profile,
        title=item.title,
        domain=item.domain,
        prompt_index=prompt_index,
    )

    def generate() -> tuple[int, GeneratedPrompt]:
        response = adapters.prompt_generator.generate_prompt(
            messages=messages,
            seed=sampling_seed,
        )
        prompt = GeneratedPrompt(index=prompt_index, text=response.text)
        prompt_id = database.results.add_prompt(
            item_id=item_id,
            prompt=prompt,
            sampling_seed=sampling_seed,
            response=response,
        )
        return prompt_id, prompt

    return _run_task(
        generate,
        database=database,
        task=task,
        retry_limit=retry_limit,
        item_id=item_id,
    )


def _image_task_suffix(image: ImageWorkItem) -> str:
    return f"{image.item_index}:{image.prompt.index}:{image.image.seed}"


def execute_prompt_generation_stage(
    *,
    config: ResolvedAppConfig,
    database: RunDatabase,
    adapters: AdapterBundle,
    prompt_profile: PromptProfile,
) -> None:
    """Generate every missing visual prompt before the next stage starts."""
    for item_index, configured_item in enumerate(config.dataset.items):
        item = BenchmarkItem(
            domain=configured_item.domain,
            title=configured_item.title,
        )
        item_id = database.results.get_or_add_dataset_item(item_index, item)
        for prompt_index in range(config.experiment.prompts_per_title):
            _load_or_generate_prompt(
                database=database,
                adapters=adapters,
                prompt_profile=prompt_profile,
                item=item,
                item_index=item_index,
                item_id=item_id,
                prompt_index=prompt_index,
                sampling_seed=config.experiment.prompt_seed + prompt_index,
                retry_limit=config.experiment.retry_limit,
            )


def execute_image_generation_stage(
    *,
    config: ResolvedAppConfig,
    database: RunDatabase,
    images_directory: Path,
    adapters: AdapterBundle,
) -> None:
    """Generate every missing image from the persisted prompts."""
    for prompt in database.results.list_prompts():
        for seed in config.experiment.image_seeds:
            task_suffix = f"{prompt.item_index}:{prompt.prompt.index}:{seed}"
            _load_or_run_single(
                database=database,
                stage="image_generation",
                task_suffix=task_suffix,
                existing=database.results.get_image(prompt.prompt_id, seed),
                operation=lambda: adapters.image_generator.generate_image(
                    prompt=prompt.prompt.text,
                    seed=seed,
                    output_directory=(images_directory / f"prompt_{prompt.prompt_id}"),
                ),
                save=lambda result: database.results.add_image(
                    prompt.prompt_id,
                    result,
                ),
                retry_limit=config.experiment.retry_limit,
                item_id=prompt.item_id,
                prompt_id=prompt.prompt_id,
                seed=seed,
            )


def execute_verification_stage(
    *,
    config: ResolvedAppConfig,
    database: RunDatabase,
    adapters: AdapterBundle,
) -> None:
    """Verify every persisted image before title guessing starts."""
    for image in database.results.list_images():
        _load_or_run_single(
            database=database,
            stage="verification",
            task_suffix=_image_task_suffix(image),
            existing=database.results.get_verification(image.image_id),
            operation=lambda: adapters.image_verifier.verify_image(
                image_path=image.image.path
            ),
            save=lambda result: database.results.add_verification(
                image.image_id,
                result,
            ),
            retry_limit=config.experiment.retry_limit,
            item_id=image.item_id,
            prompt_id=image.prompt_id,
            seed=image.image.seed,
            image_id=image.image_id,
        )


def execute_image_description_stage(
    *,
    config: ResolvedAppConfig,
) -> None:
    """Reserve the optional stage boundary implemented in Phase 4."""
    if config.stages.image_description is not None:
        raise NotImplementedError(
            "Image-description execution will be added in Phase 4."
        )


def execute_title_guessing_stage(
    *,
    config: ResolvedAppConfig,
    database: RunDatabase,
    adapters: AdapterBundle,
) -> None:
    """Guess every title directly from its persisted image."""
    if config.stages.title_guessing.input != "image":
        raise NotImplementedError(
            "Description-based title guessing will be added in Phase 4."
        )

    for image in database.results.list_images():
        _load_or_run_single(
            database=database,
            stage="title_guessing",
            task_suffix=_image_task_suffix(image),
            existing=database.results.get_prediction(image.image_id),
            operation=lambda: adapters.image_title_guesser.guess_title(
                image_path=image.image.path,
                domain=image.item.domain,
            ),
            save=lambda result: database.results.add_prediction(
                image.image_id,
                result,
                input_kind="image",
            ),
            retry_limit=config.experiment.retry_limit,
            item_id=image.item_id,
            prompt_id=image.prompt_id,
            seed=image.image.seed,
            image_id=image.image_id,
        )


def execute_evaluation_stage(
    *,
    config: ResolvedAppConfig,
    database: RunDatabase,
) -> None:
    """Evaluate every persisted prediction as an independently resumable task."""
    for image in database.results.list_images():
        _raise_if_pause_requested(database)
        verification_entry = database.results.get_verification(image.image_id)
        prediction_entry = database.results.get_prediction(image.image_id)
        if verification_entry is None or prediction_entry is None:
            raise RuntimeError(
                f"Image {image.image_id} is missing verification or prediction data."
            )

        verification_id, verification = verification_entry
        prediction_id, prediction = prediction_entry
        task = database.tasks.get_or_create(
            task_key=f"evaluation:{_image_task_suffix(image)}",
            stage="evaluation",
            expected_outputs=1,
            item_id=image.item_id,
            prompt_id=image.prompt_id,
            image_id=image.image_id,
            seed=image.image.seed,
        )
        evaluation_id = database.results.get_evaluation_id(prediction_id)
        if evaluation_id is not None:
            if task.status != "completed":
                database.tasks.mark_completed(task.task_id, 1)
            continue
        if task.status == "completed":
            raise RuntimeError(
                f"Task {task.task_key} is completed but has no evaluation."
            )

        def evaluate() -> int:
            exact_match = title_exact_match(image.item.title, prediction.title)
            contains_match = title_casefold_contains_match(
                image.item.title,
                prediction.title,
            )
            included, score = apply_verification_policy(
                title_matches=exact_match,
                verification_passed=verification.passed,
                failed_verification=config.evaluation.failed_verification,
            )
            return database.results.add_evaluation_if_missing(
                verification_id=verification_id,
                prediction_id=prediction_id,
                exact_match=exact_match,
                casefold_contains_match=contains_match,
                included=included,
                primary_score=score,
                exact_method=EXACT_MATCH_METHOD,
                contains_method=CONTAINS_MATCH_METHOD,
            )

        _run_task(
            evaluate,
            database=database,
            task=task,
            retry_limit=0,
            item_id=image.item_id,
            prompt_id=image.prompt_id,
            image_id=image.image_id,
        )


def _execute_runtime_stage(
    *,
    config: ResolvedAppConfig,
    database: RunDatabase,
    runtime_session: RuntimeSession,
    stage: StageName,
    operation: StageOperation,
) -> None:
    """Activate a model only when its stage still has missing result rows."""
    expected = expected_stage_outputs(config).get(stage)
    if expected is None:
        operation()
        return

    produced = getattr(database.results.counts(), _STAGE_RESULT_FIELDS[stage])
    if produced > expected:
        raise RuntimeError(
            f"Stage '{stage}' has {produced} outputs but only {expected} are expected."
        )
    if produced < expected:
        _raise_if_pause_requested(database)
        runtime_session.activate_stage(config, stage)
    operation()


def execute_stages(
    *,
    config: ResolvedAppConfig,
    database: RunDatabase,
    images_directory: Path,
    adapters: AdapterBundle,
    prompt_profile: PromptProfile,
    runtime_session: RuntimeSession,
) -> None:
    """Execute all missing work in complete, sequential pipeline stages."""
    _execute_runtime_stage(
        config=config,
        database=database,
        runtime_session=runtime_session,
        stage="prompt_generation",
        operation=lambda: execute_prompt_generation_stage(
            config=config,
            database=database,
            adapters=adapters,
            prompt_profile=prompt_profile,
        ),
    )
    _execute_runtime_stage(
        config=config,
        database=database,
        runtime_session=runtime_session,
        stage="image_generation",
        operation=lambda: execute_image_generation_stage(
            config=config,
            database=database,
            images_directory=images_directory,
            adapters=adapters,
        ),
    )
    _execute_runtime_stage(
        config=config,
        database=database,
        runtime_session=runtime_session,
        stage="verification",
        operation=lambda: execute_verification_stage(
            config=config,
            database=database,
            adapters=adapters,
        ),
    )
    _execute_runtime_stage(
        config=config,
        database=database,
        runtime_session=runtime_session,
        stage="image_description",
        operation=lambda: execute_image_description_stage(config=config),
    )
    _execute_runtime_stage(
        config=config,
        database=database,
        runtime_session=runtime_session,
        stage="title_guessing",
        operation=lambda: execute_title_guessing_stage(
            config=config,
            database=database,
            adapters=adapters,
        ),
    )
    runtime_session.release()
    execute_evaluation_stage(
        config=config,
        database=database,
    )


def run_pipeline(
    *,
    config: ResolvedAppConfig,
    run_context: RunContext,
    database_path: Path,
    images_directory: Path,
    adapters: AdapterBundle,
    prompt_profile: PromptProfile,
    resume: bool = False,
) -> PipelineSummary:
    """Run a new experiment or continue a paused, interrupted, or failed run."""
    with RunDatabase(database_path, run_context) as database:
        runtime_session = RuntimeSession(database)
        try:
            if resume:
                database.clear_pause_request()
            database.update_status("running")
            try:
                execute_stages(
                    config=config,
                    database=database,
                    images_directory=images_directory,
                    adapters=adapters,
                    prompt_profile=prompt_profile,
                    runtime_session=runtime_session,
                )
            finally:
                runtime_session.release()
        except PauseRequested:
            database.update_status("paused")
            return _summary(database, "paused")
        except KeyboardInterrupt:
            database.tasks.reset_running_tasks()
            database.update_status("interrupted")
            raise
        except Exception:
            database.update_status("failed")
            raise

        database.update_status("completed")
        return _summary(database, "completed")
