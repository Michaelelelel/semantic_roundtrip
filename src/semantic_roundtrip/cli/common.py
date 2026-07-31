"""Shared behavior for all CLI command groups."""

import signal
import sqlite3
import time
from collections.abc import Callable
from pathlib import Path
from types import FrameType
from typing import Never

import typer
import yaml
from rich.console import Console

from semantic_roundtrip.adapters.errors import AdapterError
from semantic_roundtrip.runtime import RuntimeControllerError


console = Console()

EXPECTED_COMMAND_ERRORS = (
    AdapterError,
    RuntimeControllerError,
    OSError,
    sqlite3.Error,
    ValueError,
    yaml.YAMLError,
)
TERMINAL_STATUSES = frozenset({"paused", "completed", "failed", "interrupted"})

StatusRenderer = Callable[[Path], str]


def runs_root_option() -> Path:
    """Create the shared option for discovering persisted jobs and runs."""
    return typer.Option(
        Path("runs"),
        "--root",
        exists=True,
        file_okay=False,
        dir_okay=True,
        resolve_path=True,
        help="Directory containing persisted jobs and standalone runs.",
    )


def _interrupt_on_sigterm(
    _signal_number: int,
    _frame: FrameType | None,
) -> Never:
    """Translate Docker's stop signal into the CLI's normal interrupt path."""
    raise KeyboardInterrupt


def install_termination_handler() -> None:
    """Persist interrupted state when Docker stops the CLI process."""
    signal.signal(signal.SIGTERM, _interrupt_on_sigterm)


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
