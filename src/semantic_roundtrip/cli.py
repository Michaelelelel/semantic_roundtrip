"""Command-line interface for semantic round-trip experiments."""

import time
from pathlib import Path

import typer

from semantic_roundtrip.adapters.factory import create_adapters
from semantic_roundtrip.cli_helper import (
    _print_run_info,
    _print_run_summary,
    _show_status,
    console,
)
from semantic_roundtrip.config import load_config
from semantic_roundtrip.pipeline import run_pipeline
from semantic_roundtrip.persistence.config_snapshot import (
    EFFECTIVE_CONFIG_FILENAME,
    PROMPT_PROFILE_FILENAME,
    create_effective_config_snapshot,
    create_input_config_snapshot,
    create_prompt_profile_snapshot,
)
from semantic_roundtrip.persistence.database import (
    database_path_for_run,
    load_run_context,
    read_run_record,
    request_run_pause,
    initialize_database,
)
from semantic_roundtrip.persistence.manifest import create_manifest
from semantic_roundtrip.persistence.run_manager import create_run
from semantic_roundtrip.prompting import load_prompt_profile

app = typer.Typer(help="Run and monitor semantic round-trip experiments.")


def _run_directory_option() -> Path:
    return typer.Option(
        ...,
        "--run",
        "-r",
        exists=True,
        file_okay=False,
        dir_okay=True,
        resolve_path=True,
        help="Existing experiment run directory.",
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
        resolve_path=True,
        help="Experiment configuration file.",
    ),
) -> None:
    """Run an experiment."""
    config = load_config(config_file)
    loaded_prompt_profile = load_prompt_profile(config.experiment.prompt_profile)
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
    prompt_profile_path = create_prompt_profile_snapshot(
        loaded_prompt_profile,
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
        prompt_profile_path,
        loaded_prompt_profile,
    )

    _print_run_info(config, database_path, manifest_path, run_context)

    summary = run_pipeline(
        config=config,
        run_context=run_context,
        database_path=database_path,
        images_directory=images_directory,
        adapters=adapters,
        prompt_profile=loaded_prompt_profile.profile,
    )
    _print_run_info(config, database_path, manifest_path, run_context)
    _print_run_summary(summary)



@app.command()
def status(
    run_directory: Path = _run_directory_option(),
    watch_seconds: float | None = typer.Option(
        None,
        "--watch",
        min=0.5,
        help="Refresh continuously at this interval in seconds.",
    ),
) -> None:
    """Show persisted progress for an experiment run."""
    terminal_states = {"paused", "completed", "failed", "interrupted"}

    while True:
        if watch_seconds is not None:
            console.clear()
        try:
            current_status = _show_status(run_directory)
        except (OSError, ValueError) as error:
            typer.echo(str(error), err=True)
            raise typer.Exit(code=1) from error

        if watch_seconds is None or current_status in terminal_states:
            return
        time.sleep(watch_seconds)


@app.command()
def pause(
    run_directory: Path = _run_directory_option(),
) -> None:
    """Request a cooperative pause after the current adapter call."""
    try:
        record = request_run_pause(database_path_for_run(run_directory))
    except (OSError, ValueError) as error:
        typer.echo(str(error), err=True)
        raise typer.Exit(code=1) from error

    typer.echo(f"Run status: {record.status}")
    typer.echo("The pipeline will pause before starting its next task.")


@app.command()
def resume(
    run_directory: Path = _run_directory_option(),
) -> None:
    """Resume a paused, interrupted, or failed schema-v3 run."""
    database_path = database_path_for_run(run_directory)
    try:
        record = read_run_record(database_path)
        if record.status not in {"paused", "failed", "interrupted"}:
            raise ValueError(f"Cannot resume a run with status '{record.status}'.")

        config = load_config(run_directory / EFFECTIVE_CONFIG_FILENAME)
        loaded_prompt_profile = load_prompt_profile(
            run_directory / PROMPT_PROFILE_FILENAME
        )
        adapters = create_adapters(config.stages)
        run_context = load_run_context(run_directory)
        summary = run_pipeline(
            config=config,
            run_context=run_context,
            database_path=database_path,
            images_directory=run_directory / "images",
            adapters=adapters,
            prompt_profile=loaded_prompt_profile.profile,
            resume=True,
        )
    except (OSError, ValueError) as error:
        typer.echo(str(error), err=True)
        raise typer.Exit(code=1) from error

    _print_run_summary(summary)


@app.command()
def evaluate(
    run_directory: Path = _run_directory_option(),
) -> None:
    """Evaluate a completed experiment."""
    typer.echo(f"Would evaluate {run_directory}")


if __name__ == "__main__":
    app()
