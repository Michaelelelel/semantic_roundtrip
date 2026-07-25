"""Commands for planning and managing persisted experiment jobs."""

from pathlib import Path

import typer

from semantic_roundtrip.cli.common import (
    EXPECTED_COMMAND_ERRORS,
    exit_with_error,
    watch_status,
)
from semantic_roundtrip.cli.job.output import (
    print_job_execution_summary,
    print_job_info,
    print_job_pause_summary,
    print_job_plan,
    show_job_status,
)
from semantic_roundtrip.job import load_job_config, plan_job
from semantic_roundtrip.job_runner import (
    execute_job,
    load_prepared_job,
    prepare_job,
    request_job_pause,
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
    except EXPECTED_COMMAND_ERRORS as error:
        exit_with_error(error)

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
        exit_with_error(
            error,
            code=130,
            message="Job interrupted safely.",
        )
    except EXPECTED_COMMAND_ERRORS as error:
        exit_with_error(error)

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
    try:
        watch_status(
            job_directory,
            render=show_job_status,
            interval_seconds=watch_seconds,
        )
    except KeyboardInterrupt as error:
        exit_with_error(
            error,
            code=130,
            message="Job status watch stopped.",
        )
    except EXPECTED_COMMAND_ERRORS as error:
        exit_with_error(error)


@app.command("pause")
def pause(job_directory: Path = _job_directory_option()) -> None:
    """Request a cooperative pause from the job's active child run."""
    try:
        summary = request_job_pause(job_directory)
    except EXPECTED_COMMAND_ERRORS as error:
        exit_with_error(error)

    print_job_pause_summary(summary)


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
        exit_with_error(
            error,
            code=130,
            message="Job interrupted safely.",
        )
    except EXPECTED_COMMAND_ERRORS as error:
        exit_with_error(error)

    print_job_execution_summary(summary)
    if summary.status == "failed":
        raise typer.Exit(code=1)


@app.command("evaluate")
def evaluate(job_directory: Path = _job_directory_option()) -> None:
    """Evaluate"""
    print("Evaluating job...")
