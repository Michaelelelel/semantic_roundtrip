"""Shared behavior for all CLI command groups."""

import time
from collections.abc import Callable
from pathlib import Path
from typing import Never

import typer
from rich.console import Console

from semantic_roundtrip.adapters.errors import AdapterError


console = Console()

EXPECTED_COMMAND_ERRORS = (AdapterError, OSError, ValueError)
TERMINAL_STATUSES = frozenset({"paused", "completed", "failed", "interrupted"})

StatusRenderer = Callable[[Path], str]


def exit_with_error(
    error: BaseException,
    *,
    code: int = 1,
    message: str | None = None,
) -> Never:
    """Print a concise expected error and stop without a traceback."""
    typer.echo(message or str(error), err=True)
    raise typer.Exit(code=code) from error


def watch_status(
    directory: Path,
    *,
    render: StatusRenderer,
    interval_seconds: float | None,
) -> None:
    """Render one status or refresh it until the persisted state is terminal."""
    while True:
        if interval_seconds is not None:
            console.clear()

        current_status = render(directory)
        if interval_seconds is None or current_status in TERMINAL_STATUSES:
            return

        time.sleep(interval_seconds)
