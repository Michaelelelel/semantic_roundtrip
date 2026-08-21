"""Read selected SQLite runs and atomically publish one study analysis."""

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
from semantic_roundtrip.analysis.config import load_study
from semantic_roundtrip.analysis.comparisons import (
    comparison_summaries,
    validate_groups,
)
from semantic_roundtrip.analysis.diagnostics import (
    failure_rows,
    stage_runtime_summaries,
    verification_summaries,
)
from semantic_roundtrip.analysis.extraction import extract_run
from semantic_roundtrip.analysis.metrics import condition_summaries, title_scores
from semantic_roundtrip.analysis.models import (
    AnalysisResult,
    ComparisonSummary,
    ConditionSummary,
    FailureRow,
    Observation,
    StageRuntimeSummary,
    TitleScore,
    VerificationSummary,
)
from semantic_roundtrip.evaluation import EXACT_MATCH_METHOD, NORMALIZED_EXACT_METHOD


ANALYSIS_MANIFEST_SCHEMA_VERSION = 1
STUDY_SNAPSHOT_FILENAME = "study_snapshot.yaml"


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
            f"Study results already exist: {destination}. Use --force to replace them."
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


def analyze_study(
    study_directory: Path,
    *,
    force: bool = False,
) -> AnalysisResult:
    """Analyze exactly the completed runs selected by one study.yaml file."""
    loaded = load_study(study_directory)
    runs = tuple(
        extract_run(
            loaded.run_directories[condition_id],
            condition_id=condition_id,
            condition_label=condition.label or condition_id,
        )
        for condition_id, condition in loaded.config.conditions.items()
    )
    records = tuple(record for run in runs for record in run.records)
    validate_groups(records, loaded.config.groups)

    titles = title_scores(records)
    summaries = condition_summaries(titles)
    comparisons = comparison_summaries(titles, loaded.config.groups)
    verifications = verification_summaries(records)
    failures = failure_rows(records)
    runtimes = stage_runtime_summaries(runs)

    try:
        from semantic_roundtrip.analysis.plots import create_figures
    except ModuleNotFoundError as error:
        if error.name != "matplotlib":
            raise
        raise ValueError(
            "Analysis plotting support is not installed. "
            "Install the project with the 'analysis' extra."
        ) from error

    destination = loaded.output_directory
    destination.parent.mkdir(parents=True, exist_ok=True)
    if destination.exists() and not force:
        raise FileExistsError(
            f"Study results already exist: {destination}. Use --force to replace them."
        )
    temporary = destination.parent / f".{destination.name}.tmp-{uuid4().hex}"
    temporary.mkdir()
    try:
        (temporary / STUDY_SNAPSHOT_FILENAME).write_bytes(loaded.source_bytes)
        csv_specs = (
            ("observations.csv", records, Observation),
            ("title_scores.csv", titles, TitleScore),
            ("summaries.csv", summaries, ConditionSummary),
            ("comparisons.csv", comparisons, ComparisonSummary),
            ("verification.csv", verifications, VerificationSummary),
            ("failures.csv", failures, FailureRow),
            ("runtimes.csv", runtimes, StageRuntimeSummary),
        )
        generated_files = [STUDY_SNAPSHOT_FILENAME]
        for filename, rows, row_type in csv_specs:
            _write_csv(temporary / filename, rows, row_type)
            generated_files.append(filename)

        labels = {
            condition_id: condition.label or condition_id
            for condition_id, condition in loaded.config.conditions.items()
        }
        plot_result = create_figures(
            temporary / "figures",
            groups=loaded.config.groups,
            labels=labels,
            summaries=summaries,
            comparisons=comparisons,
        )
        generated_files.extend(
            f"figures/{filename}" for filename in plot_result.generated
        )

        manifest_filename = "manifest.json"
        manifest_files = [manifest_filename, *generated_files]
        manifest = {
            "analysis_manifest_schema_version": ANALYSIS_MANIFEST_SCHEMA_VERSION,
            "software_version": _software_version(),
            "study_name": loaded.config.study.name,
            "conditions": {
                run.condition_id: {
                    "label": run.condition_label,
                    "run_id": run.run_id,
                    "experiment_name": run.experiment_name,
                    "run_directory": str(run.run_directory),
                }
                for run in runs
            },
            "groups": {
                group_id: group.model_dump(mode="json")
                for group_id, group in loaded.config.groups.items()
            },
            "methods": {
                "primary_metric": "title-level end-to-end strict exact accuracy",
                "primary_exact_method": EXACT_MATCH_METHOD,
                "secondary_normalized_method": NORMALIZED_EXACT_METHOD,
                "missing_prediction_score": 0,
                "verifier_rejection_score": 0,
                "independent_unit": "title",
                "seed_repetitions": "averaged within each title",
                "bootstrap_repetitions": BOOTSTRAP_REPETITIONS,
                "bootstrap_seed": BOOTSTRAP_SEED,
                "confidence_interval": "95% percentile bootstrap by title",
                "overall_bootstrap": "stratified by domain",
            },
            "row_counts": {
                "conditions": len(runs),
                "observations": len(records),
                "titles": len(titles),
                "summaries": len(summaries),
                "comparisons": len(comparisons),
                "failures": len(failures),
                "runtimes": len(runtimes),
            },
            "generated_files": manifest_files,
            "omitted_figures": plot_result.omitted,
        }
        with (temporary / manifest_filename).open("x", encoding="utf-8") as file:
            json.dump(manifest, file, indent=2, ensure_ascii=False, sort_keys=True)
            file.write("\n")

        _publish_directory(temporary, destination, force=force)
    except Exception:
        if temporary.exists():
            rmtree(temporary)
        raise

    return AnalysisResult(
        study_name=loaded.config.study.name,
        output_directory=destination,
        condition_count=len(runs),
        observation_rows=len(records),
        title_rows=len(titles),
        summary_rows=len(summaries),
        comparison_rows=len(comparisons),
        generated_files=tuple(manifest_files),
    )
