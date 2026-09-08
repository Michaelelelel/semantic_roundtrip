"""Read-only HTTP routes for status pages and process health checks."""

from pathlib import Path
from typing import Annotated, Literal

from fastapi import APIRouter, Depends, HTTPException, Query, Request, status
from fastapi.responses import FileResponse, HTMLResponse, RedirectResponse
from pydantic import BaseModel, Field

from semantic_roundtrip.config_resolution import load_effective_config
from semantic_roundtrip.persistence.job.schema import job_database_path
from semantic_roundtrip.persistence.run.config_snapshot import EFFECTIVE_CONFIG_FILENAME
from semantic_roundtrip.persistence.run.result_queries import (
    RouteAccuracy,
    read_image_artifact_path,
    read_result_trace_page,
    read_route_accuracies,
    read_verification_summary,
)
from semantic_roundtrip.persistence.run.schema import database_path_for_run
from semantic_roundtrip.status.common import STATUS_READ_ERRORS
from semantic_roundtrip.status.discovery import list_jobs, list_standalone_runs
from semantic_roundtrip.status.jobs import get_job_status
from semantic_roundtrip.status.runs import get_run_status

router = APIRouter()

RESULTS_PAGE_SIZE = 20
TERMINAL_STATUSES = frozenset({"completed", "failed", "interrupted"})
IMAGE_SUFFIXES = frozenset({".jpeg", ".jpg", ".png", ".webp"})


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


def _resolve_run_directory(runs_root: Path, relative_path: str) -> Path:
    """Resolve an experiment run containing a current run database."""
    run_directory = _resolve_runs_directory(runs_root, relative_path)
    if not database_path_for_run(run_directory).is_file():
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Run not found.",
        )
    return run_directory


def _parent_job_id(run_directory: Path, runs_root: Path) -> str | None:
    """Return the owning job ID for a child run, otherwise None."""
    if run_directory.parent.name != "runs":
        return None

    job_directory = run_directory.parent.parent
    if job_directory.parent != runs_root:
        return None
    if not job_database_path(job_directory).is_file():
        return None
    return job_directory.name


def _resolve_image_file(run_directory: Path, stored_path: Path) -> Path:
    """Resolve one database-recorded image without escaping its run."""
    image_path = (run_directory / stored_path).resolve()
    try:
        image_path.relative_to(run_directory)
    except ValueError as error:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Image not found.",
        ) from error

    if image_path.suffix.lower() not in IMAGE_SUFFIXES or not image_path.is_file():
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Image not found.",
        )
    return image_path


def _unreadable_status(error: BaseException) -> HTTPException:
    """Return a concise HTTP error without exposing a server traceback."""
    return HTTPException(
        status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
        detail=f"Persisted status could not be read: {error}",
    )


def _run_accuracies(run_directory: Path) -> dict[str, RouteAccuracy]:
    config = load_effective_config(run_directory / EFFECTIVE_CONFIG_FILENAME)
    return read_route_accuracies(database_path_for_run(run_directory), config)


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
        auto_refresh=True,
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
    entry_accuracies = {}
    for entry in job.entries:
        try:
            entry_accuracies[entry.index] = _run_accuracies(entry.run_directory)
        except STATUS_READ_ERRORS:
            entry_accuracies[entry.index] = None
    return _render(
        request,
        "job.html",
        job=job,
        entry_paths=entry_paths,
        entry_accuracies=entry_accuracies,
        auto_refresh=job.status not in TERMINAL_STATUSES,
    )


@router.get("/runs/{run_path:path}", response_class=HTMLResponse)
def run_detail(
    request: Request,
    run_path: str,
    runs_root: RunsRoot,
) -> HTMLResponse:
    """Show one standalone or job-owned experiment run."""
    run_directory = _resolve_run_directory(runs_root, run_path)

    try:
        run = get_run_status(run_directory)
        config = load_effective_config(run_directory / EFFECTIVE_CONFIG_FILENAME)
        database_path = database_path_for_run(run_directory)
        accuracies = read_route_accuracies(database_path, config)
        verification = read_verification_summary(database_path, config)
    except STATUS_READ_ERRORS as error:
        raise _unreadable_status(error) from error

    return _render(
        request,
        "run.html",
        run=run,
        accuracies=accuracies,
        verification=verification,
        run_path=run_directory.relative_to(runs_root).as_posix(),
        parent_job_id=_parent_job_id(run_directory, runs_root),
        auto_refresh=run.status not in TERMINAL_STATUSES,
    )


@router.get("/results/{run_path:path}", response_class=HTMLResponse)
def run_results(
    request: Request,
    run_path: str,
    runs_root: RunsRoot,
    page: Annotated[int, Query(ge=1)] = 1,
) -> HTMLResponse:
    """Show paginated products from every completed pipeline stage."""
    run_directory = _resolve_run_directory(runs_root, run_path)
    database_path = database_path_for_run(run_directory)

    try:
        run = get_run_status(run_directory)
        config = load_effective_config(run_directory / EFFECTIVE_CONFIG_FILENAME)
        result_page = read_result_trace_page(
            database_path,
            config,
            page=page,
            page_size=RESULTS_PAGE_SIZE,
        )
        accuracies = read_route_accuracies(database_path, config)
        verification = read_verification_summary(database_path, config)
    except STATUS_READ_ERRORS as error:
        raise _unreadable_status(error) from error

    if page > result_page.total_pages:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Result page not found.",
        )

    return _render(
        request,
        "results.html",
        run=run,
        run_path=run_directory.relative_to(runs_root).as_posix(),
        result_page=result_page,
        accuracies=accuracies,
        verification=verification,
        stages={stage.name: stage for stage in run.stages},
        is_terminal=run.status in TERMINAL_STATUSES,
        auto_refresh=run.status not in TERMINAL_STATUSES,
    )


@router.get("/images/{image_id}/{run_path:path}", response_class=FileResponse)
def run_image(
    image_id: int,
    run_path: str,
    runs_root: RunsRoot,
) -> FileResponse:
    """Serve one database-recorded generated image from its run directory."""
    run_directory = _resolve_run_directory(runs_root, run_path)
    try:
        stored_path = read_image_artifact_path(
            database_path_for_run(run_directory),
            image_id,
        )
    except STATUS_READ_ERRORS as error:
        raise _unreadable_status(error) from error

    if stored_path is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Image not found.",
        )
    return FileResponse(_resolve_image_file(run_directory, stored_path))


@router.get("/prompt-results/{run_path:path}", response_class=RedirectResponse)
def run_prompt_results(
    request: Request,
    run_path: str,
    runs_root: RunsRoot,
) -> RedirectResponse:
    """Keep old bookmarks working without a separate prompt-results page."""
    run_directory = _resolve_run_directory(runs_root, run_path)
    # Old pagination counted prompts, while the unified view can expand images.
    # Reset to the first page rather than forwarding a different page coordinate.
    return RedirectResponse(
        request.url_for(
            "run_results", run_path=run_directory.relative_to(runs_root).as_posix()
        ),
        status_code=status.HTTP_303_SEE_OTHER,
    )


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
