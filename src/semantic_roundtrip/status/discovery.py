"""Discover persisted jobs and standalone runs below one runs root."""

from pathlib import Path

from semantic_roundtrip.persistence.job.schema import job_database_path
from semantic_roundtrip.persistence.run.schema import database_path_for_run
from semantic_roundtrip.status.common import STATUS_READ_ERRORS, unavailable
from semantic_roundtrip.status.jobs import get_job_status
from semantic_roundtrip.status.models import (
    JobDiscoveryResult,
    RunDiscoveryResult,
)
from semantic_roundtrip.status.runs import get_run_status


def _directories(root: Path) -> list[Path]:
    root = root.resolve()
    if not root.is_dir():
        raise NotADirectoryError(f"Runs root does not exist: {root}")
    return sorted(
        (path for path in root.iterdir() if path.is_dir()),
        key=lambda path: path.name,
        reverse=True,
    )


def _matches(status: str, statuses: set[str] | None) -> bool:
    return statuses is None or status in statuses


def list_jobs(
    runs_root: Path,
    statuses: set[str] | None = None,
) -> list[JobDiscoveryResult]:
    """List immediate persisted jobs, newest directory first."""
    results: list[JobDiscoveryResult] = []
    for directory in _directories(runs_root):
        try:
            if not job_database_path(directory).is_file():
                continue
            result: JobDiscoveryResult = get_job_status(directory)
        except STATUS_READ_ERRORS as error:
            result = unavailable("job", directory, error)

        if _matches(result.status, statuses):
            results.append(result)
    return results


def list_standalone_runs(
    runs_root: Path,
    statuses: set[str] | None = None,
) -> list[RunDiscoveryResult]:
    """List immediate runs without descending into job child directories."""
    results: list[RunDiscoveryResult] = []
    for directory in _directories(runs_root):
        try:
            if job_database_path(directory).is_file():
                continue
            if not database_path_for_run(directory).is_file():
                continue
            result: RunDiscoveryResult = get_run_status(directory)
        except STATUS_READ_ERRORS as error:
            result = unavailable("run", directory, error)

        if _matches(result.status, statuses):
            results.append(result)
    return results
