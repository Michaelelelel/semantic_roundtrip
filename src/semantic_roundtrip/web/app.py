"""FastAPI application factory for the read-only status website."""

import os
from pathlib import Path

from fastapi import FastAPI

from semantic_roundtrip.web.routes import router


RUNS_ROOT_ENVIRONMENT_VARIABLE = "SEMANTIC_ROUNDTRIP_RUNS_ROOT"


def _configured_runs_root(runs_root: Path | None) -> Path:
    if runs_root is None:
        configured_value = os.environ.get(RUNS_ROOT_ENVIRONMENT_VARIABLE)
        if configured_value is None:
            raise RuntimeError(
                f"{RUNS_ROOT_ENVIRONMENT_VARIABLE} must point to the runs directory."
            )
        runs_root = Path(configured_value)

    resolved_root = runs_root.resolve()
    if not resolved_root.is_dir():
        raise NotADirectoryError(f"Runs root does not exist: {resolved_root}")
    return resolved_root


def create_app(runs_root: Path | None = None) -> FastAPI:
    """Create a status application bound to one persisted runs root."""
    app = FastAPI(
        title="Semantic Roundtrip Status",
        docs_url=None,
        redoc_url=None,
        openapi_url=None,
    )
    app.state.runs_root = _configured_runs_root(runs_root)
    app.include_router(router)
    return app
