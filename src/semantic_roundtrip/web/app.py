"""FastAPI application factory for the read-only status website."""

import os
from pathlib import Path

from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

from semantic_roundtrip.web.formatting import (
    format_datetime,
    format_duration,
    format_eta,
    format_stage,
)
from semantic_roundtrip.web.routes import router


RUNS_ROOT_ENVIRONMENT_VARIABLE = "SEMANTIC_ROUNDTRIP_RUNS_ROOT"
WEB_DIRECTORY = Path(__file__).parent


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
    templates = Jinja2Templates(directory=WEB_DIRECTORY / "templates")
    templates.env.filters.update(
        datetime=format_datetime,
        duration=format_duration,
        eta=format_eta,
        stage=format_stage,
    )
    app.state.templates = templates
    app.mount(
        "/static",
        StaticFiles(directory=WEB_DIRECTORY / "static"),
        name="static",
    )
    app.include_router(router)
    return app
