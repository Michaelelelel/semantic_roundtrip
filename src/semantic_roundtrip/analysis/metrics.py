"""Aggregate repeated observations into title and condition metrics."""

from collections import defaultdict

from semantic_roundtrip.analysis.bootstrap import (
    bootstrap_mean_interval,
    bootstrap_stratified_mean_interval,
)
from semantic_roundtrip.analysis.models import (
    ConditionSummary,
    Observation,
    TitleScore,
)


def _mean(values: list[float]) -> float:
    return sum(values) / len(values)


def _rounded(value: float | None) -> float | None:
    return None if value is None else round(value, 8)


def title_scores(records: tuple[Observation, ...]) -> tuple[TitleScore, ...]:
    """Average prompt/image-seed repetitions per title and route."""
    grouped: dict[tuple[object, ...], list[Observation]] = defaultdict(list)
    for record in records:
        grouped[
            (
                record.condition_id,
                record.condition_label,
                record.run_id,
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
        results.append(
            TitleScore(
                condition_id=key[0],
                condition_label=key[1],
                run_id=key[2],
                dataset_id=key[3],
                item_id=key[4],
                item_index=key[5],
                domain=key[6],
                expected_title=key[7],
                route=key[8],
                prediction_model=key[9],
                expected_predictions=len(observations),
                completed_predictions=sum(
                    row.prediction_id is not None for row in observations
                ),
                verifier_passed_predictions=sum(
                    row.verification_passed is True for row in observations
                ),
                strict_exact_accuracy=round(
                    _mean(
                        [
                            float(row.strict_exact_match is True)
                            for row in observations
                        ]
                    ),
                    8,
                ),
                normalized_exact_accuracy=round(
                    _mean(
                        [
                            float(row.normalized_exact_match is True)
                            for row in observations
                        ]
                    ),
                    8,
                ),
                end_to_end_strict_accuracy=round(
                    _mean(
                        [float(row.end_to_end_strict_score) for row in observations]
                    ),
                    8,
                ),
                end_to_end_normalized_accuracy=round(
                    _mean(
                        [
                            float(row.end_to_end_normalized_score)
                            for row in observations
                        ]
                    ),
                    8,
                ),
            )
        )

    return tuple(
        sorted(
            results,
            key=lambda row: (row.condition_id, row.item_index, row.route),
        )
    )


def condition_summaries(
    scores: tuple[TitleScore, ...],
) -> tuple[ConditionSummary, ...]:
    """Summarize title scores for every condition, route, and domain."""
    grouped: dict[tuple[object, ...], list[TitleScore]] = defaultdict(list)
    for score in scores:
        base = (
            score.condition_id,
            score.condition_label,
            score.run_id,
            score.dataset_id,
            score.route,
            score.prediction_model,
        )
        grouped[(*base, score.domain)].append(score)
        grouped[(*base, "all")].append(score)

    results: list[ConditionSummary] = []
    for key, rows in grouped.items():
        primary_values = [row.end_to_end_strict_accuracy for row in rows]
        context = "summary|" + "|".join(str(part) for part in key)
        if key[6] == "all":
            values_by_domain: dict[str, list[float]] = defaultdict(list)
            for row in rows:
                values_by_domain[row.domain].append(row.end_to_end_strict_accuracy)
            ci_low, ci_high = bootstrap_stratified_mean_interval(
                dict(values_by_domain),
                seed_context=context,
            )
        else:
            ci_low, ci_high = bootstrap_mean_interval(
                primary_values,
                seed_context=context,
            )

        expected = sum(row.expected_predictions for row in rows)
        completed = sum(row.completed_predictions for row in rows)
        verifier_passed = sum(row.verifier_passed_predictions for row in rows)
        results.append(
            ConditionSummary(
                condition_id=key[0],
                condition_label=key[1],
                run_id=key[2],
                dataset_id=key[3],
                route=key[4],
                prediction_model=key[5],
                domain=key[6],
                title_count=len(rows),
                expected_predictions=expected,
                completed_predictions=completed,
                verifier_passed_predictions=verifier_passed,
                completion_rate=round(completed / expected, 8),
                verifier_pass_rate=round(verifier_passed / expected, 8),
                strict_exact_accuracy=round(
                    _mean([row.strict_exact_accuracy for row in rows]),
                    8,
                ),
                normalized_exact_accuracy=round(
                    _mean([row.normalized_exact_accuracy for row in rows]),
                    8,
                ),
                end_to_end_strict_accuracy=round(_mean(primary_values), 8),
                ci95_low=_rounded(ci_low),
                ci95_high=_rounded(ci_high),
                end_to_end_normalized_accuracy=round(
                    _mean([row.end_to_end_normalized_accuracy for row in rows]),
                    8,
                ),
            )
        )

    return tuple(
        sorted(
            results,
            key=lambda row: (
                row.condition_id,
                row.route,
                row.domain != "all",
                row.domain,
            ),
        )
    )
