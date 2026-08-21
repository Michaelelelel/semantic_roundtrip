"""Validate comparable run grids and calculate paired title differences."""

from collections import defaultdict

from semantic_roundtrip.analysis.bootstrap import (
    bootstrap_mean_interval,
    bootstrap_stratified_mean_interval,
)
from semantic_roundtrip.analysis.config import StudyGroup
from semantic_roundtrip.analysis.models import (
    ComparisonSummary,
    Observation,
    TitleScore,
)


def _observation_map(
    records: tuple[Observation, ...],
    *,
    condition_id: str,
    route: str,
) -> dict[tuple[str, int, int, int], Observation]:
    result: dict[tuple[str, int, int, int], Observation] = {}
    for record in records:
        if record.condition_id != condition_id or record.route != route:
            continue
        key = (
            record.item_id,
            record.prompt_index,
            record.prompt_seed,
            record.image_seed,
        )
        if key in result:
            raise ValueError(
                f"Duplicate expected observation for condition '{condition_id}': {key}"
            )
        result[key] = record
    return result


def _required_observations(
    records: tuple[Observation, ...],
    *,
    group_id: str,
    condition_id: str,
    route: str,
) -> dict[tuple[str, int, int, int], Observation]:
    observations = _observation_map(
        records,
        condition_id=condition_id,
        route=route,
    )
    if not observations:
        raise ValueError(
            f"Study group '{group_id}' requires route '{route}' for condition "
            f"'{condition_id}'."
        )
    return observations


def _require_matching_observations(
    *,
    group_id: str,
    left_name: str,
    left: dict[tuple[str, int, int, int], Observation],
    right_name: str,
    right: dict[tuple[str, int, int, int], Observation],
) -> None:
    if set(left) != set(right):
        raise ValueError(
            f"Study group '{group_id}' has different title/seed grids for "
            f"'{left_name}' and '{right_name}'."
        )
    for key in left:
        left_row = left[key]
        right_row = right[key]
        if (
            left_row.dataset_id != right_row.dataset_id
            or left_row.domain != right_row.domain
            or left_row.expected_title != right_row.expected_title
        ):
            raise ValueError(
                f"Study group '{group_id}' has incompatible data for observation "
                f"{key}."
            )


def validate_groups(
    records: tuple[Observation, ...],
    groups: dict[str, StudyGroup],
) -> None:
    """Reject groups whose routes, titles, or repetition grids cannot be paired."""
    for group_id, group in groups.items():
        if group.kind == "routes":
            first_condition = group.conditions[0]
            reference_grid = _required_observations(
                records,
                group_id=group_id,
                condition_id=first_condition,
                route="direct",
            )
            for condition_id in group.conditions:
                direct = _required_observations(
                    records,
                    group_id=group_id,
                    condition_id=condition_id,
                    route="direct",
                )
                description = _required_observations(
                    records,
                    group_id=group_id,
                    condition_id=condition_id,
                    route="description",
                )
                _require_matching_observations(
                    group_id=group_id,
                    left_name=first_condition,
                    left=reference_grid,
                    right_name=condition_id,
                    right=direct,
                )
                _require_matching_observations(
                    group_id=group_id,
                    left_name=f"{condition_id}:direct",
                    left=direct,
                    right_name=f"{condition_id}:description",
                    right=description,
                )
            continue

        first_condition = group.conditions[0]
        reference_grid = _required_observations(
            records,
            group_id=group_id,
            condition_id=first_condition,
            route=group.route,
        )
        for condition_id in group.conditions[1:]:
            other_grid = _required_observations(
                records,
                group_id=group_id,
                condition_id=condition_id,
                route=group.route,
            )
            _require_matching_observations(
                group_id=group_id,
                left_name=first_condition,
                left=reference_grid,
                right_name=condition_id,
                right=other_grid,
            )


def _title_score_map(
    scores: tuple[TitleScore, ...],
    *,
    group_id: str,
    condition_id: str,
    route: str,
) -> dict[str, TitleScore]:
    result: dict[str, TitleScore] = {}
    for score in scores:
        if score.condition_id != condition_id or score.route != route:
            continue
        if score.item_id in result:
            raise ValueError(
                f"Duplicate title score for condition '{condition_id}': "
                f"{score.item_id}"
            )
        result[score.item_id] = score
    if not result:
        raise ValueError(
            f"Study group '{group_id}' has no title scores for condition "
            f"'{condition_id}' and route '{route}'."
        )
    return result


def _comparison_rows(
    *,
    group_id: str,
    kind: str,
    condition_id: str,
    reference_condition_id: str,
    condition_route: str,
    reference_route: str,
    condition_scores: dict[str, TitleScore],
    reference_scores: dict[str, TitleScore],
) -> list[ComparisonSummary]:
    if set(condition_scores) != set(reference_scores):
        raise ValueError(
            f"Study group '{group_id}' cannot pair all titles for "
            f"'{condition_id}' and '{reference_condition_id}'."
        )

    paired: list[tuple[TitleScore, TitleScore, float]] = []
    for item_id in sorted(condition_scores):
        condition = condition_scores[item_id]
        reference = reference_scores[item_id]
        if (
            condition.dataset_id != reference.dataset_id
            or condition.domain != reference.domain
            or condition.expected_title != reference.expected_title
            or condition.expected_predictions != reference.expected_predictions
        ):
            raise ValueError(
                f"Study group '{group_id}' has incompatible title '{item_id}'."
            )
        paired.append(
            (
                condition,
                reference,
                condition.end_to_end_strict_accuracy
                - reference.end_to_end_strict_accuracy,
            )
        )

    rows: list[ComparisonSummary] = []
    domains = ["all", *sorted({condition.domain for condition, _, _ in paired})]
    for domain in domains:
        selected = [
            row for row in paired if domain == "all" or row[0].domain == domain
        ]
        differences = [row[2] for row in selected]
        context = (
            f"comparison|{group_id}|{condition_id}|{reference_condition_id}|"
            f"{condition_route}|{reference_route}|{domain}"
        )
        if domain == "all":
            by_domain: dict[str, list[float]] = defaultdict(list)
            for condition, _, difference in selected:
                by_domain[condition.domain].append(difference)
            ci_low, ci_high = bootstrap_stratified_mean_interval(
                dict(by_domain),
                seed_context=context,
            )
        else:
            ci_low, ci_high = bootstrap_mean_interval(
                differences,
                seed_context=context,
            )
        rows.append(
            ComparisonSummary(
                group_id=group_id,
                kind=kind,
                condition_id=condition_id,
                reference_condition_id=reference_condition_id,
                condition_route=condition_route,
                reference_route=reference_route,
                domain=domain,
                title_count=len(selected),
                condition_accuracy=round(
                    sum(row[0].end_to_end_strict_accuracy for row in selected)
                    / len(selected),
                    8,
                ),
                reference_accuracy=round(
                    sum(row[1].end_to_end_strict_accuracy for row in selected)
                    / len(selected),
                    8,
                ),
                difference=round(sum(differences) / len(differences), 8),
                ci95_low=None if ci_low is None else round(ci_low, 8),
                ci95_high=None if ci_high is None else round(ci_high, 8),
            )
        )
    return rows


def comparison_summaries(
    scores: tuple[TitleScore, ...],
    groups: dict[str, StudyGroup],
) -> tuple[ComparisonSummary, ...]:
    """Calculate only comparisons explicitly declared in study.yaml."""
    results: list[ComparisonSummary] = []
    for group_id, group in groups.items():
        if group.kind == "accuracy":
            continue

        if group.kind == "paired":
            assert group.reference is not None
            reference_scores = _title_score_map(
                scores,
                group_id=group_id,
                condition_id=group.reference,
                route=group.route,
            )
            for condition_id in group.conditions:
                if condition_id == group.reference:
                    continue
                results.extend(
                    _comparison_rows(
                        group_id=group_id,
                        kind="paired",
                        condition_id=condition_id,
                        reference_condition_id=group.reference,
                        condition_route=group.route,
                        reference_route=group.route,
                        condition_scores=_title_score_map(
                            scores,
                            group_id=group_id,
                            condition_id=condition_id,
                            route=group.route,
                        ),
                        reference_scores=reference_scores,
                    )
                )
            continue

        for condition_id in group.conditions:
            results.extend(
                _comparison_rows(
                    group_id=group_id,
                    kind="routes",
                    condition_id=condition_id,
                    reference_condition_id=condition_id,
                    condition_route="description",
                    reference_route="direct",
                    condition_scores=_title_score_map(
                        scores,
                        group_id=group_id,
                        condition_id=condition_id,
                        route="description",
                    ),
                    reference_scores=_title_score_map(
                        scores,
                        group_id=group_id,
                        condition_id=condition_id,
                        route="direct",
                    ),
                )
            )

    return tuple(
        sorted(
            results,
            key=lambda row: (
                row.group_id,
                row.condition_id,
                row.domain != "all",
                row.domain,
            ),
        )
    )
