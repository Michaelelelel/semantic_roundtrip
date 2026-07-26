"""Creation and execution of one independently resumable experiment run."""

from dataclasses import dataclass
from pathlib import Path

from semantic_roundtrip.adapters.factory import AdapterBundle, create_adapters
from semantic_roundtrip.config import ResolvedAppConfig
from semantic_roundtrip.config_resolution import (
    load_effective_config,
    load_input_config,
)
from semantic_roundtrip.persistence.config_snapshot import (
    EFFECTIVE_CONFIG_FILENAME,
    create_effective_config_snapshot,
    create_input_config_snapshot,
    create_prompt_snapshots,
    use_prompt_snapshots,
)
from semantic_roundtrip.persistence.run_database import (
    load_run_context,
    read_run_record,
)
from semantic_roundtrip.persistence.manifest import create_manifest
from semantic_roundtrip.persistence.run_manager import RunContext, create_run
from semantic_roundtrip.persistence.run_schema import (
    database_path_for_run,
    initialize_database,
)
from semantic_roundtrip.pipeline import PipelineSummary, run_pipeline
from semantic_roundtrip.prompting import PromptProfile, load_prompt_profile


RESUMABLE_RUN_STATUSES = frozenset({"created", "paused", "failed", "interrupted"})


@dataclass(frozen=True, slots=True)
class PreparedExperiment:
    """Everything required to execute a newly created experiment run."""

    config: ResolvedAppConfig
    run_context: RunContext
    database_path: Path
    manifest_path: Path
    images_directory: Path
    adapters: AdapterBundle
    prompt_profile: PromptProfile


def prepare_experiment(
    *,
    config: ResolvedAppConfig,
    input_config_path: Path,
    output_directory: Path | None = None,
) -> PreparedExperiment:
    """Validate dependencies and create all static artifacts for a new run."""
    if output_directory is not None:
        run_config = config.run.model_copy(
            update={"output_directory": output_directory}
        )
        config = config.model_copy(update={"run": run_config})

    loaded_prompt_profile = load_prompt_profile(
        config.stages.prompt_generation.prompt_profile
    )
    adapters = create_adapters(config)
    run_context = create_run(
        config.run.output_directory,
        config.run.name,
    )

    input_snapshot_path = create_input_config_snapshot(
        input_config_path,
        run_context.directory,
    )
    effective_config_path = create_effective_config_snapshot(
        config,
        run_context.directory,
    )
    prompt_paths = create_prompt_snapshots(
        config,
        loaded_prompt_profile,
        run_context.directory,
    )
    images_directory = run_context.directory / "images"
    images_directory.mkdir()
    database_path = initialize_database(
        run_context,
        config.run.name,
        input_snapshot_path,
        effective_config_path,
    )
    manifest_path = create_manifest(
        run_context,
        config.run.name,
        input_snapshot_path,
        effective_config_path,
        database_path,
        images_directory,
        prompt_paths,
    )

    return PreparedExperiment(
        config=config,
        run_context=run_context,
        database_path=database_path,
        manifest_path=manifest_path,
        images_directory=images_directory,
        adapters=adapters,
        prompt_profile=loaded_prompt_profile.profile,
    )


def prepare_experiment_from_file(
    config_path: Path,
    *,
    output_directory: Path | None = None,
) -> PreparedExperiment:
    """Resolve an input configuration and prepare its new run."""
    return prepare_experiment(
        config=load_input_config(config_path),
        input_config_path=config_path,
        output_directory=output_directory,
    )


def execute_prepared_experiment(
    prepared: PreparedExperiment,
) -> PipelineSummary:
    """Execute a newly prepared experiment."""
    return run_pipeline(
        config=prepared.config,
        run_context=prepared.run_context,
        database_path=prepared.database_path,
        images_directory=prepared.images_directory,
        adapters=prepared.adapters,
        prompt_profile=prepared.prompt_profile,
    )


def resume_experiment(
    run_directory: Path,
    *,
    allowed_statuses: frozenset[str] = RESUMABLE_RUN_STATUSES,
) -> PipelineSummary:
    """Resume an existing experiment from its effective snapshots."""
    database_path = database_path_for_run(run_directory)
    record = read_run_record(database_path)
    if record.status not in allowed_statuses:
        raise ValueError(f"Cannot resume a run with status '{record.status}'.")

    config = use_prompt_snapshots(
        load_effective_config(run_directory / EFFECTIVE_CONFIG_FILENAME),
        run_directory,
    )
    loaded_prompt_profile = load_prompt_profile(
        config.stages.prompt_generation.prompt_profile
    )
    adapters = create_adapters(config)
    run_context = load_run_context(run_directory)
    return run_pipeline(
        config=config,
        run_context=run_context,
        database_path=database_path,
        images_directory=run_directory / "images",
        adapters=adapters,
        prompt_profile=loaded_prompt_profile.profile,
        resume=True,
    )
