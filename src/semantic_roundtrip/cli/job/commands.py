"""Commands for planning and managing persisted experiment jobs."""

import time
from pathlib import Path

import typer

from semantic_roundtrip.cli.common import console
from semantic_roundtrip.cli.job.output import (
    print_job_execution_summary,
    print_job_info,
    print_job_plan,
    show_job_status,
)
from semantic_roundtrip.job import load_job_config, plan_job
from semantic_roundtrip.job_runner import (
    execute_job,
    load_prepared_job,
    prepare_job,
)


app = typer.Typer(
    help="Plan and manage a persisted collection of experiment runs.",
    no_args_is_help=True,
)


def _job_config_option() -> Path:
    """Create the shared option for selecting a job configuration."""
    return typer.Option(
        ...,
        "--config",
        "-c",
        exists=True,
        file_okay=True,
        dir_okay=False,
        resolve_path=True,
        help="Job configuration file.",
    )


def _job_directory_option() -> Path:
    """Create the shared option for selecting an existing job directory."""
    return typer.Option(
        ...,
        "--job",
        "-j",
        exists=True,
        file_okay=False,
        dir_okay=True,
        resolve_path=True,
        help="Existing job directory.",
    )


@app.command("plan")
def plan(config_path: Path = _job_config_option()) -> None:
    """Validate a job and display its expected work without creating artifacts."""
    try:
        loaded = load_job_config(config_path)
        job_plan = plan_job(loaded)
    except (OSError, ValueError) as error:
        typer.echo(str(error), err=True)
        raise typer.Exit(code=1) from error

    if print_job_plan(job_plan):
        raise typer.Exit(code=1)


@app.command("start")
def start(config_path: Path = _job_config_option()) -> None:
    """Create and execute a new persisted job."""
    try:
        prepared = prepare_job(config_path)
        print_job_info(prepared)
        summary = execute_job(prepared, report=typer.echo)
    except KeyboardInterrupt as error:
        typer.echo("Job interrupted safely.", err=True)
        raise typer.Exit(code=130) from error
    except (OSError, ValueError) as error:
        typer.echo(str(error), err=True)
        raise typer.Exit(code=1) from error

    print_job_execution_summary(summary)
    if summary.status == "failed":
        raise typer.Exit(code=1)


@app.command("status")
def status(
    job_directory: Path = _job_directory_option(),
    watch_seconds: float | None = typer.Option(
        None,
        "--watch",
        min=0.5,
        help="Refresh continuously at this interval in seconds.",
    ),
) -> None:
    """Show persisted job and child-run states."""
    terminal_states = {"paused", "completed", "failed", "interrupted"}
    while True:
        if watch_seconds is not None:
            console.clear()
        try:
            current_status = show_job_status(job_directory)
        except (OSError, ValueError) as error:
            typer.echo(str(error), err=True)
            raise typer.Exit(code=1) from error

        if watch_seconds is None or current_status in terminal_states:
            return
        time.sleep(watch_seconds)


@app.command("pause")
def pause(job_directory: Path = _job_directory_option()) -> None:
    """Placeholder for pausing a job at a safe boundary."""
    typer.echo(f"Would pause {job_directory}")


@app.command("resume")
def resume(job_directory: Path = _job_directory_option()) -> None:
    """Resume incomplete entries without repeating completed runs."""
    try:
        prepared = load_prepared_job(job_directory)
        summary = execute_job(
            prepared,
            resume=True,
            report=typer.echo,
        )
    except KeyboardInterrupt as error:
        typer.echo("Job interrupted safely.", err=True)
        raise typer.Exit(code=130) from error
    except (OSError, ValueError) as error:
        typer.echo(str(error), err=True)
        raise typer.Exit(code=1) from error

    print_job_execution_summary(summary)
    if summary.status == "failed":
        raise typer.Exit(code=1)


@app.command("evaluate")
def evaluate(job_directory: Path = _job_directory_option()) -> None:
    """Placeholder for evaluating all completed runs in a job."""
    typer.echo(f"Would evaluate {job_directory}")
