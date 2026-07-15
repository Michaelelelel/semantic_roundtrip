from pathlib import Path

import typer

from semantic_roundtrip.config import load_config
from semantic_roundtrip.persistence.run_manager import create_run, create_config_snapshot

app = typer.Typer(
    help="Run semantic round-trip experiments."
)


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

    print(config.run.output_directory)


    run_context = create_run(
        config.run.output_directory,
        config.run.name,
    )
    snapshot_path = create_config_snapshot(
        config,
        run_context.directory,
    )

    typer.echo("Configuration is valid.")
    typer.echo(f"Experiment name: {config.run.name}")
    typer.echo(f"Run ID: {run_context.run_id}")
    typer.echo(f"Run directory: {run_context.directory}")


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
