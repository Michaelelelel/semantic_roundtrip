"""Read-only aggregation for jobs and their child experiment runs."""

from pathlib import Path

from semantic_roundtrip.job import JOB_SNAPSHOT_FILENAME, load_job_snapshot
from semantic_roundtrip.persistence.job_database import (
    read_job_entries,
    read_job_record,
)
from semantic_roundtrip.persistence.job_schema import job_database_path
from semantic_roundtrip.persistence.run_database import read_run_record
from semantic_roundtrip.persistence.run_schema import database_path_for_run
from semantic_roundtrip.status.common import (
    STATUS_READ_ERRORS,
    elapsed_seconds,
    unavailable,
)
from semantic_roundtrip.status.models import (
    ChildRunStatus,
    JobEntryStatus,
    JobStatus,
    UnavailableStatus,
)
from semantic_roundtrip.status.runs import get_run_status


def get_job_status(job_directory: Path) -> JobStatus:
    """Read one job and aggregate the states of all child runs."""
    job_directory = job_directory.resolve()
    database_path = job_database_path(job_directory)
    record = read_job_record(database_path)
    persisted_entries = read_job_entries(database_path, job_directory)
    config = load_job_snapshot(job_directory / JOB_SNAPSHOT_FILENAME)

    configured_entries = {entry.index: entry for entry in config.entries}
    if len(configured_entries) != len(persisted_entries):
        raise ValueError("Job snapshot and database entry counts do not match.")

    entries: list[JobEntryStatus] = []
    for entry in persisted_entries:
        configured = configured_entries.get(entry.entry_index)
        if configured is None:
            raise ValueError(f"Missing job snapshot entry {entry.entry_index}.")

        try:
            child_record = read_run_record(database_path_for_run(entry.run_directory))
            child = ChildRunStatus(
                run_id=child_record.run_id,
                status=child_record.status,
                last_update=child_record.heartbeat_at,
            )
        except STATUS_READ_ERRORS as error:
            child = unavailable("run", entry.run_directory, error)

        models = tuple(
            backend.model_id or backend.adapter for backend in configured.backends
        )
        if entry.error_message is not None:
            last_error = f"{entry.error_type}: {entry.error_message}"
        elif isinstance(child, UnavailableStatus):
            last_error = child.error
        else:
            last_error = None
        entries.append(
            JobEntryStatus(
                index=entry.entry_index,
                name=configured.name,
                status=entry.status,
                run_directory=entry.run_directory,
                child=child,
                models=models,
                last_error=last_error,
            )
        )

    active_entry = next(
        (entry for entry in entries if entry.status in {"running", "paused"}),
        None,
    )
    active_child = None
    if active_entry is not None and not isinstance(
        active_entry.child, UnavailableStatus
    ):
        try:
            active_child = get_run_status(active_entry.run_directory)
        except STATUS_READ_ERRORS:
            pass
    latest_updates = [record.heartbeat_at]
    latest_updates.extend(
        entry.child.last_update
        for entry in entries
        if isinstance(entry.child, ChildRunStatus)
    )
    last_update = max(
        (value for value in latest_updates if value is not None),
        default=None,
    )
    last_error = next(
        (entry.last_error for entry in reversed(entries) if entry.last_error),
        None,
    )

    return JobStatus(
        directory=job_directory,
        job_id=record.job_id,
        name=record.name,
        status=record.status,
        created_at=record.created_at,
        started_at=record.started_at,
        last_update=last_update,
        finished_at=record.finished_at,
        elapsed_seconds=elapsed_seconds(
            status=record.status,
            started_at=record.started_at,
            heartbeat_at=record.heartbeat_at,
            finished_at=record.finished_at,
        ),
        entries=tuple(entries),
        completed_entries=sum(entry.status == "completed" for entry in entries),
        total_entries=len(entries),
        active_entry_name=(None if active_entry is None else active_entry.name),
        active_run_id=(
            None
            if active_entry is None or isinstance(active_entry.child, UnavailableStatus)
            else active_entry.child.run_id
        ),
        active_stage=(None if active_child is None else active_child.active_stage),
        eta_state=("none" if active_child is None else active_child.eta_state),
        eta_seconds=(None if active_child is None else active_child.eta_seconds),
        last_error=last_error,
    )
