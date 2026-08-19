"""Sequential execution and resume behavior for persisted jobs."""

from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from shutil import copy2
from typing import Literal

import yaml

from semantic_roundtrip.experiment_runner import (
    prepare_experiment,
    resume_experiment,
)
from semantic_roundtrip.job.config import (
    JOB_INPUT_FILENAME,
    JOB_RUNS_DIRECTORY,
    JOB_SNAPSHOT_FILENAME,
    JobContext,
    LoadedJobConfig,
    ResolvedJobConfig,
    ResolvedJobEntry,
    create_resolved_job_config,
    load_job_config,
    load_job_snapshot,
    plan_job,
)
from semantic_roundtrip.persistence.run.database import (
    request_run_pause,
)
from semantic_roundtrip.persistence.job.database import (
    JobDatabase,
    read_job_entries,
    read_job_record,
)
from semantic_roundtrip.persistence.job.schema import (
    initialize_job_database,
    job_database_path,
)
from semantic_roundtrip.persistence.run.manager import create_run
from semantic_roundtrip.persistence.run.queries import read_run_record
from semantic_roundtrip.persistence.run.schema import database_path_for_run


Report = Callable[[str], None]
EntryOutcome = Literal["continue", "paused", "failed"]
CHILD_RESUMABLE_STATUSES = frozenset({"created", "paused", "failed", "interrupted"})
JOB_RESUMABLE_STATUSES = frozenset({"created", "paused", "failed", "interrupted"})


class JobStateError(ValueError):
    """Refuse execution when persisted state suggests another active process."""


@dataclass(frozen=True, slots=True)
class PreparedJob:
    """A persisted job ready for initial execution."""

    context: JobContext
    config: ResolvedJobConfig
    database_path: Path
    input_config_path: Path
    effective_config_path: Path
    run_directories: tuple[Path, ...]


@dataclass(frozen=True, slots=True)
class JobExecutionSummary:
    """Final persisted state after one job invocation."""

    job_id: str
    directory: Path
    status: str
    pending: int
    running: int
    paused: int
    completed: int
    failed: int
    interrupted: int


@dataclass(frozen=True, slots=True)
class JobPauseSummary:
    """The active child run that received a cooperative pause request."""

    job_id: str
    job_directory: Path
    entry_index: int
    entry_name: str
    child_run_id: str
    child_directory: Path
    child_status: str


def _report(callback: Report | None, message: str) -> None:
    if callback is not None:
        callback(message)


def _write_job_snapshot(
    config: ResolvedJobConfig,
    path: Path,
) -> None:
    with path.open("x", encoding="utf-8") as file:
        yaml.safe_dump(
            config.model_dump(mode="json", exclude_none=True),
            file,
            sort_keys=False,
            allow_unicode=True,
        )


def _create_job_context(loaded: LoadedJobConfig) -> JobContext:
    run_context = create_run(
        loaded.input_config.job.output_directory,
        loaded.input_config.job.name,
    )
    return JobContext(
        job_id=run_context.run_id,
        directory=run_context.directory,
        created_at=run_context.created_at,
    )


def prepare_job(config_path: Path) -> PreparedJob:
    """Validate and freeze a new job before executing any experiment."""
    loaded = load_job_config(config_path)
    plan = plan_job(loaded)
    if plan.missing_credentials:
        names = ", ".join(plan.missing_credentials)
        raise ValueError(f"Missing credential environment variables: {names}")
    if plan.missing_runtime_models:
        names = ", ".join(plan.missing_runtime_models)
        raise ValueError(f"Models missing from deployment catalogs: {names}")

    context = _create_job_context(loaded)
    runs_directory = context.directory / JOB_RUNS_DIRECTORY
    runs_directory.mkdir()

    input_config_path = context.directory / JOB_INPUT_FILENAME
    copy2(loaded.source_path, input_config_path)

    run_directories: list[Path] = []
    for entry in loaded.experiments:
        child = prepare_experiment(
            config=entry.config,
            input_config_path=entry.source_path,
            output_directory=runs_directory,
        )
        run_directories.append(
            child.run_context.directory.relative_to(context.directory)
        )

    resolved_config = create_resolved_job_config(loaded)
    effective_config_path = context.directory / JOB_SNAPSHOT_FILENAME
    _write_job_snapshot(resolved_config, effective_config_path)
    database_path = initialize_job_database(
        context,
        resolved_config,
        input_config_path,
        effective_config_path,
        run_directories,
    )
    return PreparedJob(
        context=context,
        config=resolved_config,
        database_path=database_path,
        input_config_path=input_config_path,
        effective_config_path=effective_config_path,
        run_directories=tuple(context.directory / path for path in run_directories),
    )


def load_prepared_job(job_directory: Path) -> PreparedJob:
    """Reconstruct a job exclusively from its frozen artifacts."""
    job_directory = job_directory.resolve()
    database_path = job_database_path(job_directory)
    record = read_job_record(database_path)
    config = load_job_snapshot(job_directory / JOB_SNAPSHOT_FILENAME)
    context = JobContext(
        job_id=record.job_id,
        directory=job_directory,
        created_at=record.created_at,
    )
    if config.job.name != record.name:
        raise ValueError("Job snapshot and database names do not match.")
    entries = read_job_entries(database_path, job_directory)
    if len(config.entries) != len(entries):
        raise ValueError("Job snapshot and database entry counts do not match.")

    return PreparedJob(
        context=context,
        config=config,
        database_path=database_path,
        input_config_path=job_directory / JOB_INPUT_FILENAME,
        effective_config_path=job_directory / JOB_SNAPSHOT_FILENAME,
        run_directories=tuple(entry.run_directory for entry in entries),
    )


def request_job_pause(job_directory: Path) -> JobPauseSummary:
    """Pause a sequential job by requesting a pause from its active child."""
    prepared = load_prepared_job(job_directory)
    record = read_job_record(prepared.database_path)
    if record.status not in {"running", "paused"}:
        raise ValueError(f"Cannot pause a job with status '{record.status}'.")

    active_entries = [
        entry
        for entry in read_job_entries(
            prepared.database_path,
            prepared.context.directory,
        )
        if entry.status in {"running", "paused"}
    ]
    if len(active_entries) != 1:
        raise JobStateError(
            "The job does not have exactly one active child run. "
            "Wait for execution to start and try again."
        )

    entry = active_entries[0]
    child_record = request_run_pause(database_path_for_run(entry.run_directory))
    configured_entry = prepared.config.entries[entry.entry_index]
    return JobPauseSummary(
        job_id=prepared.context.job_id,
        job_directory=prepared.context.directory,
        entry_index=entry.entry_index,
        entry_name=configured_entry.name,
        child_run_id=child_record.run_id,
        child_directory=entry.run_directory,
        child_status=child_record.status,
    )


def _execution_summary(
    prepared: PreparedJob,
    database: JobDatabase,
    status: str,
) -> JobExecutionSummary:
    counts = {
        "pending": 0,
        "running": 0,
        "paused": 0,
        "completed": 0,
        "failed": 0,
        "interrupted": 0,
    }
    for entry in database.entries():
        counts[entry.status] += 1
    return JobExecutionSummary(
        job_id=prepared.context.job_id,
        directory=prepared.context.directory,
        status=status,
        pending=counts["pending"],
        running=counts["running"],
        paused=counts["paused"],
        completed=counts["completed"],
        failed=counts["failed"],
        interrupted=counts["interrupted"],
    )


def _execute_job_entry(
    *,
    prepared: PreparedJob,
    database: JobDatabase,
    configured_entry: ResolvedJobEntry,
    report: Report | None,
) -> EntryOutcome:
    """Execute or synchronize one child run and return its job-level outcome."""
    entry = database.get_entry(configured_entry.index)
    position = configured_entry.index + 1
    total = len(prepared.config.entries)
    prefix = f"[{position}/{total}] {configured_entry.name}:"

    if entry.status == "completed":
        _report(report, f"{prefix} already completed, skipping")
        return "continue"

    child_directory = entry.run_directory
    try:
        child_record = read_run_record(database_path_for_run(child_directory))
        if child_record.status == "completed":
            database.mark_entry_status(entry.entry_index, "completed")
            _report(report, f"{prefix} child run already completed, skipping")
            return "continue"
        if child_record.status == "running":
            raise JobStateError(
                f"Child run for job entry '{configured_entry.name}' is still "
                "marked running. Refusing to start a duplicate process."
            )

        database.mark_entry_running(entry.entry_index)
        action = "starting" if child_record.status == "created" else "resuming"
        _report(report, f"{prefix} {action} {child_directory.name}")
        summary = resume_experiment(
            child_directory,
            allowed_statuses=CHILD_RESUMABLE_STATUSES,
        )

        if summary.status == "paused":
            database.mark_entry_status(entry.entry_index, "paused")
            _report(report, f"{prefix} paused")
            return "paused"
        if summary.status != "completed":
            raise RuntimeError(
                f"Child run ended with unexpected status '{summary.status}'."
            )

        database.mark_entry_status(entry.entry_index, "completed")
        if summary.failed_tasks:
            task_label = "task" if summary.failed_tasks == 1 else "tasks"
            _report(
                report,
                f"{prefix} completed with {summary.failed_tasks} failed {task_label}",
            )
        else:
            _report(report, f"{prefix} completed")
        return "continue"
    except KeyboardInterrupt:
        database.mark_entry_status(entry.entry_index, "interrupted")
        _report(report, f"{prefix} interrupted")
        raise
    except JobStateError:
        raise
    except Exception as error:
        database.mark_entry_status(
            entry.entry_index,
            "failed",
            error=error,
        )
        _report(report, f"{prefix} failed: {error}")
        return "failed"


def execute_job(
    prepared: PreparedJob,
    *,
    resume: bool = False,
    report: Report | None = None,
) -> JobExecutionSummary:
    """Execute missing job entries sequentially and persist every transition."""
    record = read_job_record(prepared.database_path)
    if resume:
        if record.status not in JOB_RESUMABLE_STATUSES:
            raise ValueError(f"Cannot resume a job with status '{record.status}'.")
    elif record.status != "created":
        raise ValueError(f"Cannot start a job with status '{record.status}'.")

    with JobDatabase(prepared.database_path, prepared.context) as database:
        try:
            database.update_job_status("running")
            for configured_entry in prepared.config.entries:
                outcome = _execute_job_entry(
                    prepared=prepared,
                    database=database,
                    configured_entry=configured_entry,
                    report=report,
                )

                if outcome == "paused":
                    database.update_job_status("paused")
                    return _execution_summary(prepared, database, "paused")
                if outcome == "failed" and not prepared.config.job.continue_on_error:
                    database.update_job_status("failed")
                    return _execution_summary(prepared, database, "failed")

            failed = any(entry.status == "failed" for entry in database.entries())
            final_status = "failed" if failed else "completed"
            database.update_job_status(final_status)
            return _execution_summary(prepared, database, final_status)
        except KeyboardInterrupt, JobStateError:
            database.update_job_status("interrupted")
            raise
