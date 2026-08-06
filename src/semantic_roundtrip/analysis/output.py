"""Atomic CSV, JSON, and figure publication for run and job analysis."""

import csv
import json
from dataclasses import asdict, fields, is_dataclass
from importlib.metadata import PackageNotFoundError, version
from pathlib import Path
from shutil import rmtree
from typing import Any
from uuid import uuid4

from semantic_roundtrip.analysis.bootstrap import (
    BOOTSTRAP_REPETITIONS,
    BOOTSTRAP_SEED,
)
from semantic_roundtrip.analysis.extraction import extract_run
from semantic_roundtrip.analysis.models import (
    AnalysisResult,
    ExtractedRun,
    PredictionRecord,
)
from semantic_roundtrip.analysis.summaries import (
    PairedRouteDifference,
    PairedRouteSummary,
    StackDomainRouteSummary,
    StageRuntimeSummary,
    TitleScore,
    VerificationSummary,
    paired_route_differences,
    paired_route_summaries,
    stack_domain_route_summaries,
    stage_runtime_summaries,
    title_scores,
    verification_summaries,
)
from semantic_roundtrip.evaluation import EXACT_MATCH_METHOD, NORMALIZED_EXACT_METHOD
from semantic_roundtrip.job import JOB_SNAPSHOT_FILENAME, load_job_snapshot
from semantic_roundtrip.persistence.job.database import (
    read_job_entries,
    read_job_record,
)
from semantic_roundtrip.persistence.job.schema import job_database_path


ANALYSIS_DIRECTORY_NAME = "analysis"
ANALYSIS_MANIFEST_SCHEMA_VERSION = 2
ANALYZABLE_JOB_STATUSES = frozenset({"completed", "failed", "interrupted"})


def _software_version() -> str:
    try:
        return version("semantic-roundtrip")
    except PackageNotFoundError:
        return "development"


def _csv_value(value: object) -> object:
    if value is None:
        return ""
    if isinstance(value, bool):
        return "true" if value else "false"
    return value


def _write_csv(path: Path, rows: tuple[Any, ...], row_type: type[Any]) -> None:
    if not is_dataclass(row_type):
        raise TypeError(f"CSV row type must be a dataclass: {row_type}")
    fieldnames = [field.name for field in fields(row_type)]
    with path.open("x", encoding="utf-8", newline="") as file:
        writer = csv.DictWriter(file, fieldnames=fieldnames, lineterminator="\n")
        writer.writeheader()
        for row in rows:
            writer.writerow(
                {key: _csv_value(value) for key, value in asdict(row).items()}
            )


def _publish_directory(
    temporary: Path,
    destination: Path,
    *,
    force: bool,
) -> None:
    if not destination.exists():
        temporary.rename(destination)
        return
    if not force:
        raise FileExistsError(
            f"Analysis already exists: {destination}. Use --force to replace it."
        )

    backup = destination.parent / f".{destination.name}.backup-{uuid4().hex}"
    destination.rename(backup)
    try:
        temporary.rename(destination)
    except Exception:
        backup.rename(destination)
        raise
    else:
        rmtree(backup)


def _write_analysis(
    source_directory: Path,
    *,
    scope: str,
    source_id: str,
    source_name: str,
    source_status: str,
    runs: tuple[ExtractedRun, ...],
    force: bool,
) -> AnalysisResult:
    try:
        from semantic_roundtrip.analysis.plots import create_figures
    except ModuleNotFoundError as error:
        if error.name != "matplotlib":
            raise
        raise ValueError(
            "Analysis plotting support is not installed. "
            "Install the project with the 'analysis' extra."
        ) from error

    records = tuple(record for run in runs for record in run.records)
    titles = title_scores(records)
    summaries = stack_domain_route_summaries(titles)
    differences = paired_route_differences(titles)
    route_summaries = paired_route_summaries(differences)
    verifications = verification_summaries(records)
    runtimes = stage_runtime_summaries(runs)

    destination = source_directory / ANALYSIS_DIRECTORY_NAME
    if destination.exists() and not force:
        raise FileExistsError(
            f"Analysis already exists: {destination}. Use --force to replace it."
        )
    temporary = source_directory / f".{ANALYSIS_DIRECTORY_NAME}.tmp-{uuid4().hex}"
    temporary.mkdir()
    try:
        csv_specs = (
            ("predictions.csv", records, PredictionRecord),
            ("title_scores.csv", titles, TitleScore),
            (
                "stack_domain_route_summary.csv",
                summaries,
                StackDomainRouteSummary,
            ),
            (
                "paired_route_differences.csv",
                differences,
                PairedRouteDifference,
            ),
            (
                "paired_route_summary.csv",
                route_summaries,
                PairedRouteSummary,
            ),
            (
                "verification_and_failures.csv",
                verifications,
                VerificationSummary,
            ),
            ("stage_runtime.csv", runtimes, StageRuntimeSummary),
        )
        generated_files: list[str] = []
        for filename, rows, row_type in csv_specs:
            _write_csv(temporary / filename, rows, row_type)
            generated_files.append(filename)

        plot_result = create_figures(
            temporary / "figures",
            records=records,
            summaries=summaries,
            differences=differences,
            route_summaries=route_summaries,
        )
        generated_files.extend(
            f"figures/{filename}" for filename in plot_result.generated
        )
        manifest_filename = "analysis_manifest.json"
        manifest_generated_files = [manifest_filename, *generated_files]
        manifest = {
            "analysis_manifest_schema_version": ANALYSIS_MANIFEST_SCHEMA_VERSION,
            "software_version": _software_version(),
            "scope": scope,
            "source_id": source_id,
            "source_name": source_name,
            "source_status": source_status,
            "run_ids": [run.run_id for run in runs],
            "methods": {
                "primary_metric": ("mean title-level end-to-end strict exact accuracy"),
                "primary_exact_method": EXACT_MATCH_METHOD,
                "normalized_diagnostic_method": NORMALIZED_EXACT_METHOD,
                "missing_or_failed_score": 0,
                "verifier_failure_score": 0,
                "bootstrap_unit": "title",
                "bootstrap_repetitions": BOOTSTRAP_REPETITIONS,
                "bootstrap_seed": BOOTSTRAP_SEED,
                "confidence_interval": "95% percentile bootstrap",
                "overall_bootstrap": "domain-stratified title bootstrap",
                "paired_difference": "description minus direct within run and title",
                "confidence_scope": "within prediction model, route, and type",
            },
            "row_counts": {
                "predictions": len(records),
                "titles": len(titles),
                "stack_domain_route_summaries": len(summaries),
                "paired_route_differences": len(differences),
                "paired_route_summaries": len(route_summaries),
                "verification_summaries": len(verifications),
                "stage_runtime_summaries": len(runtimes),
            },
            "generated_files": manifest_generated_files,
            "omitted_figures": plot_result.omitted,
        }
        with (temporary / manifest_filename).open(
            "x",
            encoding="utf-8",
        ) as file:
            json.dump(manifest, file, indent=2, ensure_ascii=False, sort_keys=True)
            file.write("\n")
        generated_files = manifest_generated_files

        _publish_directory(temporary, destination, force=force)
    except Exception:
        if temporary.exists():
            rmtree(temporary)
        raise

    return AnalysisResult(
        scope=scope,
        source_id=source_id,
        output_directory=destination,
        prediction_rows=len(records),
        title_rows=len(titles),
        summary_rows=len(summaries),
        generated_files=tuple(generated_files),
    )


def evaluate_run(run_directory: Path, *, force: bool = False) -> AnalysisResult:
    """Analyze one terminal run without modifying its inference database."""
    run_directory = run_directory.resolve()
    extracted = extract_run(run_directory)
    return _write_analysis(
        run_directory,
        scope="run",
        source_id=extracted.run_id,
        source_name=extracted.experiment_name,
        source_status=extracted.run_status,
        runs=(extracted,),
        force=force,
    )


def evaluate_job(job_directory: Path, *, force: bool = False) -> AnalysisResult:
    """Combine every child run from one terminal persisted job."""
    job_directory = job_directory.resolve()
    database_path = job_database_path(job_directory)
    record = read_job_record(database_path)
    if record.status not in ANALYZABLE_JOB_STATUSES:
        raise ValueError(
            f"Job status '{record.status}' is not terminal; complete or stop it first."
        )
    snapshot = load_job_snapshot(job_directory / JOB_SNAPSHOT_FILENAME)
    persisted_entries = read_job_entries(database_path, job_directory)
    configured_entries = {entry.index: entry for entry in snapshot.entries}
    if len(configured_entries) != len(persisted_entries):
        raise ValueError("Job snapshot and database entry counts do not match.")

    runs: list[ExtractedRun] = []
    for persisted in persisted_entries:
        configured = configured_entries.get(persisted.entry_index)
        if configured is None:
            raise ValueError(f"Missing job snapshot entry {persisted.entry_index}.")
        runs.append(
            extract_run(
                persisted.run_directory,
                job_id=record.job_id,
                job_entry=configured.name,
                require_terminal=False,
            )
        )
    return _write_analysis(
        job_directory,
        scope="job",
        source_id=record.job_id,
        source_name=record.name,
        source_status=record.status,
        runs=tuple(runs),
        force=force,
    )
