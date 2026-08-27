"""Resolve one configured inheritance reference to one concrete source run."""

from dataclasses import dataclass
from pathlib import Path

from semantic_roundtrip.config import ResolvedAppConfig


@dataclass(frozen=True, slots=True)
class SourceRun:
    """The minimum stable interface exposed by a persisted source run."""

    directory: Path
    run_id: str
    config: ResolvedAppConfig


def load_source_run(run_directory: Path) -> SourceRun:
    """Load a current-schema run without mutating its database or artifacts."""
    from semantic_roundtrip.config_resolution import load_effective_config
    from semantic_roundtrip.persistence.run.config_snapshot import (
        EFFECTIVE_CONFIG_FILENAME,
    )
    from semantic_roundtrip.persistence.run.queries import read_run_record
    from semantic_roundtrip.persistence.run.schema import database_path_for_run

    directory = run_directory.expanduser().resolve()
    if not directory.is_dir():
        raise FileNotFoundError(f"Inherited run directory does not exist: {directory}")

    config_path = directory / EFFECTIVE_CONFIG_FILENAME
    if not config_path.is_file():
        raise FileNotFoundError(
            f"Inherited run has no effective configuration: {config_path}"
        )
    record = read_run_record(database_path_for_run(directory))
    return SourceRun(
        directory=directory,
        run_id=record.run_id,
        config=load_effective_config(config_path),
    )


def resolve_job_entry_run(job_directory: Path, entry_name: str) -> SourceRun:
    """Resolve one stable entry name from a persisted job to its child run."""
    from semantic_roundtrip.job.config import JOB_SNAPSHOT_FILENAME, load_job_snapshot
    from semantic_roundtrip.persistence.job.database import read_job_entries
    from semantic_roundtrip.persistence.job.schema import job_database_path

    directory = job_directory.expanduser().resolve()
    snapshot = load_job_snapshot(directory / JOB_SNAPSHOT_FILENAME)
    matches = [entry for entry in snapshot.entries if entry.name == entry_name]
    if len(matches) != 1:
        raise ValueError(
            f"Job source must contain exactly one entry named '{entry_name}'."
        )
    entry = matches[0]
    records = read_job_entries(job_database_path(directory), directory)
    try:
        record = records[entry.index]
    except IndexError as error:
        raise ValueError(
            f"Job entry '{entry_name}' has no persisted child run."
        ) from error
    return load_source_run(record.run_directory)
