from pathlib import Path

import typer
from rich.table import Table
from rich.console import Console

from semantic_roundtrip.config import AppConfig, load_config
from semantic_roundtrip.persistence.config_snapshot import EFFECTIVE_CONFIG_FILENAME
from semantic_roundtrip.persistence.database import (
    database_path_for_run,
    read_run_record,
    read_stage_progress,
)
from semantic_roundtrip.persistence.run_manager import RunContext
from semantic_roundtrip.pipeline import PipelineSummary


console = Console()


def _print_run_info(
    config: AppConfig, database_path: Path, manifest_path: Path, run_context: RunContext
):
    typer.echo(f"Experiment name: {config.run.name}")
    typer.echo(f"Run ID: {run_context.run_id}")
    typer.echo(f"Run directory: {run_context.directory}")
    typer.echo(f"Database: {database_path}")
    typer.echo(f"Manifest: {manifest_path}")


def _print_run_summary(summary: PipelineSummary) -> None:
    typer.echo(f"Run status: {summary.status}")
    typer.echo(f"Dataset items: {summary.dataset_items}")
    typer.echo(f"Prompts: {summary.prompts}")
    typer.echo(f"Images: {summary.images}")
    typer.echo(f"Verifications: {summary.verifications}")
    typer.echo(f"Predictions: {summary.predictions}")
    typer.echo(f"Evaluations: {summary.evaluations}")


def _expected_stage_outputs(config: AppConfig) -> dict[str, int]:
    prompt_count = len(config.dataset.items) * config.experiment.prompts_per_title
    image_count = prompt_count * len(config.experiment.image_seeds)
    return {
        "prompt_generation": prompt_count,
        "image_generation": image_count,
        "verification": image_count,
        "title_guessing": image_count,
    }


def _show_status(run_directory: Path) -> str:
    database_path = database_path_for_run(run_directory)
    record = read_run_record(database_path)
    config = load_config(run_directory / EFFECTIVE_CONFIG_FILENAME)
    expected = _expected_stage_outputs(config)
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
