"""Deterministic paired title resampling for predeclared study effects."""

from hashlib import sha256

import numpy as np
import pandas as pd

BOOTSTRAP_REPETITIONS = 10_000
BOOTSTRAP_SEED = 20260827


def _context_seed(context: str) -> int:
    digest = sha256(f"{BOOTSTRAP_SEED}:{context}".encode()).digest()
    return int.from_bytes(digest[:8], "big")


def paired_title_interval(
    differences: pd.DataFrame,
    *,
    value_column: str = "difference",
    context: str,
    repetitions: int = BOOTSTRAP_REPETITIONS,
) -> tuple[float, float, float]:
    """Return mean effect and a paired, stratified 95% percentile interval.

    Each input row represents one complete title. Sampling happens independently
    inside domain/title-length strata while preserving each stratum's size.
    """
    required = {value_column, "domain", "title_length_group"}
    missing = required - set(differences.columns)
    if missing:
        raise ValueError(f"Paired interval is missing columns: {sorted(missing)}")
    if differences.empty:
        raise ValueError("Paired interval requires at least one title.")
    if repetitions < 1:
        raise ValueError("Bootstrap repetitions must be positive.")

    values = differences[value_column].astype(float)
    estimate = float(values.mean())
    if len(values) == 1:
        return estimate, estimate, estimate

    rng = np.random.default_rng(_context_seed(context))
    sampled_sums = np.zeros(repetitions, dtype=float)
    total = 0
    grouped = differences.groupby(
        ["domain", "title_length_group"],
        sort=True,
        dropna=False,
    )
    for _, stratum in grouped:
        stratum_values = stratum[value_column].to_numpy(dtype=float)
        size = len(stratum_values)
        sampled_sums += rng.choice(
            stratum_values,
            size=(repetitions, size),
            replace=True,
        ).sum(axis=1)
        total += size

    sampled_means = sampled_sums / total
    low, high = np.quantile(sampled_means, [0.025, 0.975])
    return estimate, float(low), float(high)
