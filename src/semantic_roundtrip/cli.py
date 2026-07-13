import typer
from pathlib import Path

from semantic_roundtrip.config import load_config

app = typer.Typer(
    help="Run semantic round-trip experiments."
)


@app.command()
def run(
    config: Path = typer.Option(
        ...,
        "--config",
        "-c",
        help="Experiment configuration file.",
    ),
) -> None:
    """Run an experiment."""

    config = load_config(config)



    typer.echo("Configuration is valid.")
    typer.echo(f"Experiment name: {config.run.name}")


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