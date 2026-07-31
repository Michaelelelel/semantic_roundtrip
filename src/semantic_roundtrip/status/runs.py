"""Read-only aggregation for individual experiment runs."""

from pathlib import Path
from statistics import median

from semantic_roundtrip.config_resolution import (
    expected_stage_outputs,
    load_effective_config,
)
from semantic_roundtrip.persistence.config_snapshot import EFFECTIVE_CONFIG_FILENAME
from semantic_roundtrip.persistence.run_database import (
    read_run_record,
    read_stage_progress,
)
from semantic_roundtrip.persistence.run_schema import (
    connect_run_database,
    database_path_for_run,
    require_run_schema,
)
from semantic_roundtrip.persistence.sqlite import parse_datetime
from semantic_roundtrip.status.common import elapsed_seconds
from semantic_roundtrip.status.models import EtaState, RunStatus, StageStatus


STAGE_ORDER = (
    "prompt_generation",
    "image_generation",
    "verification",
    "image_description",
    "title_guessing",
    "evaluation",
)
MINIMUM_ETA_SAMPLES = 3


def _completed_task_durations(database_path: Path, stage: str) -> list[float]:
    """Return clean first-attempt task durations for one stage."""
    connection = connect_run_database(database_path, read_only=True)
    try:
        require_run_schema(connection)
        rows = connection.execute(
            """
            SELECT started_at, finished_at
            FROM stage_tasks
            WHERE stage = ?
              AND status = 'completed'
              AND attempt = 1
              AND started_at IS NOT NULL
              AND finished_at IS NOT NULL
            """,
            (stage,),
        ).fetchall()
    finally:
        connection.close()

    durations: list[float] = []
    for row in rows:
        started_at = parse_datetime(row["started_at"])
        finished_at = parse_datetime(row["finished_at"])
        if started_at is None or finished_at is None:
            continue
        duration = (finished_at - started_at).total_seconds()
        if duration >= 0:
            durations.append(duration)
    return durations


def _active_runtime_action(database_path: Path) -> str | None:
    connection = connect_run_database(database_path, read_only=True)
    try:
        require_run_schema(connection)
        row = connection.execute(
            """
            SELECT action
            FROM runtime_events
            WHERE status = 'started'
            ORDER BY runtime_event_id DESC
            LIMIT 1
            """
        ).fetchone()
    finally:
        connection.close()
    return None if row is None else str(row["action"])


def _latest_stage_error(database_path: Path) -> str | None:
    """Return the newest persisted adapter error for a failed run."""
    connection = connect_run_database(database_path, read_only=True)
    try:
        require_run_schema(connection)
        row = connection.execute(
            """
            SELECT error_type, message
            FROM stage_errors
            ORDER BY error_id DESC
            LIMIT 1
            """
        ).fetchone()
    finally:
        connection.close()
    if row is None:
        return None
    return f"{row['error_type']}: {row['message']}"


def _active_stage(status: str, stages: tuple[StageStatus, ...]) -> str | None:
    if status == "created" or status == "completed":
        return None

    for stage in stages:
        if stage.running > 0:
            return stage.name

    if status == "failed":
        for stage in reversed(stages):
            if stage.failed > 0:
                return stage.name

    for stage in stages:
        if stage.produced < stage.expected:
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

    durations = _completed_task_durations(database_path, stage.name)
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
    progress = {stage.stage: stage for stage in read_stage_progress(database_path)}

    stages = tuple(
        StageStatus(
            name=stage_name,
            produced=(
                progress[stage_name].produced_outputs if stage_name in progress else 0
            ),
            expected=expected[stage_name],
            pending=(progress[stage_name].pending if stage_name in progress else 0),
            running=(progress[stage_name].running if stage_name in progress else 0),
            failed=(progress[stage_name].failed if stage_name in progress else 0),
        )
        for stage_name in STAGE_ORDER
        if stage_name in expected
    )
    active_stage_name = _active_stage(record.status, stages)
    active_stage = next(
        (stage for stage in stages if stage.name == active_stage_name),
        None,
    )
    eta_state, eta_seconds = _estimate_remaining(
        database_path=database_path,
        stage=active_stage,
        runtime_action=(
            _active_runtime_action(database_path)
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
            _latest_stage_error(database_path) if record.status == "failed" else None
        ),
    )
