"""Study tables shared by the three notebooks; no plotting or model calls.

Seed aggregation and bootstrap live in statistics.py. These functions only
assemble the specified study contrasts, summaries and reproducibility exports.
"""

import hashlib
import json
import platform
from datetime import UTC, datetime
from importlib.metadata import version
from pathlib import Path

import numpy as np
import pandas as pd

from semantic_roundtrip import evaluation
from semantic_roundtrip.analysis.loader import load_job
from semantic_roundtrip.analysis.statistics import (
    aggregate_titles,
    paired_stratified_bootstrap,
)
from semantic_roundtrip.config_resolution import load_effective_config
from semantic_roundtrip.evaluation import (
    EXACT_MATCH_METHOD,
    NORMALIZED_EXACT_METHOD,
    PROMPT_TITLE_MATCH_METHOD,
    STRICT_IMAGE_VERIFICATION_METHOD,
    TITLE_AWARE_IMAGE_VERIFICATION_METHOD,
)
from semantic_roundtrip.job import JOB_SNAPSHOT_FILENAME, load_job_snapshot
from semantic_roundtrip.persistence.job.database import (
    read_job_entries,
    read_job_record,
)
from semantic_roundtrip.persistence.run.config_snapshot import EFFECTIVE_CONFIG_FILENAME

QG = ["q25", "g3", "q38", "g4"]
LOCAL = ["d32", "o120"]
TEXT = [*LOCAL, "v4"]
PAIRS = {
    "Qwen": ("q25", "q38"),
    "Gemma": ("g3", "g4"),
    "Family 2025": ("q25", "g3"),
    "Family 2026": ("q38", "g4"),
}
DOMAINS = {
    "songs": ("#0072B2", "o"),
    "movies": ("#D55E00", "s"),
    "bands": ("#009E73", "^"),
}
METRIC = "end_to_end_strict_accuracy"
TITLE_KEYS = ["dataset_id", "item_key", "domain", "title_length_group"]
RATING_KEYS = ["pg", *TITLE_KEYS]
INTERVAL_COLUMNS = ["estimate", "ci95_low", "ci95_high"]
STYLE_METRICS = {
    METRIC: (
        "Strict image / strict title",
        f"{STRICT_IMAGE_VERIFICATION_METHOD}+{EXACT_MATCH_METHOD}",
        "#0072B2",
        "o",
    ),
    "end_to_end_normalized_accuracy": (
        "Strict image / normalized title",
        f"{STRICT_IMAGE_VERIFICATION_METHOD}+{NORMALIZED_EXACT_METHOD}",
        "#D55E00",
        "s",
    ),
    "title_aware_end_to_end_strict_accuracy": (
        "Title-aware image / strict title",
        f"{TITLE_AWARE_IMAGE_VERIFICATION_METHOD}+{EXACT_MATCH_METHOD}",
        "#009E73",
        "^",
    ),
    "title_aware_end_to_end_normalized_accuracy": (
        "Title-aware image / normalized title",
        f"{TITLE_AWARE_IMAGE_VERIFICATION_METHOD}+{NORMALIZED_EXACT_METHOD}",
        "#CC79A7",
        "D",
    ),
}


def annotate(frame):
    """Extract PG, BB and BI model labels from the configured condition names."""
    roles = frame["entry_name"].str.extract(
        "^(?:direct|indirect)_pg_(?P<pg>[^_]+)(?:_bb_(?P<bb>[^_]+))?_bi_(?P<bi>[^_]+)$"
    )
    return frame.join(roles)


def difference(positive, negative):
    """Weights for mean(positive conditions) minus mean(negative conditions)."""
    positive, negative = (list(positive), list(negative))
    return {c: 1 / len(positive) for c in positive} | {
        c: -1 / len(negative) for c in negative
    }


def effects(frame, contrasts, condition_column="condition"):
    """Evaluate contrasts overall and per domain; report estimates and CIs in pp."""
    rows = []
    for domain, subset in [("all", frame), *frame.groupby("domain", sort=True)]:
        for comparison, weights in contrasts.items():
            result = paired_stratified_bootstrap(
                subset, condition_weights=weights, condition_column=condition_column
            )
            rows.append({"domain": domain, "comparison": comparison, **result})
    table = pd.DataFrame(rows).rename(columns={"effect": "estimate"})
    table[INTERVAL_COLUMNS] *= 100
    return table


def indirect_contrasts(frame):
    """Planned model-role contrasts, keeping hosted and local scopes explicit."""
    cells = (
        frame[["condition", "pg", "bb", "bi"]].drop_duplicates().set_index("condition")
    )
    contrasts = {}
    for role in ["pg", "bb", "bi"]:
        pairs = (
            [(f"{y.upper()} − {x.upper()}", [y], [x]) for x, y in PAIRS.values()]
            if role == "bb"
            else [("O120 − D32", ["o120"], ["d32"])]
        )
        if role != "bb" and "v4" in cells[role].values:
            pairs.append(("V4 − mean(D32, O120)", ["v4"], LOCAL))
        for label, positive, negative in pairs:
            contrasts[f"{role.upper()}: {label}"] = difference(
                cells.index[cells[role].isin(positive)],
                cells.index[cells[role].isin(negative)],
            )
    return contrasts


def matching_contrasts(frame):
    """Equal-condition same-versus-mixed PG/BI differences, overall and per BB."""
    cells = (
        frame[["condition", "pg", "bb", "bi"]].drop_duplicates().set_index("condition")
    )
    contrasts = {}
    for label, subset in [
        ("All BB", cells),
        *[(f"BB={bb.upper()}", cells[cells.bb == bb]) for bb in QG],
    ]:
        contrasts[label] = difference(
            subset.index[subset.pg == subset.bi], subset.index[subset.pg != subset.bi]
        )
    return contrasts


def accuracy_rates(
    planned, predictions, end_to_end_correct, prediction_correct, accepted
):
    """Count-based percentages with distinct denominators; empty subsets are n/a."""
    return pd.DataFrame(
        {
            "end_to_end_strict_accuracy": 100 * end_to_end_correct / planned,
            "prediction_only_strict_accuracy": 100
            * prediction_correct
            / predictions.replace(0, np.nan),
            "verifier_accepted_strict_accuracy": 100
            * end_to_end_correct
            / accepted.replace(0, np.nan),
            "coverage": 100 * predictions / planned,
            "acceptance_rate": 100 * accepted / planned,
        }
    )


def technical_tables(observation_sets, title_sets, job_sets):
    """Supporting metrics/counts plus provenance-deduplicated errors and timings."""
    tables = {}
    accuracy_rows, verifier_rows = ([], [])
    for study, observations in observation_sets.items():
        observations = observations.copy()
        observations["route_verification_passed"] = observations[
            "strict_image_verification_passed"
        ].where(
            ~observations.route.eq("prompt"), observations.prompt_verification_passed
        )
        scoped = pd.concat([observations, observations.assign(domain="all")])
        scoped = pd.concat([scoped, scoped.assign(condition="all")])
        grouped = (
            scoped.groupby(["condition", "route", "domain"], sort=True)
            .agg(
                planned_observations=("image_seed", "size"),
                predictions=("prediction_id", "count"),
                prediction_correct=(
                    "strict_exact_match",
                    lambda s: int(s.astype("boolean").fillna(False).sum()),
                ),
                end_to_end_correct=("end_to_end_strict_score", "sum"),
                end_to_end_normalized_correct=(
                    "end_to_end_normalized_score",
                    "sum",
                ),
                title_aware_end_to_end_correct=(
                    "title_aware_end_to_end_strict_score",
                    lambda s: s.sum(min_count=1),
                ),
                title_aware_end_to_end_normalized_correct=(
                    "title_aware_end_to_end_normalized_score",
                    lambda s: s.sum(min_count=1),
                ),
                prompt_accepted_observations=(
                    "prompt_verification_passed",
                    lambda s: int(s.eq(True).sum()),
                ),
                accepted=(
                    "route_verification_passed",
                    lambda s: int(s.eq(True).sum()),
                ),
                verifier_rejections=(
                    "route_verification_passed",
                    lambda s: int(s.eq(False).sum()),
                ),
                missing_verifier_decisions=(
                    "route_verification_passed",
                    lambda s: int(s.isna().sum()),
                ),
                missing_predictions_with_error=(
                    "prediction_status",
                    lambda s: int(s.eq("failed").sum()),
                ),
            )
            .reset_index()
        )
        grouped.insert(0, "study", study)
        grouped["missing_predictions"] = (
            grouped.planned_observations - grouped.predictions
        )
        grouped[
            [
                "end_to_end_strict_accuracy",
                "prediction_only_strict_accuracy",
                "verifier_accepted_strict_accuracy",
                "coverage",
                "acceptance_rate",
            ]
        ] = accuracy_rates(
            grouped.planned_observations,
            grouped.predictions,
            grouped.end_to_end_correct,
            grouped.prediction_correct,
            grouped.accepted,
        )
        grouped["title_aware_end_to_end_strict_accuracy"] = (
            100 * grouped.title_aware_end_to_end_correct / grouped.planned_observations
        )
        grouped["end_to_end_normalized_accuracy"] = (
            100 * grouped.end_to_end_normalized_correct / grouped.planned_observations
        )
        grouped["title_aware_end_to_end_normalized_accuracy"] = (
            100
            * grouped.title_aware_end_to_end_normalized_correct
            / grouped.planned_observations
        )
        accuracy_rows.append(grouped)
        prompts = observations.drop_duplicates(
            ["condition", "dataset_id", "item_key", "prompt_seed"]
        )
        images = observations[~observations.route.eq("prompt")].drop_duplicates(
            ["condition", "dataset_id", "item_key", "prompt_seed", "image_seed"]
        )
        checks = [
            (
                "prompt_title_absence",
                prompts,
                "prompt_text",
                "prompt_verification_passed",
                "prompt_verification_configured",
            ),
            (
                "strict_image_text",
                images,
                "image_id",
                "strict_image_verification_passed",
                "strict_image_verification_configured",
            ),
            (
                "title_aware_image_text",
                images,
                "image_id",
                "title_aware_image_verification_passed",
                "title_aware_image_verification_configured",
            ),
        ]
        for check, units, artifact_column, decision_column, configured_column in checks:
            if configured_column is not None and not units[configured_column].any():
                continue
            decisions = units[decision_column]
            verifier_rows.append(
                {
                    "study": study,
                    "check": check,
                    "planned": len(units),
                    "materialized": int(units[artifact_column].notna().sum()),
                    "decided": int(decisions.notna().sum()),
                    "passed": int(decisions.eq(True).sum()),
                    "rejected": int(decisions.eq(False).sum()),
                    "missing_decisions": int(decisions.isna().sum()),
                }
            )
    tables["accuracy_and_coverage_percent"] = pd.concat(
        accuracy_rows, ignore_index=True
    )
    tables["verifier"] = pd.DataFrame(verifier_rows)
    supporting_metrics = [
        "end_to_end_normalized_accuracy",
        "title_aware_end_to_end_normalized_accuracy",
        "prediction_only_normalized_accuracy",
    ]
    supporting = []
    for study, scores in title_sets.items():
        table = (100 * scores.groupby("route")[supporting_metrics].mean()).reset_index()
        table.insert(0, "study", study)
        supporting.append(table)
    tables["title_weighted_normalized_metrics_percent"] = pd.concat(
        supporting, ignore_index=True
    )
    produced = pd.concat(observation_sets.values(), ignore_index=True)
    produced = produced[produced.prediction_id.notna()].assign(
        answer_likelihood=lambda f: f.confidence.astype(float)
    )
    likelihood = (
        produced.groupby(["prediction_model", "route"], dropna=False)
        .agg(
            predictions=("prediction_id", "count"),
            available=("answer_likelihood", "count"),
            median=("answer_likelihood", "median"),
            q25=("answer_likelihood", lambda s: s.quantile(0.25)),
            q75=("answer_likelihood", lambda s: s.quantile(0.75)),
        )
        .reset_index()
    )
    likelihood["availability_percent"] = (
        100 * likelihood.available / likelihood.predictions
    )
    tables["answer_likelihood"] = likelihood
    errors, timings = ([], [])
    for study, job in job_sets:
        errors.append(job.errors.assign(study=study))
        timings.append(job.timings.assign(study=study))
    errors = pd.concat(errors, ignore_index=True).reindex(
        columns=[
            "study",
            "provenance_error_key",
            "execution_origin",
            "stage",
            "error_type",
            "terminal_error",
            "recovered",
        ]
    )
    errors["origin_order"] = errors.execution_origin.map(
        {"local": 0, "imported": 1}
    ).fillna(2)
    errors = errors.sort_values("origin_order").drop_duplicates("provenance_error_key")
    tables["error_attempts"] = (
        errors.groupby(
            ["study", "stage", "error_type", "terminal_error", "recovered"],
            dropna=False,
        )
        .size()
        .rename("attempts")
        .reset_index()
    )
    timings = pd.concat(timings, ignore_index=True).reindex(
        columns=[
            "study",
            "provenance_timing_key",
            "execution_origin",
            "kind",
            "stage",
            "action",
            "duration_seconds",
        ]
    )
    timings["origin_order"] = timings.execution_origin.map(
        {"local": 0, "imported": 1}
    ).fillna(2)
    timings = timings.sort_values("origin_order").drop_duplicates(
        "provenance_timing_key"
    )
    tables["task_time_minutes"] = (
        timings[timings.kind.eq("task") & timings.action.eq("execute")]
        .groupby(["study", "stage"], dropna=False)
        .duration_seconds.sum(min_count=1)
        .div(60)
        .rename("minutes")
        .reset_index()
    )
    return tables


def overall_domain_means(frame, design):
    conditions = frame.condition.unique()
    table = effects(
        frame, {"Mean accuracy": dict.fromkeys(conditions, 1 / len(conditions))}
    )
    return table[table.domain != "all"].assign(design=design)


def load_direct_supplement(path):
    """Load a complete direct supplement, averaging its four seed observations."""
    job = load_job(path)
    observations = annotate(job.observations)
    titles = aggregate_titles(observations, condition_columns=["pg", "bb", "bi"])
    return job, observations, titles[titles.route.eq("direct")]


def load_style_jobs(paths):
    """Load four complete direct 4x4 style jobs on the shared title/seed grid."""
    jobs, observations, titles = {}, {}, {}
    entries = [f"direct_pg_{pg}_bi_{bi}" for pg in QG for bi in QG]
    for style, path in paths.items():
        job = load_job(path, entries=entries)
        frame = annotate(job.observations)
        frame = frame[frame.route.eq("direct")].assign(style=style)
        if set(frame.prompt_seed) != {1000, 1001} or set(frame.image_seed) != {
            8566257,
            2875613,
        }:
            raise ValueError(
                f"Style {style} does not use the fixed prompt/image seed grid."
            )
        if (
            not frame.prompt_verification_configured.all()
            or not frame.strict_image_verification_configured.all()
            or not frame.title_aware_image_verification_configured.all()
        ):
            raise ValueError(
                f"Style {style} is missing a required verification policy."
            )
        frame["model_pair"] = frame.pg.str.upper() + " → " + frame.bi.str.upper()
        jobs[style], observations[style] = job, frame
        titles[style] = aggregate_titles(
            frame,
            condition_columns=["style", "pg", "bi", "model_pair"],
            expected_observations=4,
        )
    return jobs, observations, titles


def style_scopes(frame):
    """Include pooled-model and pooled-domain rows with equal original weights."""
    scoped = pd.concat(
        [frame.assign(report_domain=frame.domain), frame.assign(report_domain="all")],
        ignore_index=True,
    )
    return pd.concat([scoped, scoped.assign(model_pair="all")], ignore_index=True)


def style_accuracy(title_scores):
    """Strict/normalized E2E percentages and whole-title percentile intervals."""
    rows = []
    for (style, model_pair, domain), frame in style_scopes(title_scores).groupby(
        ["style", "model_pair", "report_domain"],
        sort=False,
    ):
        conditions = frame.condition.unique()
        for metric, (label, method, _, _) in STYLE_METRICS.items():
            if frame[metric].isna().all():
                continue
            result = paired_stratified_bootstrap(
                frame,
                condition_weights=dict.fromkeys(conditions, 1 / len(conditions)),
                metric=metric,
            )
            rows.append(
                {
                    "style": style,
                    "model_pair": model_pair,
                    "domain": domain,
                    "metric": label,
                    "method": method,
                    "titles": result["titles"],
                    "planned_observations": int(frame.observations.sum()),
                    "correct": round((frame[metric] * frame.observations).sum()),
                    "accuracy_percent": 100 * result["effect"],
                    "ci95_low": 100 * result["ci95_low"],
                    "ci95_high": 100 * result["ci95_high"],
                }
            )
    return pd.DataFrame(rows)


def prompt_verifications(observations):
    """Return one persisted prompt-verification decision per generated prompt."""
    identity = ["style", "dataset_id", "item_key", "prompt_seed"]
    materialized = observations[observations.prompt_id.notna()]
    origin_keys = ["style", "origin_prompt_run_id", "origin_prompt_id"]
    compared = [
        "dataset_id",
        "domain",
        "item_key",
        "prompt_seed",
        "prompt_text",
        "prompt_verification_passed",
        "prompt_verification_method",
    ]
    if (
        materialized.groupby(origin_keys, dropna=False)[compared]
        .nunique(dropna=False)
        .gt(1)
        .any(axis=None)
    ):
        raise ValueError("Inherited copies disagree about a shared prompt/check.")
    prompts = pd.concat(
        [
            materialized.drop_duplicates(origin_keys),
            observations[observations.prompt_id.isna()].drop_duplicates(
                [*identity, "prompt_model"]
            ),
        ],
        ignore_index=True,
    )
    return prompts[
        [
            "style",
            "condition",
            "dataset_id",
            "item_key",
            "domain",
            "expected_title",
            "prompt_seed",
            "prompt_model",
            "origin_prompt_run_id",
            "origin_prompt_id",
            "prompt_text",
            "prompt_verification_passed",
            "prompt_verification_reason",
            "prompt_verification_method",
        ]
    ]


def candidate_roster(path):
    """Read the persisted full-pool roster, including candidates without ratings."""
    directory = Path(path).expanduser().resolve()
    runs = read_job_entries(directory / "job_state.sqlite", directory)
    config = load_effective_config(runs[0].run_directory / EFFECTIVE_CONFIG_FILENAME)
    return pd.DataFrame(
        [
            {
                "dataset_id": config.dataset.dataset_id,
                "domain": item.domain,
                "item_key": item.id,
                "title": item.title,
            }
            for item in config.dataset.items
        ]
    )


def candidate_tables(roster, raw_ratings):
    """Keep all candidates; a mean requires four valid integer ratings, with no imputation."""
    keys = ["dataset_id", "domain", "item_key"]
    ratings = raw_ratings.reindex(
        columns=["entry_name", *keys, "title", "score"]
    ).copy()
    ratings["model"] = ratings.entry_name.astype("string").str.removeprefix("rating_")
    numeric = pd.to_numeric(ratings.score, errors="coerce")
    ratings["valid"] = numeric.between(0, 100) & numeric.mod(1).eq(0)
    ratings["score"] = numeric.where(ratings.valid)
    scores = ratings.pivot(index=keys, columns="model", values="score").reindex(
        index=pd.MultiIndex.from_frame(roster[keys]),
        columns=QG,
    )
    scores["valid_model_ratings"] = scores.notna().sum(axis=1)
    scores["mean_score"] = scores[QG].mean(axis=1, skipna=False)
    scores = roster.merge(scores, on=keys, validate="one_to_one")
    counts = (
        scores.groupby("domain")
        .mean_score.agg(
            candidates="size",
            complete_four_model_means="count",
        )
        .reindex(DOMAINS)
    )
    counts["missing_means"] = counts.candidates - counts.complete_four_model_means
    model_counts = (
        ratings.groupby(["domain", "model"])
        .valid.agg(
            recorded_ratings="size",
            valid_ratings="sum",
        )
        .reindex(
            pd.MultiIndex.from_product([DOMAINS, QG], names=["domain", "model"]),
            fill_value=0,
        )
    )
    model_counts["planned_ratings"] = model_counts.index.get_level_values("domain").map(
        counts.candidates
    )
    model_counts["missing_ratings"] = (
        model_counts.planned_ratings - model_counts.recorded_ratings
    )
    model_counts["invalid_ratings"] = (
        model_counts.recorded_ratings - model_counts.valid_ratings
    )
    return scores, counts, model_counts


def histogram_counts(scores, bins):
    """Export the exact displayed bins; only the final bin includes its right edge."""
    rows = []
    for domain in DOMAINS:
        counts, _ = np.histogram(
            scores.loc[scores.domain.eq(domain), "mean_score"].dropna(), bins=bins
        )
        rows.extend(
            {
                "domain": domain,
                "bin_left": int(left),
                "bin_right": int(right),
                "right_inclusive": bool(right == bins[-1]),
                "titles": int(count),
            }
            for left, right, count in zip(bins[:-1], bins[1:], counts, strict=True)
        )
    return pd.DataFrame(rows)


def export_tables(tables, output_dir):
    """Write supporting data quietly; missing estimates are explicitly unavailable."""
    for name, table in tables.items():
        table.to_csv(Path(output_dir) / f"{name}.csv", index=False, na_rep="n/a")


def write_manifest(notebook, job_paths, output_dir, *, analysis):
    """Record exact input/configuration and analysis code hashes, not a compatibility check."""
    notebook, output_dir = Path(notebook).resolve(), Path(output_dir).resolve()

    def digest(path):
        return hashlib.sha256(Path(path).read_bytes()).hexdigest()

    sources = []
    for label, path in job_paths.items():
        directory = Path(path).expanduser().resolve()
        record = read_job_record(directory / "job_state.sqlite")
        snapshot = load_job_snapshot(directory / JOB_SNAPSHOT_FILENAME)
        runs = read_job_entries(directory / "job_state.sqlite", directory)
        inputs = [directory / JOB_SNAPSHOT_FILENAME, directory / "job_state.sqlite"]
        for run in runs:
            inputs.extend(
                [
                    run.run_directory / EFFECTIVE_CONFIG_FILENAME,
                    run.run_directory / "pipeline_state.sqlite",
                ]
            )
        sources.append(
            {
                "label": label,
                "directory": str(directory),
                "job_id": record.job_id,
                "job_name": record.name,
                "status": record.status,
                "entries": {
                    entry.name: str(run.run_directory)
                    for entry, run in zip(snapshot.entries, runs, strict=True)
                },
                "sha256": {str(p): digest(p) for p in inputs},
            }
        )
    code_files = [
        notebook,
        Path(evaluation.__file__),
        *sorted(Path(__file__).parent.glob("*.py")),
    ]
    manifest = {
        "analysis": analysis,
        "created_at_utc": datetime.now(UTC).isoformat(),
        "python": platform.python_version(),
        "packages": {
            name: version(name)
            for name in [
                "semantic-roundtrip",
                "pandas",
                "numpy",
                "matplotlib",
                "seaborn",
            ]
        },
        "methods": {
            "strict_title_match": EXACT_MATCH_METHOD,
            "normalized_title_match": NORMALIZED_EXACT_METHOD,
            "prompt_verification": PROMPT_TITLE_MATCH_METHOD,
            "strict_image_verification": STRICT_IMAGE_VERIFICATION_METHOD,
            "title_aware_image_verification": (TITLE_AWARE_IMAGE_VERIFICATION_METHOD),
        },
        "analysis_sha256": {str(p): digest(p) for p in code_files},
        "sources": sources,
        "exports_sha256": {
            p.name: digest(p)
            for p in sorted(output_dir.iterdir())
            if p.suffix in {".csv", ".png", ".pdf"}
        },
    }
    (output_dir / "manifest.json").write_text(
        json.dumps(manifest, indent=2, ensure_ascii=False) + "\n", encoding="utf-8"
    )
