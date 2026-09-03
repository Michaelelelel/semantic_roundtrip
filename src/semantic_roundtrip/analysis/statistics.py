"""Small, reusable calculations for the final thesis notebook."""

from __future__ import annotations

from collections.abc import Iterable, Mapping

import numpy as np
import pandas as pd

from semantic_roundtrip.evaluation import (
    title_exact_match,
    title_normalized_exact_match,
)

BOOTSTRAP_REPETITIONS = 10_000
BOOTSTRAP_SEED = 20260829


def score_observations(observations: pd.DataFrame) -> pd.DataFrame:
    """Add title matches and end-to-end scores for both image policies."""
    result = observations.copy()
    if result.empty:
        return result

    strict: list[bool | None] = []
    normalized: list[bool | None] = []
    for expected, predicted in zip(
        result["expected_title"], result["predicted_title"], strict=True
    ):
        if pd.isna(predicted):
            strict.append(None)
            normalized.append(None)
        else:
            strict.append(title_exact_match(str(expected), str(predicted)))
            normalized.append(
                title_normalized_exact_match(str(expected), str(predicted))
            )
    result["strict_exact_match"] = pd.array(strict, dtype="boolean")
    result["normalized_exact_match"] = pd.array(normalized, dtype="boolean")
    prompt_configured = result["prompt_verification_configured"].astype(bool)
    prompt_passed = result["prompt_verification_passed"].astype("boolean")
    prompt_gate = (~prompt_configured) | prompt_passed.fillna(False)
    strict_configured = result["strict_image_verification_configured"].astype(bool)
    strict_passed = (
        result["strict_image_verification_passed"].astype("boolean").fillna(False)
    )
    strict_gate = (~strict_configured) | strict_passed
    result["end_to_end_strict_score"] = (
        prompt_gate & strict_gate & result["strict_exact_match"].fillna(False)
    ).astype(int)
    result["end_to_end_normalized_score"] = (
        prompt_gate & strict_gate & result["normalized_exact_match"].fillna(False)
    ).astype(int)
    title_aware_configured = result["title_aware_image_verification_configured"].astype(
        bool
    )
    title_aware_passed = (
        result["title_aware_image_verification_passed"].astype("boolean").fillna(False)
    )
    result["title_aware_end_to_end_strict_score"] = pd.array(
        np.where(
            title_aware_configured,
            (
                prompt_gate
                & title_aware_passed
                & result["strict_exact_match"].fillna(False)
            ).astype(int),
            pd.NA,
        ),
        dtype="Int64",
    )
    result["title_aware_end_to_end_normalized_score"] = pd.array(
        np.where(
            title_aware_configured,
            (
                prompt_gate
                & title_aware_passed
                & result["normalized_exact_match"].fillna(False)
            ).astype(int),
            pd.NA,
        ),
        dtype="Int64",
    )
    return result


def aggregate_titles(
    observations: pd.DataFrame,
    *,
    condition_columns: Iterable[str] = (),
    expected_observations: int = 4,
) -> pd.DataFrame:
    """Average seed observations before comparing experimental conditions."""
    if observations.empty:
        return pd.DataFrame()
    keys = [
        "condition",
        *condition_columns,
        "route",
        "dataset_id",
        "item_key",
        "item_index",
        "domain",
        "expected_title",
        "title_length_group",
    ]
    keys = list(dict.fromkeys(keys))
    grouped = observations.groupby(keys, dropna=False, sort=True)
    result = grouped.agg(
        observations=("end_to_end_strict_score", "size"),
        predictions=("prediction_id", "count"),
        verifier_passes=(
            "strict_image_verification_passed",
            lambda values: values.eq(True).sum(),
        ),
        prompt_verification_passes=(
            "prompt_verification_passed",
            lambda values: values.eq(True).sum(),
        ),
        title_aware_image_verification_passes=(
            "title_aware_image_verification_passed",
            lambda values: values.eq(True).sum(),
        ),
        prediction_only_strict_accuracy=(
            "strict_exact_match",
            lambda values: values.astype("boolean").mean(),
        ),
        prediction_only_normalized_accuracy=(
            "normalized_exact_match",
            lambda values: values.astype("boolean").mean(),
        ),
        end_to_end_strict_accuracy=("end_to_end_strict_score", "mean"),
        end_to_end_normalized_accuracy=("end_to_end_normalized_score", "mean"),
        title_aware_end_to_end_strict_accuracy=(
            "title_aware_end_to_end_strict_score",
            "mean",
        ),
        title_aware_end_to_end_normalized_accuracy=(
            "title_aware_end_to_end_normalized_score",
            "mean",
        ),
    ).reset_index()
    wrong = result[result["observations"] != expected_observations]
    if not wrong.empty:
        raise ValueError(
            "Title aggregation found a condition with "
            f"{int(wrong.iloc[0]['observations'])} instead of "
            f"{expected_observations} seed observations."
        )
    return result


def _stratified_groups(
    frame: pd.DataFrame,
    strata: tuple[str, ...],
) -> tuple[np.ndarray, ...]:
    groups = frame.groupby(list(strata), sort=True, dropna=False).indices
    return tuple(np.asarray(index, dtype=int) for index in groups.values())


def _stratified_samples(
    groups: tuple[np.ndarray, ...],
    rng: np.random.Generator,
    repetitions: int,
) -> np.ndarray:
    """Rows are whole-title resamples; each stratum keeps its original size."""
    return np.column_stack(
        [
            rng.choice(index, size=(repetitions, len(index)), replace=True)
            for index in groups
        ]
    )


def paired_stratified_bootstrap(
    title_scores: pd.DataFrame,
    *,
    condition_weights: Mapping[str, float],
    metric: str = "end_to_end_strict_accuracy",
    condition_column: str = "condition",
    repetitions: int = BOOTSTRAP_REPETITIONS,
    seed: int = BOOTSTRAP_SEED,
    strata: tuple[str, ...] = ("domain",),
) -> dict[str, float | int]:
    """Estimate one paired title contrast and its stratified percentile interval."""
    if not condition_weights:
        raise ValueError("At least one condition weight is required.")
    if repetitions < 1:
        raise ValueError("Bootstrap repetitions must be positive.")
    identity = ["dataset_id", "item_key", *strata]
    selected = title_scores[title_scores[condition_column].isin(condition_weights)]
    pivot = selected.pivot(
        index=identity,
        columns=condition_column,
        values=metric,
    )
    if set(pivot.columns) != set(condition_weights) or pivot.isna().any(axis=None):
        raise ValueError("Contrast does not have one complete paired title grid.")
    contrast = pivot.reset_index()[identity]
    contrast["value"] = sum(
        pivot[condition].to_numpy(dtype=float) * weight
        for condition, weight in condition_weights.items()
    )
    estimate = float(contrast["value"].mean())
    rng = np.random.default_rng(seed)
    groups = _stratified_groups(contrast, strata)
    sampled = _stratified_samples(groups, rng, repetitions)
    samples = contrast["value"].to_numpy(dtype=float)[sampled].mean(axis=1)
    low, high = np.quantile(samples, [0.025, 0.975])
    return {
        "titles": len(contrast),
        "effect": estimate,
        "ci95_low": float(low),
        "ci95_high": float(high),
    }


def _spearman(x: pd.Series, y: pd.Series) -> float:
    if x.nunique(dropna=True) < 2 or y.nunique(dropna=True) < 2:
        return float("nan")
    return float(np.corrcoef(x.rank(method="average"), y.rank(method="average"))[0, 1])


def illustratability_spearman(
    ratings: pd.DataFrame,
    outcomes: pd.DataFrame,
    *,
    model_column: str = "pg",
    outcome_column: str = "end_to_end_strict_accuracy",
    repetitions: int = BOOTSTRAP_REPETITIONS,
    seed: int = BOOTSTRAP_SEED,
) -> pd.DataFrame:
    """Correlate ratings with title outcomes, separately for each PG model."""
    if repetitions < 1:
        raise ValueError("Bootstrap repetitions must be positive.")
    keys = [model_column, "dataset_id", "item_key", "domain", "title_length_group"]
    rating_values = ratings[[*keys, "score"]].dropna(subset=["score"])
    outcome_values = outcomes[[*keys, outcome_column]].dropna(subset=[outcome_column])
    merged = rating_values.merge(
        outcome_values,
        on=keys,
        how="inner",
        validate="one_to_one",
    )
    result: list[dict[str, float | int | str]] = []
    for offset, (model, frame) in enumerate(
        merged.groupby(model_column, sort=True, dropna=False)
    ):
        rho = _spearman(frame["score"], frame[outcome_column])
        if np.isnan(rho):
            valid = np.empty(0, dtype=float)
            low = high = float("nan")
        else:
            rng = np.random.default_rng(seed + offset)
            groups = _stratified_groups(
                frame,
                ("domain",),
            )
            sampled = _stratified_samples(groups, rng, repetitions)
            # Rank each resample independently, including average ranks for ties.
            x = pd.DataFrame(frame["score"].to_numpy()[sampled]).rank(axis=1).to_numpy()
            y = (
                pd.DataFrame(frame[outcome_column].to_numpy()[sampled])
                .rank(axis=1)
                .to_numpy()
            )
            x -= x.mean(axis=1, keepdims=True)
            y -= y.mean(axis=1, keepdims=True)
            denominator = np.sqrt((x * x).sum(axis=1) * (y * y).sum(axis=1))
            bootstrap = np.full(repetitions, np.nan)
            np.divide(
                (x * y).sum(axis=1), denominator, out=bootstrap, where=denominator > 0
            )
            valid = bootstrap[~np.isnan(bootstrap)]
            if len(valid) < repetitions * 0.95:
                low = high = float("nan")
            else:
                low, high = np.quantile(valid, [0.025, 0.975])
        result.append(
            {
                model_column: str(model),
                "titles": len(frame),
                "spearman_rho": rho,
                "ci95_low": float(low),
                "ci95_high": float(high),
                "valid_bootstrap_repetitions": len(valid),
            }
        )
    return pd.DataFrame.from_records(
        result,
        columns=[
            model_column,
            "titles",
            "spearman_rho",
            "ci95_low",
            "ci95_high",
            "valid_bootstrap_repetitions",
        ],
    )
