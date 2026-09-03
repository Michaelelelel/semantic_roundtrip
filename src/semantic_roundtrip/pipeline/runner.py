"""Top-level lifecycle and stage ordering for one experiment run."""

from collections.abc import Callable
from contextlib import suppress
from pathlib import Path

from semantic_roundtrip.adapters.factory import AdapterBundle
from semantic_roundtrip.config import ResolvedAppConfig, StageName
from semantic_roundtrip.config_resolution import (
    configured_image_verification_policies,
    get_stage_config,
)
from semantic_roundtrip.inheritance.materialize import materialize_inheritance
from semantic_roundtrip.persistence.run.database import RunDatabase
from semantic_roundtrip.persistence.run.manager import RunContext
from semantic_roundtrip.pipeline.models import PipelineSummary
from semantic_roundtrip.pipeline.stages import (
    execute_description_title_guessing_stage,
    execute_direct_title_guessing_stage,
    execute_illustratability_rating_stage,
    execute_image_description_stage,
    execute_image_generation_stage,
    execute_prompt_generation_stage,
    execute_verification_stage,
)
from semantic_roundtrip.pipeline.tasks import PauseRequested, raise_if_pause_requested
from semantic_roundtrip.prompting import PromptProfile
from semantic_roundtrip.runtime import RuntimeSession

StageOperation = Callable[[], None]


def _summary(database: RunDatabase, status: str) -> PipelineSummary:
    counts = database.results.counts()
    return PipelineSummary(
        status=status,
        dataset_items=counts.dataset_items,
        illustratability_ratings=counts.illustratability_ratings,
        prompts=counts.prompts,
        images=counts.images,
        prompt_verifications=counts.prompt_verifications,
        strict_image_verifications=counts.strict_image_verifications,
        title_aware_image_verifications=counts.title_aware_image_verifications,
        image_descriptions=counts.image_descriptions,
        predictions=counts.predictions,
        failed_tasks=database.tasks.count_failed(),
    )


def _execute_runtime_stage(
    *,
    config: ResolvedAppConfig,
    database: RunDatabase,
    runtime_session: RuntimeSession,
    stage: StageName,
    operation: StageOperation,
) -> None:
    """Activate a model only while this run has actionable local work."""
    counts = database.results.counts()
    if stage == "illustratability_rating":
        work_items = len(config.dataset.items)
    elif stage == "prompt_generation":
        work_items = len(config.dataset.items) * len(config.experiment.prompt_seeds)
    elif stage == "image_generation":
        work_items = counts.prompts * len(config.experiment.image_seeds)
    elif stage == "title_guessing_from_description":
        work_items = counts.image_descriptions
    elif stage == "verification":
        verification = config.stages.verification
        assert verification is not None
        work_items = (
            counts.prompts if verification.prompt is not None else 0
        ) + counts.images * len(configured_image_verification_policies(config))
    else:
        work_items = counts.images

    terminal = database.tasks.count_terminal_local(stage)
    if terminal > work_items:
        raise RuntimeError(
            f"Stage '{stage}' has {terminal} terminal local tasks but only "
            f"{work_items} source artifacts."
        )
    if terminal < work_items:
        raise_if_pause_requested(database)
        runtime_session.activate_stage(config, stage)
    operation()


def execute_stages(
    *,
    config: ResolvedAppConfig,
    database: RunDatabase,
    images_directory: Path,
    adapters: AdapterBundle,
    illustratability_profile: PromptProfile | None,
    prompt_profile: PromptProfile | None,
    runtime_session: RuntimeSession,
) -> None:
    """Execute all missing model-backed work in sequential pipeline stages."""
    if get_stage_config(config, "illustratability_rating") is not None:
        if illustratability_profile is None:
            raise RuntimeError("Illustratability rating has no loaded prompt profile.")
        _execute_runtime_stage(
            config=config,
            database=database,
            runtime_session=runtime_session,
            stage="illustratability_rating",
            operation=lambda: execute_illustratability_rating_stage(
                config=config,
                database=database,
                adapters=adapters,
                prompt_profile=illustratability_profile,
            ),
        )
    if get_stage_config(config, "prompt_generation") is not None:
        if prompt_profile is None:
            raise RuntimeError("Prompt generation has no loaded prompt profile.")
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
    if get_stage_config(config, "image_generation") is not None:
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
    if get_stage_config(config, "verification") is not None:
        if configured_image_verification_policies(config):
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
        else:
            execute_verification_stage(
                config=config,
                database=database,
                adapters=adapters,
            )
    if get_stage_config(config, "title_guessing_direct") is not None:
        _execute_runtime_stage(
            config=config,
            database=database,
            runtime_session=runtime_session,
            stage="title_guessing_direct",
            operation=lambda: execute_direct_title_guessing_stage(
                config=config,
                database=database,
                adapters=adapters,
            ),
        )
    if get_stage_config(config, "image_description") is not None:
        _execute_runtime_stage(
            config=config,
            database=database,
            runtime_session=runtime_session,
            stage="image_description",
            operation=lambda: execute_image_description_stage(
                config=config,
                database=database,
                adapters=adapters,
            ),
        )
    if get_stage_config(config, "title_guessing_from_description") is not None:
        _execute_runtime_stage(
            config=config,
            database=database,
            runtime_session=runtime_session,
            stage="title_guessing_from_description",
            operation=lambda: execute_description_title_guessing_stage(
                config=config,
                database=database,
                adapters=adapters,
            ),
        )


def run_pipeline(
    *,
    config: ResolvedAppConfig,
    run_context: RunContext,
    database_path: Path,
    images_directory: Path,
    adapters: AdapterBundle,
    illustratability_profile: PromptProfile | None,
    prompt_profile: PromptProfile | None,
    resume: bool = False,
) -> PipelineSummary:
    """Run a new experiment or continue a paused, interrupted, or failed run."""
    with RunDatabase(database_path, run_context) as database:
        runtime_session = RuntimeSession(database)
        try:
            if resume:
                database.clear_pause_request()
            database.update_status("running")
            materialize_inheritance(config, run_context.directory)
            try:
                execute_stages(
                    config=config,
                    database=database,
                    images_directory=images_directory,
                    adapters=adapters,
                    illustratability_profile=illustratability_profile,
                    prompt_profile=prompt_profile,
                    runtime_session=runtime_session,
                )
            except BaseException:
                # release() persists normal cleanup failures in runtime_events.
                with suppress(Exception):
                    runtime_session.release()
                raise

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
