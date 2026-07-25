"""Root command-line application."""

import typer

from semantic_roundtrip.cli.job import app as job_app
from semantic_roundtrip.cli.run import app as run_app


app = typer.Typer(
    help="Run and manage semantic round-trip experiments.",
    no_args_is_help=True,
)
app.add_typer(run_app, name="run")
app.add_typer(job_app, name="job")


if __name__ == "__main__":
    app()
