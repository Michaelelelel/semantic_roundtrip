"""Terminal presentation for individual experiment runs."""

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
from semantic_roundtrip.experiment_runner import (
    PreparedExperiment,
    RunPauseSummary,
)
from semantic_roundtrip.pipeline import PipelineSummary
from semantic_roundtrip.status.models import RunDiscoveryResult, RunStatus
from semantic_roundtrip.status.runs import get_run_status


def print_run_info(prepared: PreparedExperiment) -> None:
    """Print artifacts created while preparing a new run."""
    typer.echo(f"Experiment name: {prepared.config.run.name}")
    typer.echo(f"Run ID: {prepared.run_context.run_id}")
    typer.echo(f"Run directory: {prepared.run_context.directory}")
    typer.echo(f"Database: {prepared.database_path}")
    typer.echo(f"Manifest: {prepared.manifest_path}")


def print_run_summary(summary: PipelineSummary) -> None:
    """Print final result counts for one run invocation."""
    typer.echo(f"Run status: {summary.status}")
    typer.echo(f"Dataset items: {summary.dataset_items}")
    typer.echo(f"Illustratability ratings: {summary.illustratability_ratings}")
    typer.echo(f"Prompts: {summary.prompts}")
    typer.echo(f"Images: {summary.images}")
    typer.echo(f"Verifications: {summary.verifications}")
    typer.echo(f"Image descriptions: {summary.image_descriptions}")
    typer.echo(f"Predictions: {summary.predictions}")
    typer.echo(f"Failed tasks: {summary.failed_tasks}")


def print_run_pause_summary(summary: RunPauseSummary) -> None:
    """Print the persisted state after requesting a cooperative pause."""
    typer.echo(f"Run status: {summary.status}")
    if summary.status == "paused":
        typer.echo("The run is safely paused and can be resumed.")
    else:
        typer.echo("The pipeline will pause before starting its next task.")


def show_run_status(run_directory: Path) -> str:
    """Print persisted run progress and return its lifecycle state."""
    status = get_run_status(run_directory)

    console.print(f"[bold]Run:[/bold] {status.name} ({status.run_id})")
    console.print(f"[bold]Status:[/bold] {status.status}")
    if status.failed_tasks:
        console.print(f"[bold red]Failed tasks:[/bold red] {status.failed_tasks}")
    if status.started_at is not None:
        console.print(f"[bold]Started:[/bold] {format_timestamp(status.started_at)}")
        console.print(
            f"[bold]Elapsed:[/bold] {format_duration(status.elapsed_seconds)}"
        )
    if status.status == "pausing":
        console.print(
            "[yellow]Pause requested; waiting for a safe checkpoint.[/yellow]"
        )
    elif status.status == "paused":
        console.print("[yellow]Run is safely paused and can be resumed.[/yellow]")
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
    table.add_column("Stage")
    table.add_column("Origin")
    table.add_column("Produced", justify="right")
    table.add_column("Expected", justify="right")
    table.add_column("Pending tasks", justify="right")
    table.add_column("Running tasks", justify="right")
    table.add_column("Failed tasks", justify="right")

    for stage in status.stages:
        table.add_row(
            format_stage(stage.name),
            "imported" if stage.imported else "local",
            str(stage.produced),
            str(stage.expected),
            str(stage.pending),
            str(stage.running),
            str(stage.failed),
        )

    console.print(table)
    return status.status


def show_run_list(
    results: list[RunDiscoveryResult],
    *,
    root: Path,
) -> None:
    """Print compact standalone-run summaries with copyable, untruncated IDs."""
    typer.echo(f"Standalone runs: {root}")
    if not results:
        typer.echo("No standalone runs found.")
        return

    for result in results:
        typer.echo()
        if not isinstance(result, RunStatus):
            typer.echo(result.directory.name)
            typer.echo(result.status)
            typer.echo(f"Directory: {result.directory}")
            typer.echo(f"Last error: {result.error}")
            continue

        typer.echo(result.name)
        displayed_status = result.status
        if result.failed_tasks:
            displayed_status += f" ({result.failed_tasks} failed)"
        typer.echo(f"{displayed_status} | {format_duration(result.elapsed_seconds)}")
        typer.echo(f"Run ID: {result.run_id}")
        active = next(
            (stage for stage in result.stages if stage.name == result.active_stage),
            None,
        )
        progress = "-" if active is None else f"{active.produced}/{active.expected}"
        if result.active_stage is not None or result.eta_state != "none":
            typer.echo(
                f"Stage: {format_stage(result.active_stage)} | {progress} | "
                f"ETA: {format_eta(result.eta_state, result.eta_seconds)}"
            )
        if result.last_error:
            typer.echo(f"Last error: {result.last_error}")
