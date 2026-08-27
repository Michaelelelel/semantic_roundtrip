"""Frozen final-study matrix definitions and validation helpers."""

from collections.abc import Iterable

import pandas as pd

DIRECT_CONDITIONS: frozenset[tuple[str, str]] = frozenset(
    {
        ("q25", "q25"),
        ("q25", "q38"),
        ("q25", "g3"),
        ("q38", "q38"),
        ("q38", "q25"),
        ("q38", "g4"),
        ("g3", "g3"),
        ("g3", "g4"),
        ("g3", "q25"),
        ("g4", "g4"),
        ("g4", "g3"),
        ("g4", "q38"),
    }
)
LOCAL_TEXT_MODELS: tuple[str, ...] = ("d32", "o120")
DESCRIPTION_MODELS: tuple[str, ...] = ("q25", "g3", "q38", "g4")
ALL_TEXT_MODELS: tuple[str, ...] = (*LOCAL_TEXT_MODELS, "v4")
LOCAL_INDIRECT_CONDITIONS: frozenset[tuple[str, str, str]] = frozenset(
    (pg, bb, bi)
    for pg in LOCAL_TEXT_MODELS
    for bb in DESCRIPTION_MODELS
    for bi in LOCAL_TEXT_MODELS
)
AQUEDUCT_CONDITIONS: frozenset[tuple[str, str, str]] = frozenset(
    (pg, bb, bi)
    for pg in ALL_TEXT_MODELS
    for bb in DESCRIPTION_MODELS
    for bi in ALL_TEXT_MODELS
    if pg == "v4" or bi == "v4"
)

DIRECT_COMPARISONS: dict[str, tuple[str, str]] = {
    "qwen_release_period": ("q25", "q38"),
    "gemma_release_period": ("g3", "g4"),
    "family_2025": ("q25", "g3"),
    "family_2026": ("q38", "g4"),
}

EXPECTED_DATASET_ID = "final_titles_v1"
EXPECTED_PROMPT_SEEDS = (1000, 1001)
EXPECTED_IMAGE_SEEDS = (8566257, 2875613)
EXPECTED_RETRY_LIMIT = 1
MODEL_IDS: dict[str, str] = {
    "q25": "qwen2.5-vl-32b-instruct-f16",
    "g3": "gemma-3-27b-it-f16",
    "q38": "qwen3.8-27b-bf16",
    "g4": "gemma-4-31b-it-bf16",
    "d32": "deepseek-r1-distill-qwen-32b-f16",
    "o120": "gpt-oss-120b-mxfp4",
    "v4": "deepseek-v4-flash-284b",
}


def _tuples(frame: pd.DataFrame, columns: Iterable[str]) -> set[tuple[str, ...]]:
    return {
        tuple(str(value) for value in row)
        for row in frame[list(columns)].itertuples(index=False, name=None)
    }


def _require_matrix(
    frame: pd.DataFrame,
    *,
    design: str,
    columns: tuple[str, ...],
    expected: frozenset[tuple[str, ...]],
) -> None:
    selected = frame[frame["design"] == design]
    actual = _tuples(selected, columns)
    if actual == expected and len(selected) == len(expected):
        return
    missing = sorted(expected - actual)
    unexpected = sorted(actual - expected)
    raise ValueError(
        f"Study design '{design}' is incomplete or duplicated: "
        f"rows={len(selected)}, expected={len(expected)}, "
        f"missing={missing}, unexpected={unexpected}."
    )


def validate_final_design(runs: pd.DataFrame) -> dict[str, int]:
    """Require the frozen local matrix and validate an optional V4 extension."""
    required_columns = {
        "condition_id",
        "design",
        "pg",
        "bg",
        "bb",
        "bi",
        "routes",
        "dataset_id",
        "title_count",
        "prompt_seeds",
        "image_seeds",
        "retry_limit",
        "verifier_model",
        "prompt_model",
        "image_model",
        "description_model",
        "direct_model",
        "description_title_model",
    }
    missing_columns = required_columns - set(runs.columns)
    if missing_columns:
        raise ValueError(
            f"Study run table is missing columns: {sorted(missing_columns)}"
        )
    if runs["condition_id"].duplicated().any():
        duplicates = sorted(
            runs.loc[runs["condition_id"].duplicated(), "condition_id"].astype(str)
        )
        raise ValueError(f"Study contains duplicate condition IDs: {duplicates}")

    _require_matrix(
        runs,
        design="direct_core",
        columns=("pg", "bi"),
        expected=DIRECT_CONDITIONS,
    )
    _require_matrix(
        runs,
        design="indirect_local",
        columns=("pg", "bb", "bi"),
        expected=LOCAL_INDIRECT_CONDITIONS,
    )

    aqueduct = runs[runs["design"] == "aqueduct_v4_extension"]
    if not aqueduct.empty:
        _require_matrix(
            runs,
            design="aqueduct_v4_extension",
            columns=("pg", "bb", "bi"),
            expected=AQUEDUCT_CONDITIONS,
        )

    known_designs = {"direct_core", "indirect_local", "aqueduct_v4_extension"}
    unexpected_designs = sorted(set(runs["design"].astype(str)) - known_designs)
    if unexpected_designs:
        raise ValueError(f"Study contains unknown designs: {unexpected_designs}")

    for row in runs.itertuples(index=False):
        if row.bg != "sd35":
            raise ValueError(f"Condition '{row.condition_id}' does not use BG=sd35.")
        if row.dataset_id != EXPECTED_DATASET_ID or row.title_count != 90:
            raise ValueError(
                f"Condition '{row.condition_id}' does not use final_titles_v1 (90)."
            )
        if tuple(row.prompt_seeds) != EXPECTED_PROMPT_SEEDS:
            raise ValueError(
                f"Condition '{row.condition_id}' has unexpected prompt seeds."
            )
        if tuple(row.image_seeds) != EXPECTED_IMAGE_SEEDS:
            raise ValueError(
                f"Condition '{row.condition_id}' has unexpected image seeds."
            )
        if row.retry_limit != EXPECTED_RETRY_LIMIT:
            raise ValueError(
                f"Condition '{row.condition_id}' has unexpected retry_limit."
            )
        if row.verifier_model != "qwen3-vl-8b-instruct-f16":
            raise ValueError(
                f"Condition '{row.condition_id}' uses the wrong verifier model."
            )
        if row.prompt_model != MODEL_IDS[row.pg]:
            raise ValueError(
                f"Condition '{row.condition_id}' has a PG model/config mismatch."
            )
        if row.image_model != "stable-diffusion-3.5-large-bf16":
            raise ValueError(
                f"Condition '{row.condition_id}' uses the wrong image model."
            )

        routes = tuple(row.routes)
        if row.design == "direct_core":
            expected_routes = (
                ("direct", "description") if row.pg == row.bi else ("direct",)
            )
            if routes != expected_routes:
                raise ValueError(
                    f"Condition '{row.condition_id}' has routes {routes}; "
                    f"expected {expected_routes}."
                )
            if row.pg == row.bi and row.bb != row.bi:
                raise ValueError(
                    f"Condition '{row.condition_id}' must use BB=BI on its "
                    "description route."
                )
            if row.direct_model != MODEL_IDS[row.bi]:
                raise ValueError(
                    f"Condition '{row.condition_id}' has a BI model/config mismatch."
                )
            if row.pg == row.bi and (
                row.description_model != MODEL_IDS[row.bb]
                or row.description_title_model != MODEL_IDS[row.bi]
            ):
                raise ValueError(
                    f"Condition '{row.condition_id}' has a BB/BI model mismatch."
                )
        elif routes != ("description",):
            raise ValueError(
                f"Condition '{row.condition_id}' must contain only description."
            )
        elif (
            row.description_model != MODEL_IDS[row.bb]
            or row.description_title_model != MODEL_IDS[row.bi]
        ):
            raise ValueError(
                f"Condition '{row.condition_id}' has a BB/BI model mismatch."
            )

    return {
        "direct_core": len(DIRECT_CONDITIONS),
        "indirect_local": len(LOCAL_INDIRECT_CONDITIONS),
        "aqueduct_v4_extension": len(aqueduct),
    }
