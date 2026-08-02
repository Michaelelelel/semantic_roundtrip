"""Read-only HTTP routes for status pages and process health checks."""

from pathlib import Path
from typing import Annotated, Literal

from fastapi import APIRouter, Depends, HTTPException, Request, status
from fastapi.responses import HTMLResponse
from pydantic import BaseModel, Field

from semantic_roundtrip.persistence.job.schema import job_database_path
from semantic_roundtrip.persistence.run.schema import database_path_for_run
from semantic_roundtrip.status.common import STATUS_READ_ERRORS
from semantic_roundtrip.status.discovery import list_jobs, list_standalone_runs
from semantic_roundtrip.status.jobs import get_job_status
from semantic_roundtrip.status.runs import get_run_status


router = APIRouter()


class HealthResponse(BaseModel):
    """Liveness response that does not depend on persisted data."""

    status: Literal["ok"] = "ok"


class ReadinessResponse(BaseModel):
    """Summary proving that the configured runs root can be discovered."""

    status: Literal["ready"] = "ready"
    jobs: int = Field(ge=0)
    standalone_runs: int = Field(ge=0)
    unavailable: int = Field(ge=0)


def get_runs_root(request: Request) -> Path:
    """Return the validated runs root configured by the application factory."""
    return request.app.state.runs_root


RunsRoot = Annotated[Path, Depends(get_runs_root)]


def _render(request: Request, template: str, **context: object) -> HTMLResponse:
    """Render one page through the application-owned template environment."""
    return request.app.state.templates.TemplateResponse(
        request=request,
        name=template,
        context=context,
    )


def _resolve_runs_directory(runs_root: Path, relative_path: str) -> Path:
    """Resolve a URL path without allowing access outside the runs root."""
    candidate = (runs_root / relative_path).resolve()
    try:
        candidate.relative_to(runs_root)
    except ValueError as error:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Status directory not found.",
        ) from error

    if not candidate.is_dir():
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Status directory not found.",
        )
    return candidate


def _unreadable_status(error: BaseException) -> HTTPException:
    """Return a concise HTTP error without exposing a server traceback."""
    return HTTPException(
        status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
        detail=f"Persisted status could not be read: {error}",
    )


@router.get("/", response_class=HTMLResponse)
def overview(request: Request, runs_root: RunsRoot) -> HTMLResponse:
    """Show all persisted jobs and standalone experiment runs."""
    try:
        jobs = list_jobs(runs_root)
        standalone_runs = list_standalone_runs(runs_root)
    except OSError as error:
        raise _unreadable_status(error) from error

    return _render(
        request,
        "overview.html",
        jobs=jobs,
        standalone_runs=standalone_runs,
    )


@router.get("/jobs/{job_id}", response_class=HTMLResponse)
def job_detail(
    request: Request,
    job_id: str,
    runs_root: RunsRoot,
) -> HTMLResponse:
    """Show one persisted job and links to all of its child runs."""
    job_directory = _resolve_runs_directory(runs_root, job_id)
    if not job_database_path(job_directory).is_file():
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Job not found.",
        )

    try:
        job = get_job_status(job_directory)
    except STATUS_READ_ERRORS as error:
        raise _unreadable_status(error) from error

    entry_paths = {
        entry.index: entry.run_directory.relative_to(runs_root).as_posix()
        for entry in job.entries
    }
    return _render(
        request,
        "job.html",
        job=job,
        entry_paths=entry_paths,
    )


@router.get("/runs/{run_path:path}", response_class=HTMLResponse)
def run_detail(
    request: Request,
    run_path: str,
    runs_root: RunsRoot,
) -> HTMLResponse:
    """Show one standalone or job-owned experiment run."""
    run_directory = _resolve_runs_directory(runs_root, run_path)
    if not database_path_for_run(run_directory).is_file():
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Run not found.",
        )

    try:
        run = get_run_status(run_directory)
    except STATUS_READ_ERRORS as error:
        raise _unreadable_status(error) from error

    return _render(request, "run.html", run=run)


@router.get("/health", response_model=HealthResponse)
def health() -> HealthResponse:
    """Report that the web process is alive."""
    return HealthResponse()


@router.get("/ready", response_model=ReadinessResponse)
def readiness(runs_root: RunsRoot) -> ReadinessResponse:
    """Read persisted job and standalone-run discovery without writing state."""
    try:
        jobs = list_jobs(runs_root)
        standalone_runs = list_standalone_runs(runs_root)
    except OSError as error:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=str(error),
        ) from error

    unavailable = sum(result.status == "unavailable" for result in jobs)
    unavailable += sum(result.status == "unavailable" for result in standalone_runs)
    return ReadinessResponse(
        jobs=len(jobs),
        standalone_runs=len(standalone_runs),
        unavailable=unavailable,
    )
