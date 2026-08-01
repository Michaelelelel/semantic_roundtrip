"""Read-only HTTP routes shared by the future status pages."""

from pathlib import Path
from typing import Annotated, Literal

from fastapi import APIRouter, Depends, HTTPException, Request, status
from pydantic import BaseModel, Field

from semantic_roundtrip.status.discovery import list_jobs, list_standalone_runs


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
