"""Terminal presentation for individual experiment runs."""

from pathlib import Path

import typer
from rich.table import Table

from semantic_roundtrip.cli.common import console
from semantic_roundtrip.config_resolution import (
    expected_stage_outputs,
    load_effective_config,
)
from semantic_roundtrip.experiment_runner import PreparedExperiment
from semantic_roundtrip.persistence.config_snapshot import EFFECTIVE_CONFIG_FILENAME
from semantic_roundtrip.persistence.database import (
    RunRecord,
    database_path_for_run,
    read_run_record,
    read_stage_progress,
)
from semantic_roundtrip.pipeline import PipelineSummary


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
    typer.echo(f"Prompts: {summary.prompts}")
    typer.echo(f"Images: {summary.images}")
    typer.echo(f"Verifications: {summary.verifications}")
    typer.echo(f"Predictions: {summary.predictions}")
    typer.echo(f"Evaluations: {summary.evaluations}")


def print_run_pause_summary(record: RunRecord) -> None:
    """Print the persisted state after requesting a cooperative pause."""
    typer.echo(f"Run status: {record.status}")
    if record.status == "paused":
        typer.echo("The run is safely paused and can be resumed.")
    else:
        typer.echo("The pipeline will pause before starting its next task.")


def show_run_status(run_directory: Path) -> str:
    """Print persisted run progress and return its lifecycle state."""
    database_path = database_path_for_run(run_directory)
    record = read_run_record(database_path)
    config = load_effective_config(run_directory / EFFECTIVE_CONFIG_FILENAME)
    expected = expected_stage_outputs(config)
    progress = {stage.stage: stage for stage in read_stage_progress(database_path)}

    console.print(f"[bold]Run:[/bold] {record.name} ({record.run_id})")
    console.print(f"[bold]Status:[/bold] {record.status}")
    if record.status == "pausing":
        console.print(
            "[yellow]Pause requested; waiting for a safe checkpoint.[/yellow]"
        )
    elif record.status == "paused":
        console.print("[yellow]Run is safely paused and can be resumed.[/yellow]")
    if record.heartbeat_at is not None:
        console.print(f"[bold]Last update:[/bold] {record.heartbeat_at.isoformat()}")

    table = Table()
    table.add_column("Stage")
    table.add_column("Produced", justify="right")
    table.add_column("Expected", justify="right")
    table.add_column("Pending tasks", justify="right")
    table.add_column("Running tasks", justify="right")
    table.add_column("Failed tasks", justify="right")

    labels = {
        "prompt_generation": "Prompt generation",
        "image_generation": "Image generation",
        "verification": "Verification",
        "title_guessing": "Title guessing",
    }
    for stage_name, label in labels.items():
        stage = progress.get(stage_name)
        table.add_row(
            label,
            str(stage.produced_outputs if stage else 0),
            str(expected[stage_name]),
            str(stage.pending if stage else 0),
            str(stage.running if stage else 0),
            str(stage.failed if stage else 0),
        )

    console.print(table)
    return record.status
