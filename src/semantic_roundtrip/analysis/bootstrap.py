"""Deterministic clustered-bootstrap helpers for title-level estimates."""

import random


BOOTSTRAP_REPETITIONS = 10_000
BOOTSTRAP_SEED = 20260806


def _percentile(sorted_values: list[float], proportion: float) -> float:
    position = (len(sorted_values) - 1) * proportion
    lower = int(position)
    upper = min(lower + 1, len(sorted_values) - 1)
    fraction = position - lower
    return sorted_values[lower] + fraction * (
        sorted_values[upper] - sorted_values[lower]
    )


def bootstrap_mean_interval(
    values: list[float],
    *,
    seed_context: str,
) -> tuple[float | None, float | None]:
    """Return a deterministic 95% percentile interval for a mean."""
    if not values:
        return None, None
    if len(values) == 1:
        return values[0], values[0]

    random_generator = random.Random(f"{BOOTSTRAP_SEED}:{seed_context}")
    sample_size = len(values)
    means = [
        sum(random_generator.choices(values, k=sample_size)) / sample_size
        for _ in range(BOOTSTRAP_REPETITIONS)
    ]
    means.sort()
    return _percentile(means, 0.025), _percentile(means, 0.975)


def bootstrap_stratified_mean_interval(
    values_by_stratum: dict[str, list[float]],
    *,
    seed_context: str,
) -> tuple[float | None, float | None]:
    """Return a 95% interval while preserving each domain's title count."""
    strata = [
        values_by_stratum[name]
        for name in sorted(values_by_stratum)
        if values_by_stratum[name]
    ]
    total_size = sum(len(values) for values in strata)
    if total_size == 0:
        return None, None
    if total_size == 1:
        value = strata[0][0]
        return value, value

    random_generator = random.Random(f"{BOOTSTRAP_SEED}:{seed_context}")
    means: list[float] = []
    for _ in range(BOOTSTRAP_REPETITIONS):
        sampled_sum = 0.0
        for values in strata:
            sampled_sum += sum(random_generator.choices(values, k=len(values)))
        means.append(sampled_sum / total_size)

    means.sort()
    return _percentile(means, 0.025), _percentile(means, 0.975)
