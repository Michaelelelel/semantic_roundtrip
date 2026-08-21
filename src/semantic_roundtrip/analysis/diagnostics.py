"""Summarize verification, missing predictions, and stage runtimes."""

from collections import defaultdict
from datetime import datetime
from statistics import median

from semantic_roundtrip.analysis.models import (
    ExtractedRun,
    FailureRow,
    Observation,
    StageRuntimeSummary,
    VerificationSummary,
)


def verification_summaries(
    records: tuple[Observation, ...],
) -> tuple[VerificationSummary, ...]:
    """Summarize verification once per expected image rather than per route."""
    images: dict[tuple[object, ...], Observation] = {}
    for record in records:
        key = (
            record.condition_id,
            record.run_id,
            record.item_id,
            record.prompt_index,
            record.image_seed,
        )
        images.setdefault(key, record)

    grouped: dict[tuple[object, ...], list[Observation]] = defaultdict(list)
    for record in images.values():
        base = (
            record.condition_id,
            record.condition_label,
            record.run_id,
            record.dataset_id,
        )
        grouped[(*base, record.domain)].append(record)
        grouped[(*base, "all")].append(record)

    results: list[VerificationSummary] = []
    for key, rows in grouped.items():
        generated = [row for row in rows if row.image_id is not None]
        verified = [row for row in rows if row.verification_passed is not None]
        passed = sum(row.verification_passed is True for row in verified)
        results.append(
            VerificationSummary(
                condition_id=key[0],
                condition_label=key[1],
                run_id=key[2],
                dataset_id=key[3],
                domain=key[4],
                expected_images=len(rows),
                generated_images=len(generated),
                verified_images=len(verified),
                passed_images=passed,
                rejected_images=len(verified) - passed,
                missing_images=len(rows) - len(generated),
                verifier_pass_rate=(
                    None if not verified else round(passed / len(verified), 8)
                ),
            )
        )
    return tuple(
        sorted(
            results,
            key=lambda row: (
                row.condition_id,
                row.domain != "all",
                row.domain,
            ),
        )
    )


def failure_rows(records: tuple[Observation, ...]) -> tuple[FailureRow, ...]:
    """Return every expected prediction that was not produced."""
    return tuple(
        FailureRow(
            condition_id=row.condition_id,
            run_id=row.run_id,
            item_id=row.item_id,
            domain=row.domain,
            expected_title=row.expected_title,
            prompt_seed=row.prompt_seed,
            image_seed=row.image_seed,
            route=row.route,
            prediction_status=row.prediction_status,
            error_stage=row.error_stage,
            error_type=row.error_type,
            error_message=row.error_message,
        )
        for row in records
        if row.prediction_id is None
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
    """Aggregate task and model-lifecycle durations per condition and stage."""
    results: list[StageRuntimeSummary] = []
    for run in runs:
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
                    duration := _duration_seconds(task.started_at, task.finished_at)
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
                    condition_id=run.condition_id,
                    condition_label=run.condition_label,
                    run_id=run.run_id,
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
    return tuple(sorted(results, key=lambda row: (row.condition_id, row.stage)))
