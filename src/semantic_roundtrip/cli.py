import typer
from pathlib import Path

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
    typer.echo(f"Would run experiment using {config}")


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