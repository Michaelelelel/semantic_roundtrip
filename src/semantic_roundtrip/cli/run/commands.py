"""Commands for starting and managing individual experiment runs."""

import time
from pathlib import Path

import typer

from semantic_roundtrip.cli.common import console
from semantic_roundtrip.cli.run.output import (
    print_run_info,
    print_run_summary,
    show_run_status,
)
from semantic_roundtrip.experiment_runner import (
    execute_prepared_experiment,
    prepare_experiment_from_file,
    resume_experiment,
)
from semantic_roundtrip.persistence.database import (
    database_path_for_run,
    request_run_pause,
)


app = typer.Typer(
    help="Start and manage one experiment run.",
    no_args_is_help=True,
)


def _run_directory_option() -> Path:
    """Create the shared option for selecting an existing run directory."""
    return typer.Option(
        ...,
        "--run",
        "-r",
        exists=True,
        file_okay=False,
        dir_okay=True,
        resolve_path=True,
        help="Existing experiment run directory.",
    )


@app.command("start")
def start(
    config_file: Path = typer.Option(
        ...,
        "--config",
        "-c",
        exists=True,
        file_okay=True,
        dir_okay=False,
        resolve_path=True,
        help="Experiment configuration file.",
    ),
) -> None:
    """Start a new experiment run."""
    prepared = prepare_experiment_from_file(config_file)

    print_run_info(prepared)

    summary = execute_prepared_experiment(prepared)

    print_run_info(prepared)
    print_run_summary(summary)


@app.command("status")
def status(
    run_directory: Path = _run_directory_option(),
    watch_seconds: float | None = typer.Option(
        None,
        "--watch",
        min=0.5,
        help="Refresh continuously at this interval in seconds.",
    ),
) -> None:
    """Show persisted progress for an experiment run."""
    terminal_states = {"paused", "completed", "failed", "interrupted"}

    while True:
        if watch_seconds is not None:
            console.clear()
        try:
            current_status = show_run_status(run_directory)
        except (OSError, ValueError) as error:
            typer.echo(str(error), err=True)
            raise typer.Exit(code=1) from error

        if watch_seconds is None or current_status in terminal_states:
            return
        time.sleep(watch_seconds)


@app.command("pause")
def pause(
    run_directory: Path = _run_directory_option(),
) -> None:
    """Request a cooperative pause after the current adapter call."""
    try:
        record = request_run_pause(database_path_for_run(run_directory))
    except (OSError, ValueError) as error:
        typer.echo(str(error), err=True)
        raise typer.Exit(code=1) from error

    typer.echo(f"Run status: {record.status}")
    typer.echo("The pipeline will pause before starting its next task.")


@app.command("resume")
def resume(
    run_directory: Path = _run_directory_option(),
) -> None:
    """Resume a paused, interrupted, or failed run."""
    try:
        summary = resume_experiment(run_directory)
    except (OSError, ValueError) as error:
        typer.echo(str(error), err=True)
        raise typer.Exit(code=1) from error

    print_run_summary(summary)


@app.command("evaluate")
def evaluate(
    run_directory: Path = _run_directory_option(),
) -> None:
    """Placeholder for evaluating a completed experiment run."""
    typer.echo(f"Would evaluate {run_directory}")
