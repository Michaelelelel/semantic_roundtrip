"""Terminal presentation for persisted experiment jobs."""

from pathlib import Path

import typer
from rich.table import Table

from semantic_roundtrip.cli.common import console
from semantic_roundtrip.job import JOB_SNAPSHOT_FILENAME, JobPlan, load_job_snapshot
from semantic_roundtrip.job_runner import JobExecutionSummary, PreparedJob
from semantic_roundtrip.persistence.database import (
    database_path_for_run,
    read_run_record,
)
from semantic_roundtrip.persistence.job_database import (
    job_database_path,
    read_job_entries,
    read_job_record,
)


def print_job_plan(plan: JobPlan) -> bool:
    """Print expected work and return whether preflight issues were found."""
    typer.echo(f"Job: {plan.name}")
    typer.echo(f"Experiment entries: {len(plan.entries)}")
    typer.echo(
        "Expected calls: "
        f"prompts={plan.expected_outputs['prompt_generation']}, "
        f"images={plan.expected_outputs['image_generation']}, "
        f"verifications={plan.expected_outputs['verification']}, "
        f"title guesses={plan.expected_outputs['title_guessing']}"
    )

    table = Table()
    table.add_column("#", justify="right")
    table.add_column("Entry")
    table.add_column("Prompts", justify="right")
    table.add_column("Images", justify="right")
    table.add_column("Backend/model stack")
    for entry in plan.entries:
        stack = ", ".join(
            f"{backend.alias}={backend.model_id or backend.adapter}"
            for backend in entry.backends
        )
        table.add_row(
            str(entry.index + 1),
            entry.name,
            str(entry.expected_outputs["prompt_generation"]),
            str(entry.expected_outputs["image_generation"]),
            stack,
        )
    console.print(table)

    typer.echo("Estimated model-stack order:")
    for index, stack in enumerate(plan.model_stacks, start=1):
        typer.echo(f"  {index}. {stack}")

    if plan.missing_credentials:
        typer.echo(
            "Missing credential environment variables: "
            + ", ".join(plan.missing_credentials),
            err=True,
        )
    if plan.missing_runtime_models:
        typer.echo(
            "Models missing from deployment catalogs: "
            + ", ".join(plan.missing_runtime_models),
            err=True,
        )

    has_preflight_issues = bool(plan.missing_credentials or plan.missing_runtime_models)
    if not has_preflight_issues:
        typer.echo("Preflight warnings: none")
    return has_preflight_issues


def print_job_info(prepared: PreparedJob) -> None:
    """Print the artifacts created while preparing a new job."""
    typer.echo(f"Job: {prepared.config.job.name}")
    typer.echo(f"Job ID: {prepared.context.job_id}")
    typer.echo(f"Job directory: {prepared.context.directory}")
    typer.echo(f"Database: {prepared.database_path}")
    typer.echo(f"Snapshot: {prepared.effective_config_path}")


def print_job_execution_summary(summary: JobExecutionSummary) -> None:
    """Print final entry counts for one job invocation."""
    typer.echo(f"Job ID: {summary.job_id}")
    typer.echo(f"Job directory: {summary.directory}")
    typer.echo(f"Job status: {summary.status}")
    typer.echo(f"Completed entries: {summary.completed}")
    typer.echo(f"Failed entries: {summary.failed}")
    typer.echo(f"Pending entries: {summary.pending}")
    typer.echo(f"Paused entries: {summary.paused}")
    typer.echo(f"Interrupted entries: {summary.interrupted}")


def show_job_status(job_directory: Path) -> str:
    """Print job and child-run states from their read-only databases."""
    database_path = job_database_path(job_directory)
    record = read_job_record(database_path)
    entries = read_job_entries(database_path, job_directory)
    config = load_job_snapshot(job_directory / JOB_SNAPSHOT_FILENAME)

    console.print(f"[bold]Job:[/bold] {record.name} ({record.job_id})")
    console.print(f"[bold]Status:[/bold] {record.status}")
    if record.heartbeat_at is not None:
        console.print(f"[bold]Last update:[/bold] {record.heartbeat_at.isoformat()}")

    table = Table()
    table.add_column("#", justify="right")
    table.add_column("Entry")
    table.add_column("Job state")
    table.add_column("Child state")
    table.add_column("Run")
    table.add_column("Models")
    table.add_column("Last error")

    for entry in entries:
        configured_entry = config.entries[entry.entry_index]
        run_name = entry.run_directory.name
        try:
            child_status = read_run_record(
                database_path_for_run(entry.run_directory)
            ).status
        except (OSError, ValueError):
            child_status = "unavailable"

        models = ", ".join(
            backend.model_id or backend.adapter for backend in configured_entry.backends
        )
        last_error = (
            "-"
            if entry.error_message is None
            else f"{entry.error_type}: {entry.error_message}"
        )
        table.add_row(
            str(entry.entry_index + 1),
            configured_entry.name,
            entry.status,
            child_status,
            run_name,
            models,
            last_error,
        )

    console.print(table)
    return record.status
