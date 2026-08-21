"""Command for producing final study tables and figures."""

from pathlib import Path

import typer

from semantic_roundtrip.analysis import analyze_study
from semantic_roundtrip.cli.common import EXPECTED_COMMAND_ERRORS, exit_with_error


app = typer.Typer(
    help="Analyze selected completed runs from one study directory.",
    no_args_is_help=True,
)


def _study_directory_option() -> Path:
    return typer.Option(
        ...,
        "--study",
        "-s",
        exists=True,
        file_okay=False,
        dir_okay=True,
        resolve_path=True,
        help="Directory containing study.yaml.",
    )


@app.command("analyze")
def analyze(
    study_directory: Path = _study_directory_option(),
    force: bool = typer.Option(
        False,
        "--force",
        help="Replace an existing results directory atomically.",
    ),
) -> None:
    """Create reproducible tables and figures for the declared study groups."""
    try:
        result = analyze_study(study_directory, force=force)
    except EXPECTED_COMMAND_ERRORS as error:
        exit_with_error(error)

    typer.echo(f"Study: {result.study_name}")
    typer.echo(f"Results: {result.output_directory}")
    typer.echo(f"Conditions: {result.condition_count}")
    typer.echo(f"Observations: {result.observation_rows}")
    typer.echo(f"Titles: {result.title_rows}")
    typer.echo(f"Summaries: {result.summary_rows}")
    typer.echo(f"Comparisons: {result.comparison_rows}")
    typer.echo(f"Generated files: {len(result.generated_files)}")
