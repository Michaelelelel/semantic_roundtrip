from pathlib import Path

import typer

from semantic_roundtrip.adapters.factory import create_adapters
from semantic_roundtrip.config import load_config
from semantic_roundtrip.pipeline import run_pipeline
from semantic_roundtrip.persistence.config_snapshot import (
    create_effective_config_snapshot,
    create_input_config_snapshot,
)
from semantic_roundtrip.persistence.database import initialize_database
from semantic_roundtrip.persistence.manifest import create_manifest
from semantic_roundtrip.persistence.run_manager import create_run

app = typer.Typer(help="Run semantic round-trip experiments.")


@app.command()
def run(
    config_file: Path = typer.Option(
        ...,
        "--config",
        "-c",
        exists=True,
        file_okay=True,
        dir_okay=False,
        help="Experiment configuration file.",
    ),
) -> None:
    """Run an experiment."""
    config = load_config(config_file)
    adapters = create_adapters(config.stages)

    run_context = create_run(
        config.run.output_directory,
        config.run.name,
    )

    input_config_path = create_input_config_snapshot(
        config_file,
        run_context.directory,
    )
    effective_config_path = create_effective_config_snapshot(
        config,
        run_context.directory,
    )
    images_directory = run_context.directory / "images"
    images_directory.mkdir()
    database_path = initialize_database(
        run_context,
        config.run.name,
        input_config_path,
        effective_config_path,
    )
    manifest_path = create_manifest(
        run_context,
        config.run.name,
        input_config_path,
        effective_config_path,
        database_path,
        images_directory,
    )

    typer.echo(f"Experiment name: {config.run.name}")
    typer.echo(f"Run ID: {run_context.run_id}")
    typer.echo(f"Run directory: {run_context.directory}")
    typer.echo(f"Database: {database_path}")
    typer.echo(f"Manifest: {manifest_path}")

    summary = run_pipeline(
        config=config,
        run_context=run_context,
        database_path=database_path,
        images_directory=images_directory,
        adapters=adapters,
    )

    typer.echo("Experiment completed.")
    typer.echo(f"Dataset items: {summary.dataset_items}")
    typer.echo(f"Prompts: {summary.prompts}")
    typer.echo(f"Images: {summary.images}")
    typer.echo(f"Predictions: {summary.predictions}")


@app.command()
def evaluate(
    run_directory: Path = typer.Option(
        ...,
        "--run",
        "-r",
        help="Directory of a completed run.",
    ),
) -> None:
    """Evaluate a completed experiment."""
    typer.echo(f"Would evaluate {run_directory}")


if __name__ == "__main__":
    app()
