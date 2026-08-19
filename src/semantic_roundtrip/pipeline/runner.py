"""Top-level lifecycle and stage ordering for one experiment run."""

from collections.abc import Callable
from contextlib import suppress
from pathlib import Path

from semantic_roundtrip.adapters.factory import AdapterBundle
from semantic_roundtrip.config import ResolvedAppConfig, StageName
from semantic_roundtrip.config_resolution import expected_stage_outputs
from semantic_roundtrip.persistence.run.database import RunDatabase
from semantic_roundtrip.persistence.run.manager import RunContext
from semantic_roundtrip.pipeline.models import PipelineSummary
from semantic_roundtrip.pipeline.stages import (
    execute_description_title_guessing_stage,
    execute_direct_title_guessing_stage,
    execute_evaluation_stage,
    execute_image_description_stage,
    execute_image_generation_stage,
    execute_prompt_generation_stage,
    execute_verification_stage,
)
from semantic_roundtrip.pipeline.tasks import PauseRequested, raise_if_pause_requested
from semantic_roundtrip.prompting import PromptProfile
from semantic_roundtrip.runtime import RuntimeSession

StageOperation = Callable[[], None]

_STAGE_RESULT_FIELDS: dict[StageName, str] = {
    "prompt_generation": "prompts",
    "image_generation": "images",
    "verification": "verifications",
    "title_guessing_direct": "direct_predictions",
    "image_description": "image_descriptions",
    "title_guessing_from_description": "description_predictions",
}


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
        raise_if_pause_requested(database)
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
    """Execute all missing model-backed work in sequential pipeline stages."""
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
        stage="title_guessing_direct",
        operation=lambda: execute_direct_title_guessing_stage(
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
        operation=lambda: execute_image_description_stage(
            config=config,
            database=database,
            adapters=adapters,
        ),
    )
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
            except BaseException:
                # release() persists normal cleanup failures in runtime_events.
                with suppress(Exception):
                    runtime_session.release()
                raise

            runtime_session.release()
            execute_evaluation_stage(
                config=config,
                database=database,
            )
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
