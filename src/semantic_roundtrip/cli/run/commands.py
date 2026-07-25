"""Commands for starting and managing individual experiment runs."""

from pathlib import Path

import typer

from semantic_roundtrip.cli.common import (
    EXPECTED_COMMAND_ERRORS,
    exit_with_error,
    watch_status,
)
from semantic_roundtrip.cli.run.output import (
    print_run_info,
    print_run_pause_summary,
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
    config_path: Path = typer.Option(
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
    try:
        prepared = prepare_experiment_from_file(config_path)
        print_run_info(prepared)
        summary = execute_prepared_experiment(prepared)
    except KeyboardInterrupt as error:
        exit_with_error(
            error,
            code=130,
            message="Run interrupted safely.",
        )
    except EXPECTED_COMMAND_ERRORS as error:
        exit_with_error(error)

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
    try:
        watch_status(
            run_directory,
            render=show_run_status,
            interval_seconds=watch_seconds,
        )
    except KeyboardInterrupt as error:
        exit_with_error(
            error,
            code=130,
            message="Run status watch stopped.",
        )
    except EXPECTED_COMMAND_ERRORS as error:
        exit_with_error(error)


@app.command("pause")
def pause(
    run_directory: Path = _run_directory_option(),
) -> None:
    """Request a cooperative pause after the current adapter call."""
    try:
        record = request_run_pause(database_path_for_run(run_directory))
    except EXPECTED_COMMAND_ERRORS as error:
        exit_with_error(error)

    print_run_pause_summary(record)


@app.command("resume")
def resume(
    run_directory: Path = _run_directory_option(),
) -> None:
    """Resume a paused, interrupted, or failed run."""
    try:
        summary = resume_experiment(run_directory)
    except KeyboardInterrupt as error:
        exit_with_error(
            error,
            code=130,
            message="Run interrupted safely.",
        )
    except EXPECTED_COMMAND_ERRORS as error:
        exit_with_error(error)

    print_run_summary(summary)


@app.command("evaluate")
def evaluate(
    run_directory: Path = _run_directory_option(),
) -> None:
    """ Evalute"""
    print("Evaluate")
