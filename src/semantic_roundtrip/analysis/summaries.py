"""Title-level, group-level, paired-route, and operational summaries."""

from collections import defaultdict
from dataclasses import dataclass
from datetime import datetime
from statistics import median

from semantic_roundtrip.analysis.bootstrap import (
    bootstrap_mean_interval,
    bootstrap_stratified_mean_interval,
)
from semantic_roundtrip.analysis.models import ExtractedRun, PredictionRecord


def _mean(values: list[float]) -> float | None:
    return None if not values else sum(values) / len(values)


def _rounded(value: float | None) -> float | None:
    return None if value is None else round(value, 8)


@dataclass(frozen=True, slots=True)
class TitleScore:
    job_id: str | None
    job_entry: str | None
    run_id: str
    experiment_name: str
    stack_id: str
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
    end_to_end_accuracy: float
    normalized_end_to_end_accuracy: float
    verifier_passed_exact_accuracy: float | None


@dataclass(frozen=True, slots=True)
class StackDomainRouteSummary:
    job_id: str | None
    job_entry: str | None
    run_id: str
    experiment_name: str
    stack_id: str
    dataset_id: str
    domain: str
    route: str
    prediction_model: str
    title_count: int
    expected_predictions: int
    completed_predictions: int
    verifier_passed_predictions: int
    completion_rate: float
    mean_title_accuracy: float
    ci95_low: float | None
    ci95_high: float | None
    mean_title_normalized_accuracy: float
    verifier_passed_title_count: int
    verifier_passed_exact_accuracy: float | None


@dataclass(frozen=True, slots=True)
class PairedRouteDifference:
    job_id: str | None
    job_entry: str | None
    run_id: str
    experiment_name: str
    stack_id: str
    dataset_id: str
    item_id: str
    item_index: int
    domain: str
    expected_title: str
    direct_prediction_model: str
    description_prediction_model: str
    direct_accuracy: float
    description_accuracy: float
    difference_description_minus_direct: float


@dataclass(frozen=True, slots=True)
class PairedRouteSummary:
    job_id: str | None
    job_entry: str | None
    run_id: str
    experiment_name: str
    stack_id: str
    dataset_id: str
    domain: str
    direct_prediction_model: str
    description_prediction_model: str
    title_count: int
    mean_difference_description_minus_direct: float
    ci95_low: float | None
    ci95_high: float | None


@dataclass(frozen=True, slots=True)
class VerificationSummary:
    job_id: str | None
    job_entry: str | None
    run_id: str
    experiment_name: str
    dataset_id: str
    domain: str
    expected_images: int
    generated_images: int
    verified_images: int
    passed_images: int
    failed_images: int
    missing_images: int
    verification_pass_rate: float | None


@dataclass(frozen=True, slots=True)
class StageRuntimeSummary:
    job_id: str | None
    job_entry: str | None
    run_id: str
    experiment_name: str
    stage: str
    task_count: int
    completed_tasks: int
    failed_tasks: int
    total_task_seconds: float
    median_task_seconds: float | None
    model_load_seconds: float
    model_unload_seconds: float
    model_reuse_events: int


def title_scores(records: tuple[PredictionRecord, ...]) -> tuple[TitleScore, ...]:
    """Aggregate image observations to the independent title unit."""
    grouped: dict[tuple[object, ...], list[PredictionRecord]] = defaultdict(list)
    for record in records:
        grouped[
            (
                record.job_id,
                record.job_entry,
                record.run_id,
                record.experiment_name,
                record.stack_id,
                record.dataset_id,
                record.item_id,
                record.item_index,
                record.domain,
                record.expected_title,
                record.route,
                record.prediction_model,
            )
        ].append(record)

    results: list[TitleScore] = []
    for key, observations in grouped.items():
        completed_count = sum(
            record.prediction_id is not None for record in observations
        )
        verifier_passed = [
            record for record in observations if record.verification_passed is True
        ]
        results.append(
            TitleScore(
                job_id=key[0],
                job_entry=key[1],
                run_id=key[2],
                experiment_name=key[3],
                stack_id=key[4],
                dataset_id=key[5],
                item_id=key[6],
                item_index=key[7],
                domain=key[8],
                expected_title=key[9],
                route=key[10],
                prediction_model=key[11],
                expected_predictions=len(observations),
                completed_predictions=completed_count,
                verifier_passed_predictions=len(verifier_passed),
                end_to_end_accuracy=_rounded(
                    _mean([float(record.end_to_end_score) for record in observations])
                )
                or 0.0,
                normalized_end_to_end_accuracy=_rounded(
                    _mean(
                        [
                            float(record.normalized_end_to_end_score)
                            for record in observations
                        ]
                    )
                )
                or 0.0,
                verifier_passed_exact_accuracy=_rounded(
                    _mean(
                        [float(record.end_to_end_score) for record in verifier_passed]
                    )
                ),
            )
        )
    return tuple(sorted(results, key=_title_sort_key))


def _title_sort_key(score: TitleScore) -> tuple[object, ...]:
    return (
        score.job_entry or "",
        score.run_id,
        score.item_index,
        score.route,
    )


def stack_domain_route_summaries(
    scores: tuple[TitleScore, ...],
) -> tuple[StackDomainRouteSummary, ...]:
    """Summarize title-level scores by run, route, and domain plus overall."""
    grouped: dict[tuple[object, ...], list[TitleScore]] = defaultdict(list)
    for score in scores:
        base = (
            score.job_id,
            score.job_entry,
            score.run_id,
            score.experiment_name,
            score.stack_id,
            score.dataset_id,
            score.route,
            score.prediction_model,
        )
        grouped[(*base, score.domain)].append(score)
        grouped[(*base, "all")].append(score)

    results: list[StackDomainRouteSummary] = []
    for key, title_rows in grouped.items():
        end_to_end = [row.end_to_end_accuracy for row in title_rows]
        context = "|".join(str(part) for part in key)
        if key[8] == "all":
            values_by_domain: dict[str, list[float]] = defaultdict(list)
            for row in title_rows:
                values_by_domain[row.domain].append(row.end_to_end_accuracy)
            ci_low, ci_high = bootstrap_stratified_mean_interval(
                dict(values_by_domain),
                seed_context=context,
            )
        else:
            ci_low, ci_high = bootstrap_mean_interval(
                end_to_end,
                seed_context=context,
            )
        expected_predictions = sum(row.expected_predictions for row in title_rows)
        completed_predictions = sum(row.completed_predictions for row in title_rows)
        verifier_passed_predictions = sum(
            row.verifier_passed_predictions for row in title_rows
        )
        verifier_passed_title_rows = [
            row for row in title_rows if row.verifier_passed_exact_accuracy is not None
        ]
        results.append(
            StackDomainRouteSummary(
                job_id=key[0],
                job_entry=key[1],
                run_id=key[2],
                experiment_name=key[3],
                stack_id=key[4],
                dataset_id=key[5],
                route=key[6],
                prediction_model=key[7],
                domain=key[8],
                title_count=len(title_rows),
                expected_predictions=expected_predictions,
                completed_predictions=completed_predictions,
                verifier_passed_predictions=verifier_passed_predictions,
                completion_rate=_rounded(completed_predictions / expected_predictions)
                or 0.0,
                mean_title_accuracy=_rounded(_mean(end_to_end)) or 0.0,
                ci95_low=_rounded(ci_low),
                ci95_high=_rounded(ci_high),
                mean_title_normalized_accuracy=_rounded(
                    _mean([row.normalized_end_to_end_accuracy for row in title_rows])
                )
                or 0.0,
                verifier_passed_title_count=len(verifier_passed_title_rows),
                verifier_passed_exact_accuracy=_rounded(
                    _mean(
                        [
                            row.verifier_passed_exact_accuracy
                            for row in verifier_passed_title_rows
                            if row.verifier_passed_exact_accuracy is not None
                        ]
                    )
                ),
            )
        )
    return tuple(
        sorted(
            results,
            key=lambda row: (
                row.job_entry or "",
                row.run_id,
                row.domain != "all",
                row.domain,
                row.route,
            ),
        )
    )


def paired_route_differences(
    scores: tuple[TitleScore, ...],
) -> tuple[PairedRouteDifference, ...]:
    """Pair direct and description title scores from the same run."""
    grouped: dict[tuple[object, ...], dict[str, TitleScore]] = defaultdict(dict)
    for score in scores:
        key = (
            score.job_id,
            score.job_entry,
            score.run_id,
            score.experiment_name,
            score.stack_id,
            score.dataset_id,
            score.item_id,
            score.item_index,
            score.domain,
            score.expected_title,
        )
        grouped[key][score.route] = score

    results: list[PairedRouteDifference] = []
    for key, routes in grouped.items():
        direct = routes.get("direct")
        description = routes.get("description")
        if direct is None or description is None:
            continue
        results.append(
            PairedRouteDifference(
                job_id=key[0],
                job_entry=key[1],
                run_id=key[2],
                experiment_name=key[3],
                stack_id=key[4],
                dataset_id=key[5],
                item_id=key[6],
                item_index=key[7],
                domain=key[8],
                expected_title=key[9],
                direct_prediction_model=direct.prediction_model,
                description_prediction_model=description.prediction_model,
                direct_accuracy=direct.end_to_end_accuracy,
                description_accuracy=description.end_to_end_accuracy,
                difference_description_minus_direct=_rounded(
                    description.end_to_end_accuracy - direct.end_to_end_accuracy
                )
                or 0.0,
            )
        )
    return tuple(
        sorted(
            results,
            key=lambda row: (row.job_entry or "", row.run_id, row.item_index),
        )
    )


def paired_route_summaries(
    differences: tuple[PairedRouteDifference, ...],
) -> tuple[PairedRouteSummary, ...]:
    """Aggregate paired title differences overall and within each domain."""
    grouped: dict[tuple[object, ...], list[PairedRouteDifference]] = defaultdict(list)
    for row in differences:
        base = (
            row.job_id,
            row.job_entry,
            row.run_id,
            row.experiment_name,
            row.stack_id,
            row.dataset_id,
            row.direct_prediction_model,
            row.description_prediction_model,
        )
        grouped[(*base, row.domain)].append(row)
        grouped[(*base, "all")].append(row)

    results: list[PairedRouteSummary] = []
    for key, title_rows in grouped.items():
        values = [row.difference_description_minus_direct for row in title_rows]
        context = "paired|" + "|".join(str(part) for part in key)
        if key[8] == "all":
            values_by_domain: dict[str, list[float]] = defaultdict(list)
            for row in title_rows:
                values_by_domain[row.domain].append(
                    row.difference_description_minus_direct
                )
            ci_low, ci_high = bootstrap_stratified_mean_interval(
                dict(values_by_domain),
                seed_context=context,
            )
        else:
            ci_low, ci_high = bootstrap_mean_interval(
                values,
                seed_context=context,
            )

        results.append(
            PairedRouteSummary(
                job_id=key[0],
                job_entry=key[1],
                run_id=key[2],
                experiment_name=key[3],
                stack_id=key[4],
                dataset_id=key[5],
                direct_prediction_model=key[6],
                description_prediction_model=key[7],
                domain=key[8],
                title_count=len(title_rows),
                mean_difference_description_minus_direct=(
                    _rounded(_mean(values)) or 0.0
                ),
                ci95_low=_rounded(ci_low),
                ci95_high=_rounded(ci_high),
            )
        )

    return tuple(
        sorted(
            results,
            key=lambda row: (
                row.job_entry or "",
                row.run_id,
                row.domain != "all",
                row.domain,
            ),
        )
    )


def verification_summaries(
    records: tuple[PredictionRecord, ...],
) -> tuple[VerificationSummary, ...]:
    """Summarize verification once per expected image, not once per route."""
    images: dict[tuple[object, ...], PredictionRecord] = {}
    for record in records:
        key = (
            record.job_id,
            record.job_entry,
            record.run_id,
            record.item_id,
            record.prompt_index,
            record.image_seed,
        )
        images.setdefault(key, record)

    grouped: dict[tuple[object, ...], list[PredictionRecord]] = defaultdict(list)
    for record in images.values():
        base = (
            record.job_id,
            record.job_entry,
            record.run_id,
            record.experiment_name,
            record.dataset_id,
        )
        grouped[(*base, record.domain)].append(record)
        grouped[(*base, "all")].append(record)

    results: list[VerificationSummary] = []
    for key, image_rows in grouped.items():
        generated = [row for row in image_rows if row.image_id is not None]
        verified = [row for row in image_rows if row.verification_passed is not None]
        passed = sum(row.verification_passed is True for row in verified)
        results.append(
            VerificationSummary(
                job_id=key[0],
                job_entry=key[1],
                run_id=key[2],
                experiment_name=key[3],
                dataset_id=key[4],
                domain=key[5],
                expected_images=len(image_rows),
                generated_images=len(generated),
                verified_images=len(verified),
                passed_images=passed,
                failed_images=len(verified) - passed,
                missing_images=len(image_rows) - len(generated),
                verification_pass_rate=_rounded(
                    None if not verified else passed / len(verified)
                ),
            )
        )
    return tuple(
        sorted(
            results,
            key=lambda row: (
                row.job_entry or "",
                row.run_id,
                row.domain != "all",
                row.domain,
            ),
        )
    )


def _duration_seconds(started_at: str | None, finished_at: str | None) -> float | None:
    if started_at is None or finished_at is None:
        return None
    duration = (
        datetime.fromisoformat(finished_at) - datetime.fromisoformat(started_at)
    ).total_seconds()
    return duration if duration >= 0 else None


def stage_runtime_summaries(
    runs: tuple[ExtractedRun, ...],
) -> tuple[StageRuntimeSummary, ...]:
    """Aggregate task and model-lifecycle durations per run and stage."""
    results: list[StageRuntimeSummary] = []
    for run in runs:
        first_record = run.records[0]
        stages = sorted(
            {task.stage for task in run.tasks}
            | {event.stage for event in run.runtime_events}
        )
        for stage in stages:
            tasks = [task for task in run.tasks if task.stage == stage]
            task_durations = [
                duration
                for task in tasks
                if (
                    duration := _duration_seconds(
                        task.started_at,
                        task.finished_at,
                    )
                )
                is not None
            ]
            events = [event for event in run.runtime_events if event.stage == stage]
            load_seconds = sum(
                duration
                for event in events
                if event.action == "load"
                and (
                    duration := _duration_seconds(
                        event.started_at,
                        event.finished_at,
                    )
                )
                is not None
            )
            unload_seconds = sum(
                duration
                for event in events
                if event.action == "unload"
                and (
                    duration := _duration_seconds(
                        event.started_at,
                        event.finished_at,
                    )
                )
                is not None
            )
            results.append(
                StageRuntimeSummary(
                    job_id=first_record.job_id,
                    job_entry=first_record.job_entry,
                    run_id=run.run_id,
                    experiment_name=run.experiment_name,
                    stage=stage,
                    task_count=len(tasks),
                    completed_tasks=sum(task.status == "completed" for task in tasks),
                    failed_tasks=sum(task.status == "failed" for task in tasks),
                    total_task_seconds=round(sum(task_durations), 6),
                    median_task_seconds=(
                        None if not task_durations else round(median(task_durations), 6)
                    ),
                    model_load_seconds=round(load_seconds, 6),
                    model_unload_seconds=round(unload_seconds, 6),
                    model_reuse_events=sum(
                        event.action == "reuse" and event.status == "completed"
                        for event in events
                    ),
                )
            )
    return tuple(
        sorted(
            results,
            key=lambda row: (row.job_entry or "", row.run_id, row.stage),
        )
    )
