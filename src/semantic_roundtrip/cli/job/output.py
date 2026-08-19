"""Terminal presentation for persisted experiment jobs."""

from pathlib import Path

import typer
from rich.table import Table

from semantic_roundtrip.cli.common import console
from semantic_roundtrip.cli.status_output import (
    format_duration,
    format_eta,
    format_stage,
    format_timestamp,
)
from semantic_roundtrip.job import JobPlan
from semantic_roundtrip.job.runner import (
    JobExecutionSummary,
    JobPauseSummary,
    PreparedJob,
)
from semantic_roundtrip.status.jobs import get_job_status
from semantic_roundtrip.status.models import (
    JobDiscoveryResult,
    JobStatus,
)


def print_job_plan(plan: JobPlan) -> bool:
    """Print expected work and return whether preflight issues were found."""
    typer.echo(f"Job: {plan.name}")
    typer.echo(f"Experiment entries: {len(plan.entries)}")
    typer.echo(
        "Expected outputs: "
        f"prompts={plan.expected_outputs['prompt_generation']}, "
        f"images={plan.expected_outputs['image_generation']}, "
        f"verifications={plan.expected_outputs['verification']}, "
        f"direct guesses={plan.expected_outputs['title_guessing_direct']}, "
        f"descriptions={plan.expected_outputs['image_description']}, "
        "description guesses="
        f"{plan.expected_outputs['title_guessing_from_description']}, "
        f"evaluations={plan.expected_outputs['evaluation']}"
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

    typer.echo("Created child runs:")
    for configured_entry, run_directory in zip(
        prepared.config.entries,
        prepared.run_directories,
        strict=True,
    ):
        typer.echo(
            f"  [{configured_entry.index + 1}/{len(prepared.run_directories)}] "
            f"{configured_entry.name}: {run_directory}"
        )


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


def print_job_pause_summary(summary: JobPauseSummary) -> None:
    """Print the child run that will cooperatively pause the job."""
    typer.echo(f"Job ID: {summary.job_id}")
    typer.echo(f"Job directory: {summary.job_directory}")
    typer.echo(f"Active entry: {summary.entry_index + 1} ({summary.entry_name})")
    typer.echo(f"Child run: {summary.child_run_id}")
    typer.echo(f"Child directory: {summary.child_directory}")
    typer.echo(f"Child run status: {summary.child_status}")
    if summary.child_status == "paused":
        typer.echo("The job is safely paused and can be resumed.")
    else:
        typer.echo("The job will stop before starting another child run.")


def show_job_status(job_directory: Path) -> str:
    """Print job and child-run states from their read-only databases."""
    status = get_job_status(job_directory)

    console.print(f"[bold]Job:[/bold] {status.name} ({status.job_id})")
    console.print(f"[bold]Status:[/bold] {status.status}")
    if status.failed_tasks:
        console.print(f"[bold red]Failed tasks:[/bold red] {status.failed_tasks}")
    if status.started_at is not None:
        console.print(f"[bold]Started:[/bold] {format_timestamp(status.started_at)}")
        console.print(
            f"[bold]Elapsed:[/bold] {format_duration(status.elapsed_seconds)}"
        )
    if status.active_entry_name is not None:
        console.print(f"[bold]Active entry:[/bold] {status.active_entry_name}")
    if status.active_stage is not None:
        console.print(f"[bold]Active stage:[/bold] {format_stage(status.active_stage)}")
        console.print(
            "[bold]Estimated remaining:[/bold] "
            f"{format_eta(status.eta_state, status.eta_seconds)}"
        )
    if status.last_update is not None:
        console.print(
            f"[bold]Last update:[/bold] {format_timestamp(status.last_update)}"
        )

    table = Table()
    table.add_column("#", justify="right")
    table.add_column("Entry")
    table.add_column("Job state")
    table.add_column("Child state")
    table.add_column("Run")
    table.add_column("Models")
    table.add_column("Last error")

    for entry in status.entries:
        run_name = entry.run_directory.name
        child_status = entry.child.status
        if entry.failed_tasks:
            child_status += f" ({entry.failed_tasks} failed)"
        table.add_row(
            str(entry.index + 1),
            entry.name,
            entry.status,
            child_status,
            run_name,
            ", ".join(entry.models),
            entry.last_error or "-",
        )

    console.print(table)
    return status.status


def show_job_list(
    results: list[JobDiscoveryResult],
    *,
    root: Path,
) -> None:
    """Print discovered jobs and their current child-run progress."""
    console.print(f"[bold]Jobs:[/bold] {root}")
    if not results:
        console.print("No jobs found.")
        return

    table = Table()
    table.add_column("Status")
    table.add_column("Job")
    table.add_column("Job ID")
    table.add_column("Started / created")
    table.add_column("Elapsed", justify="right")
    table.add_column("Updated")
    table.add_column("Runs", justify="right")
    table.add_column("Active run")
    table.add_column("Stage")
    table.add_column("ETA")
    table.add_column("Last error")

    for result in results:
        if not isinstance(result, JobStatus):
            table.add_row(
                result.status,
                result.directory.name,
                "-",
                "-",
                "-",
                "-",
                "-",
                "-",
                "-",
                "-",
                result.error,
            )
            continue

        active_run = result.active_entry_name or "-"
        if result.active_run_id is not None:
            active_run = f"{active_run} ({result.active_run_id})"
        displayed_status = result.status
        if result.failed_tasks:
            displayed_status += f" ({result.failed_tasks} failed)"
        table.add_row(
            displayed_status,
            result.name,
            result.job_id,
            format_timestamp(result.started_at or result.created_at),
            format_duration(result.elapsed_seconds),
            format_timestamp(result.last_update),
            f"{result.completed_entries}/{result.total_entries}",
            active_run,
            format_stage(result.active_stage),
            format_eta(result.eta_state, result.eta_seconds),
            result.last_error or "-",
        )

    console.print(table)
