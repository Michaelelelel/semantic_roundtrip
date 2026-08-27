"""Title-level aggregation and paired comparisons used by the notebook."""

import pandas as pd

from semantic_roundtrip.analysis.bootstrap import paired_title_interval

TITLE_KEYS = [
    "condition_id",
    "design",
    "pg",
    "bg",
    "bb",
    "bi",
    "route",
    "dataset_id",
    "item_key",
    "item_index",
    "domain",
    "expected_title",
    "title_length_group",
]


def aggregate_titles(observations: pd.DataFrame) -> pd.DataFrame:
    """Average all configured seed observations before condition comparisons."""
    if observations.empty:
        return pd.DataFrame()
    grouped = observations.groupby(TITLE_KEYS, dropna=False, sort=True)
    titles = grouped.agg(
        expected_observations=("end_to_end_strict_score", "size"),
        completed_predictions=("prediction_id", "count"),
        verifier_passed_observations=(
            "verification_passed",
            lambda values: values.fillna(False).astype(bool).sum(),
        ),
        strict_accuracy=(
            "strict_exact_match",
            lambda values: values.fillna(False).astype(bool).mean(),
        ),
        normalized_accuracy=(
            "normalized_exact_match",
            lambda values: values.fillna(False).astype(bool).mean(),
        ),
        end_to_end_strict_accuracy=("end_to_end_strict_score", "mean"),
        end_to_end_normalized_accuracy=("end_to_end_normalized_score", "mean"),
    )
    return titles.reset_index()


def condition_summary(title_scores: pd.DataFrame) -> pd.DataFrame:
    """Summarize title-weighted outcomes overall and separately per domain."""
    if title_scores.empty:
        return pd.DataFrame()
    grouping = ["condition_id", "design", "pg", "bg", "bb", "bi", "route"]
    rows: list[pd.DataFrame] = []
    selections: list[tuple[str, pd.DataFrame]] = [("overall", title_scores)]
    selections.extend(
        (str(domain), selected)
        for domain, selected in title_scores.groupby("domain", sort=True)
    )
    for domain, selected in selections:
        summary = (
            selected.groupby(grouping, dropna=False, sort=True)
            .agg(
                titles=("item_key", "size"),
                end_to_end_strict_accuracy=("end_to_end_strict_accuracy", "mean"),
                end_to_end_normalized_accuracy=(
                    "end_to_end_normalized_accuracy",
                    "mean",
                ),
                completed_predictions=("completed_predictions", "sum"),
                expected_observations=("expected_observations", "sum"),
                verifier_passed=("verifier_passed_observations", "sum"),
            )
            .reset_index()
        )
        summary["completion_rate"] = (
            summary["completed_predictions"] / summary["expected_observations"]
        )
        summary["verifier_pass_rate"] = (
            summary["verifier_passed"] / summary["expected_observations"]
        )
        summary["domain"] = domain
        rows.append(summary)
    return pd.concat(rows, ignore_index=True)


def paired_title_differences(
    title_scores: pd.DataFrame,
    *,
    left_condition: str,
    right_condition: str,
    left_route: str = "direct",
    right_route: str = "direct",
    metric: str = "end_to_end_strict_accuracy",
) -> pd.DataFrame:
    """Pair two conditions by title and return left-minus-right effects."""
    identity = [
        "dataset_id",
        "item_key",
        "item_index",
        "domain",
        "expected_title",
        "title_length_group",
    ]
    left = title_scores[
        (title_scores["condition_id"] == left_condition)
        & (title_scores["route"] == left_route)
    ][[*identity, metric]].rename(columns={metric: "left"})
    right = title_scores[
        (title_scores["condition_id"] == right_condition)
        & (title_scores["route"] == right_route)
    ][[*identity, metric]].rename(columns={metric: "right"})
    paired = left.merge(
        right,
        on=identity,
        how="outer",
        validate="one_to_one",
        indicator=True,
    )
    if not (paired["_merge"] == "both").all():
        raise ValueError(
            f"Conditions '{left_condition}:{left_route}' and "
            f"'{right_condition}:{right_route}' do not share one complete title grid."
        )
    paired = paired.drop(columns="_merge")
    paired["difference"] = paired["left"] - paired["right"]
    return paired


def paired_effect(
    title_scores: pd.DataFrame,
    *,
    left_condition: str,
    right_condition: str,
    left_route: str = "direct",
    right_route: str = "direct",
    metric: str = "end_to_end_strict_accuracy",
    domain: str | None = None,
) -> dict[str, float | int | str]:
    """Return one predeclared paired effect with a title-resampled interval."""
    paired = paired_title_differences(
        title_scores,
        left_condition=left_condition,
        right_condition=right_condition,
        left_route=left_route,
        right_route=right_route,
        metric=metric,
    )
    if domain is not None:
        paired = paired[paired["domain"] == domain]
    context = (
        f"{left_condition}:{left_route}-{right_condition}:{right_route}:"
        f"{metric}:{domain or 'overall'}"
    )
    estimate, low, high = paired_title_interval(paired, context=context)
    return {
        "left_condition": left_condition,
        "right_condition": right_condition,
        "left_route": left_route,
        "right_route": right_route,
        "metric": metric,
        "domain": domain or "overall",
        "titles": len(paired),
        "effect": estimate,
        "ci95_low": low,
        "ci95_high": high,
    }


def weighted_title_effect(
    title_scores: pd.DataFrame,
    *,
    condition_weights: dict[str, float],
    route: str,
    label: str,
    metric: str = "end_to_end_strict_accuracy",
    domain: str | None = None,
) -> dict[str, float | int | str]:
    """Estimate one predeclared linear contrast from paired title values.

    Conditions are first aligned by title. The supplied weights may sum to zero
    for a difference or to one for a marginal mean. Every selected condition must
    contain every selected title exactly once.
    """
    if not condition_weights:
        raise ValueError("A weighted title effect requires at least one condition.")
    selected = title_scores[
        (title_scores["condition_id"].isin(condition_weights))
        & (title_scores["route"] == route)
    ]
    if domain is not None:
        selected = selected[selected["domain"] == domain]
    identity = [
        "dataset_id",
        "item_key",
        "item_index",
        "domain",
        "expected_title",
        "title_length_group",
    ]
    pivot = selected.pivot(index=identity, columns="condition_id", values=metric)
    expected_columns = set(condition_weights)
    actual_columns = set(pivot.columns.astype(str))
    if actual_columns != expected_columns or pivot.isna().any(axis=None):
        raise ValueError(
            f"Contrast '{label}' does not have one complete paired title grid."
        )

    values = sum(
        pivot[condition_id].astype(float) * weight
        for condition_id, weight in condition_weights.items()
    )
    differences = pivot.reset_index()[["domain", "title_length_group"]]
    differences["difference"] = values.to_numpy()
    context = f"{label}:{route}:{metric}:{domain or 'overall'}"
    estimate, low, high = paired_title_interval(differences, context=context)
    return {
        "label": label,
        "route": route,
        "metric": metric,
        "domain": domain or "overall",
        "titles": len(differences),
        "effect": estimate,
        "ci95_low": low,
        "ci95_high": high,
    }
