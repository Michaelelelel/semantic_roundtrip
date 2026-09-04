"""Read-only aggregation for individual experiment runs."""

from pathlib import Path
from statistics import median

from semantic_roundtrip.config import PipelineStageName, ResolvedAppConfig
from semantic_roundtrip.config_resolution import (
    expected_output_count,
    expected_stage_outputs,
    get_stage_config,
    load_effective_config,
)
from semantic_roundtrip.inheritance.dependencies import dependency_closure
from semantic_roundtrip.persistence.run.config_snapshot import (
    EFFECTIVE_CONFIG_FILENAME,
)
from semantic_roundtrip.persistence.run.queries import (
    read_active_runtime_action,
    read_completed_task_durations,
    read_latest_stage_error,
    read_run_record,
    read_stage_progress,
    read_stage_runtime_model,
)
from semantic_roundtrip.persistence.run.schema import database_path_for_run
from semantic_roundtrip.status.common import elapsed_seconds
from semantic_roundtrip.status.models import EtaState, RunStatus, StageStatus

STAGE_ORDER = (
    "illustratability_rating",
    "prompt_generation",
    "image_generation",
    "verification",
    "title_guessing_direct",
    "image_description",
    "title_guessing_from_description",
)
MINIMUM_ETA_SAMPLES = 3


def _stage_model(
    config: ResolvedAppConfig,
    stage_name: PipelineStageName,
    *,
    database_path: Path,
    imported: bool,
) -> str | None:
    """Return the configured model ID for one executable pipeline stage."""
    if imported:
        return read_stage_runtime_model(database_path, stage_name)

    stage = get_stage_config(config, stage_name)
    if stage is None:
        return None

    backend = config.backends[stage.backend]
    model_id = backend.settings.get("model_id")
    if isinstance(model_id, str) and model_id:
        return model_id
    return backend.adapter


def _active_stage(status: str, stages: tuple[StageStatus, ...]) -> str | None:
    if status == "created" or status == "completed":
        return None

    for stage in stages:
        if not stage.imported and stage.running > 0:
            return stage.name

    if status == "failed":
        for stage in reversed(stages):
            if not stage.imported and stage.failed > 0:
                return stage.name

    for stage in stages:
        if not stage.imported and stage.produced < stage.expected:
            return stage.name
    return None


def _estimate_remaining(
    *,
    database_path: Path,
    stage: StageStatus | None,
    runtime_action: str | None,
) -> tuple[EtaState, float | None]:
    if runtime_action == "load":
        return "loading_model", None
    if runtime_action == "unload":
        return "unloading_model", None
    if stage is None or stage.produced >= stage.expected:
        return "none", None

    durations = read_completed_task_durations(database_path, stage.name)
    if len(durations) < MINIMUM_ETA_SAMPLES:
        return "calculating", None

    remaining = stage.expected - stage.produced
    return "estimated", median(durations) * remaining


def get_run_status(run_directory: Path) -> RunStatus:
    """Read one run's lifecycle, stage progress, duration, and stage ETA."""
    run_directory = run_directory.resolve()
    database_path = database_path_for_run(run_directory)
    record = read_run_record(database_path)
    config = load_effective_config(run_directory / EFFECTIVE_CONFIG_FILENAME)
    expected = expected_stage_outputs(config)
    imported_stages = (
        set()
        if config.inherit is None
        else set(dependency_closure(config.inherit.stages))
    )
    progress = {stage.stage: stage for stage in read_stage_progress(database_path)}
    for stage_name in imported_stages:
        expected[stage_name] = (
            progress[stage_name].expected_outputs
            if stage_name in progress
            else expected_output_count(config, stage_name)
        )

    stages = tuple(
        StageStatus(
            name=stage_name,
            model=_stage_model(
                config,
                stage_name,
                database_path=database_path,
                imported=stage_name in imported_stages,
            ),
            produced=(
                progress[stage_name].produced_outputs if stage_name in progress else 0
            ),
            expected=expected[stage_name],
            pending=(progress[stage_name].pending if stage_name in progress else 0),
            running=(progress[stage_name].running if stage_name in progress else 0),
            failed=(progress[stage_name].failed if stage_name in progress else 0),
            imported=stage_name in imported_stages,
        )
        for stage_name in STAGE_ORDER
        if stage_name in expected
    )
    failed_tasks = sum(stage.failed for stage in stages)
    active_stage_name = _active_stage(record.status, stages)
    active_stage = next(
        (stage for stage in stages if stage.name == active_stage_name),
        None,
    )
    eta_state, eta_seconds = _estimate_remaining(
        database_path=database_path,
        stage=active_stage,
        runtime_action=(
            read_active_runtime_action(database_path)
            if record.status in {"running", "pausing"}
            else None
        ),
    )

    return RunStatus(
        directory=run_directory,
        run_id=record.run_id,
        name=record.name,
        status=record.status,
        created_at=record.created_at,
        started_at=record.started_at,
        last_update=record.heartbeat_at,
        finished_at=record.finished_at,
        elapsed_seconds=elapsed_seconds(
            status=record.status,
            started_at=record.started_at,
            heartbeat_at=record.heartbeat_at,
            finished_at=record.finished_at,
        ),
        stages=stages,
        active_stage=active_stage_name,
        eta_state=eta_state,
        eta_seconds=eta_seconds,
        last_error=(
            read_latest_stage_error(database_path)
            if record.status == "failed" or failed_tasks > 0
            else None
        ),
    )
