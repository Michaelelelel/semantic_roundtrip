"""Typed records shared by analysis extraction, summaries, and output."""

from dataclasses import dataclass
from pathlib import Path

from semantic_roundtrip.persistence.run.analysis_queries import (
    StoredRuntimeEvent,
    StoredTaskTiming,
)


@dataclass(frozen=True, slots=True)
class PredictionRecord:
    """One expected image-route observation, including missing outcomes."""

    job_id: str | None
    job_entry: str | None
    run_id: str
    experiment_name: str
    run_status: str
    stack_id: str
    dataset_id: str
    item_id: str
    item_index: int
    domain: str
    expected_title: str
    prompt_index: int
    prompt_seed: int
    prompt_id: int | None
    prompt_text: str | None
    prompt_backend: str
    prompt_model: str
    image_seed: int
    image_id: int | None
    image_path: str | None
    image_backend: str
    image_model: str
    verification_passed: bool | None
    verification_reason: str | None
    verifier_backend: str
    verifier_model: str
    image_description: str | None
    describer_backend: str | None
    describer_model: str | None
    route: str
    prediction_input: str
    prediction_backend: str
    prediction_model: str
    prediction_status: str
    prediction_id: int | None
    predicted_title: str | None
    confidence: float | None
    confidence_type: str | None
    exact_match: bool | None
    normalized_exact_match: bool | None
    exact_method: str | None
    normalized_method: str | None
    end_to_end_score: int
    normalized_end_to_end_score: int
    error_stage: str | None
    error_type: str | None
    error_message: str | None


@dataclass(frozen=True, slots=True)
class ExtractedRun:
    """Expected prediction records and operational rows from one run."""

    run_id: str
    experiment_name: str
    run_status: str
    records: tuple[PredictionRecord, ...]
    tasks: tuple[StoredTaskTiming, ...]
    runtime_events: tuple[StoredRuntimeEvent, ...]


@dataclass(frozen=True, slots=True)
class AnalysisResult:
    """Small CLI-facing description of generated analysis artifacts."""

    scope: str
    source_id: str
    output_directory: Path
    prediction_rows: int
    title_rows: int
    summary_rows: int
    generated_files: tuple[str, ...]
