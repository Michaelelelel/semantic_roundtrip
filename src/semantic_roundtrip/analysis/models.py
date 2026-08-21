"""Typed records shared by study extraction, summaries, and output."""

from dataclasses import dataclass
from pathlib import Path

from semantic_roundtrip.persistence.run.analysis_queries import (
    StoredRuntimeEvent,
    StoredTaskTiming,
)


@dataclass(frozen=True, slots=True)
class Observation:
    """One expected image-route result, including failed or missing outputs."""

    condition_id: str
    condition_label: str
    run_id: str
    experiment_name: str
    dataset_id: str
    item_id: str
    item_index: int
    domain: str
    expected_title: str
    prompt_index: int
    prompt_seed: int
    prompt_id: int | None
    prompt_text: str | None
    prompt_model: str
    image_seed: int
    image_id: int | None
    image_path: str | None
    image_model: str
    verification_passed: bool | None
    verification_reason: str | None
    verifier_model: str
    image_description: str | None
    describer_model: str | None
    route: str
    prediction_model: str
    prediction_status: str
    prediction_id: int | None
    predicted_title: str | None
    confidence: float | None
    confidence_type: str | None
    strict_exact_match: bool | None
    normalized_exact_match: bool | None
    end_to_end_strict_score: int
    end_to_end_normalized_score: int
    error_stage: str | None
    error_type: str | None
    error_message: str | None


@dataclass(frozen=True, slots=True)
class ExtractedRun:
    """Expected observations and operational rows from one selected run."""

    condition_id: str
    condition_label: str
    run_directory: Path
    run_id: str
    experiment_name: str
    records: tuple[Observation, ...]
    tasks: tuple[StoredTaskTiming, ...]
    runtime_events: tuple[StoredRuntimeEvent, ...]


@dataclass(frozen=True, slots=True)
class AnalysisResult:
    """Small CLI-facing description of one generated study analysis."""

    study_name: str
    output_directory: Path
    condition_count: int
    observation_rows: int
    title_rows: int
    summary_rows: int
    comparison_rows: int
    generated_files: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class TitleScore:
    """Seed repetitions averaged into one title and route score."""

    condition_id: str
    condition_label: str
    run_id: str
    dataset_id: str
    item_id: str
    item_index: int
    domain: str
    expected_title: str
    route: str
    prediction_model: str
    expected_predictions: int
    completed_predictions: int
    verifier_passed_predictions: int
    strict_exact_accuracy: float
    normalized_exact_accuracy: float
    end_to_end_strict_accuracy: float
    end_to_end_normalized_accuracy: float


@dataclass(frozen=True, slots=True)
class ConditionSummary:
    """Accuracy and completion summary for one condition, route, and domain."""

    condition_id: str
    condition_label: str
    run_id: str
    dataset_id: str
    domain: str
    route: str
    prediction_model: str
    title_count: int
    expected_predictions: int
    completed_predictions: int
    verifier_passed_predictions: int
    completion_rate: float
    verifier_pass_rate: float
    strict_exact_accuracy: float
    normalized_exact_accuracy: float
    end_to_end_strict_accuracy: float
    ci95_low: float | None
    ci95_high: float | None
    end_to_end_normalized_accuracy: float


@dataclass(frozen=True, slots=True)
class ComparisonSummary:
    """Paired title-level difference between two conditions or routes."""

    group_id: str
    kind: str
    condition_id: str
    reference_condition_id: str
    condition_route: str
    reference_route: str
    domain: str
    title_count: int
    condition_accuracy: float
    reference_accuracy: float
    difference: float
    ci95_low: float | None
    ci95_high: float | None


@dataclass(frozen=True, slots=True)
class VerificationSummary:
    """Image generation and verification counts for one condition and domain."""

    condition_id: str
    condition_label: str
    run_id: str
    dataset_id: str
    domain: str
    expected_images: int
    generated_images: int
    verified_images: int
    passed_images: int
    rejected_images: int
    missing_images: int
    verifier_pass_rate: float | None


@dataclass(frozen=True, slots=True)
class FailureRow:
    """One expected prediction that was not produced."""

    condition_id: str
    run_id: str
    item_id: str
    domain: str
    expected_title: str
    prompt_seed: int
    image_seed: int
    route: str
    prediction_status: str
    error_stage: str | None
    error_type: str | None
    error_message: str | None


@dataclass(frozen=True, slots=True)
class StageRuntimeSummary:
    """Task and model-lifecycle timings for one condition and stage."""

    condition_id: str
    condition_label: str
    run_id: str
    stage: str
    task_count: int
    completed_tasks: int
    failed_tasks: int
    total_task_seconds: float
    median_task_seconds: float | None
    model_load_seconds: float
    model_unload_seconds: float
    model_reuse_events: int
