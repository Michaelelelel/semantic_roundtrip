"""The bounded SQ1 comparison; observations remain prompt- or image-bound."""

import hashlib
import json
from pathlib import Path

import pandas as pd
import yaml

from semantic_roundtrip.analysis.loader import load_job
from semantic_roundtrip.analysis.reporting import (
    METRIC,
    QG,
    SENSITIVITY_METRICS,
    annotate,
    difference,
    effects,
)
from semantic_roundtrip.analysis.statistics import (
    aggregate_titles,
    paired_stratified_bootstrap,
)
from semantic_roundtrip.config_resolution import load_effective_config
from semantic_roundtrip.inheritance.source import resolve_stage_provenance
from semantic_roundtrip.persistence.job.database import read_job_record
from semantic_roundtrip.persistence.job.schema import job_database_path
from semantic_roundtrip.persistence.run.config_snapshot import EFFECTIVE_CONFIG_FILENAME

PROMPT_KEYS = ["condition", "dataset_id", "domain", "item_key", "prompt_seed"]
IMAGE_KEYS = [*PROMPT_KEYS, "image_seed", "route"]
# Canonical parsed content of the unchanged visual_single v5 chat profile.
UNRESTRICTED_PROFILE_SHA256 = (
    "8d56f8382d91fda43cdb692e92404a67439761b0a5c9bee8a32db3a17affeb65"
)
RECONSTRUCTION_MODELS = {
    "q25": "qwen2.5-vl-32b-instruct-f16",
    "g3": "gemma-3-27b-it-f16",
    "q38": "qwen3.8-27b-bf16",
    "g4": "gemma-4-31b-it-bf16",
}


def _same_rows(left, right, keys, columns, label):
    columns = list(dict.fromkeys([*keys, *columns]))
    if left.duplicated(keys).any() or right.duplicated(keys).any():
        raise ValueError(f"{label}: duplicate observation identity.")
    left = left[columns].sort_values(keys).reset_index(drop=True)
    right = right[columns].sort_values(keys).reset_index(drop=True)
    try:
        pd.testing.assert_frame_equal(left, right, check_dtype=False)
    except AssertionError as error:
        raise ValueError(f"{label}: source/observation mismatch.") from error


def load_prompt_baseline(path, direct_job_path):
    """Require the full unrestricted source and its four existing indirect diagonals."""
    for directory in (path, direct_job_path):
        if (
            read_job_record(
                job_database_path(Path(directory).expanduser().resolve())
            ).status
            != "completed"
        ):
            raise ValueError(
                "SQ1 analysis requires completed source and supplement jobs."
            )
    source = load_job(direct_job_path)
    job = load_job(path)
    original = annotate(source.observations)
    observations = annotate(job.observations)
    if set(original.job_name) != {"final_direct_core"}:
        raise ValueError("SQ1 requires the unrestricted final_direct_core source.")
    if set(observations.job_name) != {"final_direct_prompt_only"}:
        raise ValueError("SQ1 requires final_direct_prompt_only.")
    entries = {f"direct_pg_{pg}_bi_{bi}" for pg in QG for bi in QG}
    if set(observations.condition) != entries or set(original.condition) != entries:
        raise ValueError("SQ1 requires all sixteen matching PG/reconstruction cells.")
    if (
        not observations.prediction_model.eq(
            observations.bi.map(RECONSTRUCTION_MODELS)
        ).all()
        or not observations.prompt_model.eq(
            observations.pg.map(RECONSTRUCTION_MODELS)
        ).all()
    ):
        raise ValueError(
            "SQ1 model identities differ from the final Qwen/Gemma matrix."
        )
    for _, entries_frame in observations.groupby("condition", sort=False):
        run_directory = Path(entries_frame.run_directory.iloc[0])
        config = load_effective_config(run_directory / EFFECTIVE_CONFIG_FILENAME)
        guessing = config.stages.title_guessing
        prompt_stage = None if guessing is None else guessing.from_prompt
        direct_source = resolve_stage_provenance(
            config, run_directory, "title_guessing_direct"
        )
        if prompt_stage is None or direct_source is None:
            raise ValueError(
                "SQ1 requires local prompt guessing and inherited Direct provenance."
            )
        direct_config = direct_source[0]
        direct_stage = direct_config.stages.title_guessing.direct
        if prompt_stage.parameters != direct_stage.parameters:
            raise ValueError("SQ1 prompt and image decoding parameters differ.")
        prompt_backend = config.backends[prompt_stage.backend].settings
        direct_backend = direct_config.backends[direct_stage.backend].settings
        for setting in (
            "model_id",
            "reasoning_effort",
            "reasoning_format",
            "thinking_budget_tokens",
            "chat_template_kwargs",
            "request_token_logprobs",
            "top_logprobs",
            "timeout_seconds",
        ):
            if prompt_backend.get(setting) != direct_backend.get(setting):
                raise ValueError(
                    f"SQ1 reconstruction backend setting differs: {setting}."
                )
    for directory in original.run_directory.unique():
        config = load_effective_config(Path(directory) / EFFECTIVE_CONFIG_FILENAME)
        provenance = resolve_stage_provenance(
            config, Path(directory), "prompt_generation"
        )
        if provenance is None:
            raise ValueError("SQ1 source has no frozen prompt-generation provenance.")
        _, defining_directory = provenance
        manifest = json.loads(
            (defining_directory / "manifest.json").read_text(encoding="utf-8")
        )
        profile_path = (
            defining_directory / manifest["artifacts"]["prompts"]["prompt_generation"]
        ).resolve()
        profile_path.relative_to(defining_directory.resolve())
        profile = yaml.safe_load(profile_path.read_text(encoding="utf-8"))
        profile_hash = hashlib.sha256(
            json.dumps(profile, sort_keys=True, ensure_ascii=False).encode("utf-8")
        ).hexdigest()
        if profile_hash != UNRESTRICTED_PROFILE_SHA256:
            raise ValueError(
                "SQ1 must not mix another style with unrestricted descriptions."
            )
    roster = observations[
        ["dataset_id", "domain", "item_key", "expected_title"]
    ].drop_duplicates()
    if set(roster.dataset_id) != {"final_titles_v1"} or roster.groupby(
        "domain"
    ).size().to_dict() != {"songs": 30, "movies": 30, "bands": 30}:
        raise ValueError("SQ1 requires the fixed ninety-title main dataset.")
    if set(observations.prompt_seed) != {1000, 1001}:
        raise ValueError("SQ1 requires the two fixed prompt seeds.")
    image_rows = observations[observations.route.ne("prompt")]
    if set(image_rows.image_seed.dropna()) != {8566257, 2875613}:
        raise ValueError("SQ1 requires the two fixed image seeds.")
    diagonal = observations.pg.eq(observations.bi)
    if (
        set(observations[observations.route.eq("description")].condition)
        != {f"direct_pg_{model}_bi_{model}" for model in QG}
        or observations[observations.route.eq("description") & ~diagonal].shape[0]
    ):
        raise ValueError(
            "SQ1 requires description reconstruction only on four diagonals."
        )
    prompt_rows = observations[observations.route.eq("prompt")]
    if (
        len(prompt_rows) != 2880
        or len(image_rows[image_rows.route.eq("direct")]) != 5760
        or len(image_rows[image_rows.route.eq("description")]) != 1440
    ):
        raise ValueError("SQ1 planned route grids are incomplete or duplicated.")
    _same_rows(
        image_rows,
        original,
        IMAGE_KEYS,
        [
            "expected_title",
            "prompt_text",
            "origin_prompt_run_id",
            "origin_prompt_id",
            "origin_image_run_id",
            "origin_image_id",
            "origin_prediction_run_id",
            "origin_prediction_id",
            "predicted_title",
            "prediction_model",
            "prompt_verification_passed",
            "strict_image_verification_passed",
            "title_aware_image_verification_passed",
        ],
        "Inherited image and description routes",
    )
    direct_prompts = image_rows[image_rows.route.eq("direct")].drop_duplicates(
        PROMPT_KEYS
    )
    _same_rows(
        prompt_rows,
        direct_prompts,
        PROMPT_KEYS,
        [
            "expected_title",
            "prompt_text",
            "origin_prompt_run_id",
            "origin_prompt_id",
            "prompt_model",
            "prediction_model",
            "prompt_verification_passed",
        ],
        "Prompt/direct pairing",
    )
    if prompt_rows.prediction_execution_origin.eq("imported").any():
        raise ValueError(
            "The SQ1 study job must execute its prompt predictions locally."
        )
    titles = pd.concat(
        [
            aggregate_titles(
                frame,
                condition_columns=["pg", "bb", "bi"],
                expected_observations=2 if route == "prompt" else 4,
            )
            for route, frame in observations.groupby("route", sort=False)
        ],
        ignore_index=True,
    )
    return job, observations, titles


def prompt_baseline_tables(observations, titles):
    """Full-grid primary/sensitivity comparisons and a labelled accepted-input diagnostic."""
    results = {}
    metric_names = [METRIC, *SENSITIVITY_METRICS]
    scored = titles.assign(condition_route=titles.condition + "__" + titles.route)
    diagonal = scored[scored.pg.eq(scored.bi)]
    absolute = []
    contrasts = []
    for scope, frame, routes in [
        (
            "16-cell prompt/direct",
            scored[scored.route.ne("description")],
            ["prompt", "direct"],
        ),
        ("four-diagonal three-route", diagonal, ["prompt", "direct", "description"]),
    ]:
        conditions = list(frame.condition.unique())
        for metric in metric_names:
            for domain, subset in [("all", frame), *frame.groupby("domain", sort=True)]:
                for route in routes:
                    names = [f"{condition}__{route}" for condition in conditions]
                    estimate = paired_stratified_bootstrap(
                        subset,
                        condition_weights=dict.fromkeys(names, 1 / len(names)),
                        condition_column="condition_route",
                        metric=metric,
                    )
                    absolute.append(
                        {
                            "scope": scope,
                            "domain": domain,
                            "route": route,
                            "metric": metric,
                            **estimate,
                        }
                    )
                for route in routes[1:]:
                    weights = difference(
                        [f"{condition}__prompt" for condition in conditions],
                        [f"{condition}__{route}" for condition in conditions],
                    )
                    estimate = paired_stratified_bootstrap(
                        subset,
                        condition_weights=weights,
                        condition_column="condition_route",
                        metric=metric,
                    )
                    contrasts.append(
                        {
                            "scope": scope,
                            "domain": domain,
                            "comparison": f"Prompt - {route}",
                            "metric": metric,
                            **estimate,
                        }
                    )
    results["sq1_route_accuracy"] = pd.DataFrame(absolute)
    results["sq1_paired_effects"] = pd.DataFrame(contrasts)
    cell_contrasts = {
        f"{pg.upper()} / {bi.upper()}: prompt - direct": difference(
            [f"direct_pg_{pg}_bi_{bi}__prompt"], [f"direct_pg_{pg}_bi_{bi}__direct"]
        )
        for pg in QG
        for bi in QG
    }
    results["sq1_cell_effects"] = effects(
        scored, cell_contrasts, condition_column="condition_route"
    )
    results["sq1_sensitivity_cell_effects"] = pd.concat(
        [
            effects(
                scored, cell_contrasts, condition_column="condition_route", metric=m
            ).assign(metric=m)
            for m in SENSITIVITY_METRICS
        ],
        ignore_index=True,
    )
    results["sq1_title_scores"] = titles
    results["sq1_observations"] = observations
    results["sq1_common_valid_inputs"] = common_valid_inputs(observations)
    results["blind_strict_sq1_common_valid_inputs"] = common_valid_inputs(
        observations, image_policy="strict"
    )
    return results


def common_valid_inputs(observations, *, image_policy="title_aware"):
    """Descriptive selected-subset means, not a replacement full-denominator endpoint."""
    if image_policy not in {"title_aware", "strict"}:
        raise ValueError("Unknown common-valid image policy.")
    rows = []
    prompts = observations[observations.route.eq("prompt")].set_index(PROMPT_KEYS)
    for scope, frame, routes in [
        ("16-cell prompt/direct", observations, ["direct"]),
        (
            "four-diagonal three-route",
            observations[observations.pg.eq(observations.bi)],
            ["direct", "description"],
        ),
    ]:
        for domain, scoped in [("all", frame), *frame.groupby("domain", sort=True)]:
            images = scoped[scoped.route.isin(routes)]
            valid = images[
                images.prompt_verification_passed.eq(True)
                & images[f"{image_policy}_image_verification_passed"].eq(True)
            ].copy()
            valid["score"] = valid.strict_exact_match.fillna(False).astype(int)
            paired = valid.pivot(
                index=[*PROMPT_KEYS, "image_seed"], columns="route", values="score"
            )
            if not paired.empty and paired.reindex(columns=routes).isna().any(
                axis=None
            ):
                raise ValueError("Common-valid diagnostic lacks a paired image route.")
            prompt_means = paired.groupby(PROMPT_KEYS).mean()
            prompt_means["prompt"] = (
                prompts.reindex(prompt_means.index)
                .strict_exact_match.fillna(False)
                .astype(int)
            )
            title_means = prompt_means.groupby(
                ["condition", "dataset_id", "domain", "item_key"]
            ).mean()
            condition_means = title_means.groupby("condition").mean()
            for route in ["prompt", *routes]:
                rows.append(
                    {
                        "scope": scope,
                        "domain": domain,
                        "route": route,
                        "image_policy": image_policy,
                        "eligible_title_conditions": len(title_means),
                        "eligible_prompts": len(prompt_means),
                        "eligible_images": len(paired),
                        "eligible_conditions": len(condition_means),
                        "strict_accuracy_percent": float(
                            100 * condition_means[route].mean()
                        )
                        if not condition_means.empty
                        else float("nan"),
                        "interpretation": "descriptive selected subset; missing predictions are zero",
                    }
                )
    return pd.DataFrame(rows)


def plot_prompt_baseline(titles, tables, output_dir):
    """One full-matrix figure and one explicitly restricted three-route figure."""
    import matplotlib.pyplot as plt

    from semantic_roundtrip.analysis.plotting import heatmap, interval_plot, save_figure

    output_dir = Path(output_dir)
    prompt = titles[titles.route.eq("prompt")]
    direct = titles[titles.route.eq("direct")]
    fig, axes = plt.subplots(1, 3, figsize=(15, 4.8), layout="constrained")
    image = heatmap(axes[0], prompt, QG, "Prompt reconstruction")
    heatmap(axes[1], direct, QG, "Direct image reconstruction")
    delta = heatmap(axes[2], prompt, QG, "Prompt - direct", baseline=direct)
    for ax in axes:
        ax.set_xlabel("Title-guessing model (TG)")
    fig.colorbar(image, ax=list(axes[:2]), label="End-to-end Strict Exact Match (%)")
    fig.colorbar(delta, ax=axes[2], label="Difference (pp)")
    save_figure(
        fig,
        output_dir / "sq1_prompt_direct_matrices",
        "SQ1: Prompt and image reconstruction, all 16 cells",
    )
    diagonal = titles[titles.pg.eq(titles.bi)]
    means = 100 * diagonal.groupby(["pg", "route"])[METRIC].mean().unstack().reindex(QG)
    fig, axes = plt.subplots(1, 2, figsize=(12, 4.5), layout="constrained")
    for route, offset, marker in [
        ("prompt", -0.15, "o"),
        ("direct", 0, "s"),
        ("description", 0.15, "^"),
    ]:
        axes[0].plot(
            [index + offset for index in range(4)],
            means[route],
            marker=marker,
            linestyle="none",
            label=route,
        )
    axes[0].set(
        xticks=range(4),
        xticklabels=[model.upper() for model in QG],
        ylim=(-2, 102),
        xlabel="Same-model diagonal (PG = ID = TG)",
        ylabel="End-to-end Strict Exact Match (%)",
    )
    axes[0].legend()
    selected = tables["sq1_paired_effects"]
    selected = selected[
        selected.scope.eq("four-diagonal three-route")
        & selected.domain.eq("all")
        & selected.metric.eq(METRIC)
    ].copy()
    for source, target in [
        ("effect", "estimate"),
        ("ci95_low", "ci95_low"),
        ("ci95_high", "ci95_high"),
    ]:
        selected[target] = 100 * selected[source]
    interval_plot(axes[1], selected)
    save_figure(
        fig,
        output_dir / "sq1_three_routes_diagonal",
        "SQ1: Three reconstruction routes, four existing diagonal baselines",
    )
