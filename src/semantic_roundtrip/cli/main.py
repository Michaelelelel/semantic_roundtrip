"""Root command-line application."""

import typer

from semantic_roundtrip.cli.common import install_termination_handler
from semantic_roundtrip.cli.job import app as job_app
from semantic_roundtrip.cli.run import app as run_app
from semantic_roundtrip.cli.study import app as study_app


app = typer.Typer(
    help="Run and manage semantic round-trip experiments.",
    no_args_is_help=True,
)
app.add_typer(run_app, name="run")
app.add_typer(job_app, name="job")
app.add_typer(study_app, name="study")


@app.callback()
def configure_cli() -> None:
    """Install process behavior shared by every command group."""
    install_termination_handler()


if __name__ == "__main__":
    app()
