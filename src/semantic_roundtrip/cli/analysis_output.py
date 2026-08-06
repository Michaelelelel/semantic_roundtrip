"""Terminal output shared by run and job analysis commands."""

import typer

from semantic_roundtrip.analysis import AnalysisResult


def print_analysis_result(result: AnalysisResult) -> None:
    """Print the location and central row counts of one analysis export."""
    typer.echo(f"Analyzed {result.scope}: {result.source_id}")
    typer.echo(f"Analysis directory: {result.output_directory}")
    typer.echo(f"Prediction rows: {result.prediction_rows}")
    typer.echo(f"Title rows: {result.title_rows}")
    typer.echo(f"Summary rows: {result.summary_rows}")
    typer.echo(f"Generated files: {len(result.generated_files)}")
