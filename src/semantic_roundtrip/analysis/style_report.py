"""Single-source style reporting and a hash-checked portable summary contract."""

import hashlib
import json
from pathlib import Path
from shutil import copy2

import pandas as pd

from semantic_roundtrip.analysis.reporting import QG, STYLE_METRICS
from semantic_roundtrip.analysis.statistics import paired_stratified_bootstrap
from semantic_roundtrip.evaluation import (
    EXACT_MATCH_METHOD,
    NORMALIZED_EXACT_METHOD,
    PROMPT_TITLE_MATCH_METHOD,
    STRICT_IMAGE_VERIFICATION_METHOD,
    TITLE_AWARE_IMAGE_VERIFICATION_METHOD,
)
from semantic_roundtrip.persistence.job.database import read_job_record
from semantic_roundtrip.persistence.job.schema import job_database_path

STYLE_REPORT_VERSION = 2
STYLE_PRIMARY_METRIC = "title_aware_end_to_end_strict_accuracy"
STYLE_NAMES = {"Unrestricted", "Photorealistic", "Sketch", "Comic"}
STYLE_METHODS = {
    "strict_title_match": EXACT_MATCH_METHOD,
    "normalized_title_match": NORMALIZED_EXACT_METHOD,
    "prompt_verification": PROMPT_TITLE_MATCH_METHOD,
    "strict_image_verification": STRICT_IMAGE_VERIFICATION_METHOD,
    "title_aware_image_verification": TITLE_AWARE_IMAGE_VERIFICATION_METHOD,
}
STYLE_BOOTSTRAP = {
    "unit": "paired whole title",
    "strata": ["domain"],
    "repetitions": 10000,
    "seed": 20260829,
    "pointwise": True,
}
STYLE_ANALYSIS_METHODS = {
    "accuracy_intervals": "paired_title_mean_domain_stratified_percentile_v1",
    "prompt_counts": "logical_prompt_origin_failed_pg_model_grid_v1",
    "centrality": "equal_domain_title_model_absolute_paired_distance_v1",
    "centrality_ties": "exact_full_grid_quarter_score_sum_v1",
}
STYLE_PRIMARY_DEFINITION = (
    "passed prompt verification + passed title-aware image verification + "
    "Strict Exact Match / all planned image observations"
)
SUMMARY_STEMS = ["style_accuracy_overall_domains"]
SUMMARY_ARTIFACTS = (
    "style_accuracy.csv",
    "style_centrality.csv",
    "style_prompt_verifications.csv",
    "accuracy_and_coverage_percent.csv",
    "verifier.csv",
    "manifest.json",
    *(f"{stem}.{suffix}" for stem in SUMMARY_STEMS for suffix in ("png", "pdf")),
    *(f"style_effects_{name}.csv" for name in ("photorealistic", "sketch", "comic")),
    *(
        f"sensitivity_style_effects_{name}.csv"
        for name in ("photorealistic", "sketch", "comic")
    ),
)


def _digest(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def _validate_analysis(analysis):
    if (
        analysis.get("purpose") != "complete_style_comparison"
        or analysis.get("bootstrap") != STYLE_BOOTSTRAP
        or analysis.get("style_analysis_methods") != STYLE_ANALYSIS_METHODS
        or analysis.get("primary_metric") != STYLE_PRIMARY_METRIC
        or analysis.get("primary_definition") != STYLE_PRIMARY_DEFINITION
        or analysis.get("seed_observations_per_title") != 4
    ):
        raise ValueError(
            "Incompatible style analysis: pairing, strata, methods or primary endpoint differ."
        )


def validate_style_grid(title_scores):
    """Require ninety shared titles and sixteen cells under every style."""
    keys = ["dataset_id", "domain", "item_key", "pg", "bi"]
    if set(title_scores["style"]) != STYLE_NAMES:
        raise ValueError("Style report requires all four styles.")
    reference = None
    for style, frame in title_scores.groupby("style", sort=True):
        if (
            len(frame) != 1440
            or frame.duplicated(keys).any()
            or not frame.observations.eq(4).all()
        ):
            raise ValueError(f"Incomplete/duplicated title-by-model grid for {style}.")
        if set(zip(frame.pg, frame.bi, strict=True)) != {
            (pg, bi) for pg in QG for bi in QG
        }:
            raise ValueError(f"Incomplete model matrix for {style}.")
        roster = frame[
            ["dataset_id", "domain", "item_key", "expected_title"]
        ].drop_duplicates()
        if set(roster.dataset_id) != {"final_titles_v1"} or roster.groupby(
            "domain"
        ).size().to_dict() != {"songs": 30, "movies": 30, "bands": 30}:
            raise ValueError(f"Incorrect final title roster for {style}.")
        current = (
            frame[[*keys, "expected_title"]].sort_values(keys).reset_index(drop=True)
        )
        if reference is not None and not current.equals(reference):
            raise ValueError("Style jobs do not share the same title/model grid.")
        reference = current


def style_centrality(title_scores):
    """Descriptive mean absolute paired distance; never select a style automatically."""
    validate_style_grid(title_scores)
    rows = []
    for domain, frame in [
        ("all", title_scores),
        *title_scores.groupby("domain", sort=True),
    ]:
        for metric in STYLE_METRICS:
            paired = frame.pivot(
                index=["dataset_id", "domain", "item_key", "pg", "bi"],
                columns="style",
                values=metric,
            )
            if paired.isna().any(axis=None):
                raise ValueError("Centrality requires all paired style scores.")
            for style in sorted(STYLE_NAMES):
                distance = paired.drop(columns=style).sub(paired[style], axis=0).abs()
                rows.append(
                    {
                        "style": style,
                        "domain": domain,
                        "metric": metric,
                        "centrality_pp": float(
                            100 * distance.to_numpy(dtype=float).sum() / distance.size
                        ),
                        "paired_title_model_cells": len(paired),
                        "centrality_method": STYLE_ANALYSIS_METHODS["centrality"],
                        "tie_method": STYLE_ANALYSIS_METHODS["centrality_ties"],
                        "interpretation": "descriptive centrality, not an automatic style decision",
                    }
                )
    result = pd.DataFrame(rows)
    result["centrality_rank"] = (
        result.groupby(["domain", "metric"])
        .centrality_pp.rank(method="min")
        .astype(int)
    )
    result["tie_count"] = result.groupby(["domain", "metric", "centrality_pp"])[
        "style"
    ].transform("size")
    result["tied"] = result.tie_count.gt(1)
    return result


def qwen_pg_style_followup(title_scores):
    """Exploratory Q38-minus-Q25 difference in each style effect, not adherence.

    Each title/style/PG value equally averages the four TG assignments. The
    three style-minus-Unrestricted interactions form one comparison family.
    The original four seed scores and every planned title remain included.
    """
    validate_style_grid(title_scores)
    metric = STYLE_PRIMARY_METRIC
    selected = title_scores[title_scores.pg.isin(["q25", "q38"])]
    if selected[metric].isna().any() or not selected[metric].between(0, 1).all():
        raise ValueError("The style follow-up requires complete primary title scores.")
    identity = ["dataset_id", "domain", "item_key", "style", "pg"]
    marginal = selected.groupby(identity, as_index=False)[metric].mean()
    marginal["condition"] = marginal["style"] + "/" + marginal["pg"]
    deltas, interactions = [], []
    for style in ["Photorealistic", "Sketch", "Comic"]:
        for pg in ["q25", "q38"]:
            result = paired_stratified_bootstrap(
                marginal,
                condition_weights={f"{style}/{pg}": 1, f"Unrestricted/{pg}": -1},
                metric=metric,
            )
            deltas.append({"style": style, "pg": pg, "metric": metric, **result})
        result = paired_stratified_bootstrap(
            marginal,
            condition_weights={
                f"{style}/q38": 1,
                "Unrestricted/q38": -1,
                f"{style}/q25": -1,
                "Unrestricted/q25": 1,
            },
            metric=metric,
            family_size=3,
        )
        interactions.append(
            {"style": style, "comparison": "Q38 - Q25 PG style effect", "metric": metric, **result}
        )
    return {
        "exploratory_qwen_pg_style_deltas": pd.DataFrame(deltas),
        "exploratory_qwen_pg_style_interactions": pd.DataFrame(interactions),
    }


def export_style_summary(output_dir):
    """Freeze completed exports after write_manifest; originals and methods stay auditable."""
    output_dir = Path(output_dir).expanduser().resolve()
    manifest_path = output_dir / "manifest.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    _validate_analysis(manifest["analysis"])
    if (
        manifest["methods"] != STYLE_METHODS
        or manifest["analysis"].get("purpose") != "complete_style_comparison"
    ):
        raise ValueError("Cannot freeze an incompatible style report.")
    if {row["label"] for row in manifest["sources"]} != STYLE_NAMES or any(
        row["status"] != "completed" for row in manifest["sources"]
    ):
        raise ValueError("Style export requires four completed source jobs.")
    hashes = {}
    for name in SUMMARY_ARTIFACTS:
        path = output_dir / name
        if not path.is_file():
            raise ValueError(f"Style summary artifact is missing: {name}")
        hashes[name] = _digest(path)
        if (
            path.suffix in {".csv", ".png", ".pdf"}
            and manifest["exports_sha256"].get(name) != hashes[name]
        ):
            raise ValueError(
                f"Style export changed after its provenance manifest: {name}"
            )
    contract = {
        "schema_version": STYLE_REPORT_VERSION,
        "methods": STYLE_METHODS,
        "primary_metric": STYLE_PRIMARY_METRIC,
        "primary_definition": STYLE_PRIMARY_DEFINITION,
        "bootstrap": STYLE_BOOTSTRAP,
        "analysis_methods": STYLE_ANALYSIS_METHODS,
        "sources": [
            {"style": row["label"], "job_id": row["job_id"]}
            for row in manifest["sources"]
        ],
        "artifacts_sha256": hashes,
        "selection": {
            "status": "recommendation_requires_supervisor_confirmation",
            "recommended_reference": "Unrestricted",
            "centrality": "descriptive_only",
        },
    }
    (output_dir / "style_summary.json").write_text(
        json.dumps(contract, indent=2, ensure_ascii=False) + "\n", encoding="utf-8"
    )


def load_style_summary(report_dir, direct_job_path, output_dir):
    """Validate a frozen style report and import only its compact summary/diagnostics."""
    report_dir = Path(report_dir).expanduser().resolve()
    output_dir = Path(output_dir).expanduser().resolve()
    contract_path = report_dir / "style_summary.json"
    contract = json.loads(contract_path.read_text(encoding="utf-8"))
    if (
        contract.get("schema_version") != STYLE_REPORT_VERSION
        or contract.get("methods") != STYLE_METHODS
        or contract.get("primary_metric") != STYLE_PRIMARY_METRIC
        or contract.get("primary_definition") != STYLE_PRIMARY_DEFINITION
        or contract.get("bootstrap") != STYLE_BOOTSTRAP
        or contract.get("analysis_methods") != STYLE_ANALYSIS_METHODS
    ):
        raise ValueError("Unsupported style-summary version or evaluation methods.")
    sources = {row["style"]: row["job_id"] for row in contract["sources"]}
    if set(contract["artifacts_sha256"]) != set(SUMMARY_ARTIFACTS):
        raise ValueError("The frozen style-summary artifact set is incomplete.")
    direct = read_job_record(
        job_database_path(Path(direct_job_path).expanduser().resolve())
    )
    if (
        set(sources) != STYLE_NAMES
        or sources["Unrestricted"] != direct.job_id
        or direct.name != "final_direct_core"
    ):
        raise ValueError(
            "Style summary does not reference this unrestricted Direct job."
        )
    for name, digest in contract["artifacts_sha256"].items():
        if Path(name).name != name or _digest(report_dir / name) != digest:
            raise ValueError(
                f"Missing, changed or unsafe style-summary artifact: {name}"
            )
    manifest = json.loads((report_dir / "manifest.json").read_text(encoding="utf-8"))
    _validate_analysis(manifest["analysis"])
    if (
        manifest["methods"] != STYLE_METHODS
        or {row["label"]: row["job_id"] for row in manifest["sources"]} != sources
        or any(row["status"] != "completed" for row in manifest["sources"])
    ):
        raise ValueError(
            "Style manifest does not contain completed current-method evidence."
        )
    tables = {
        Path(name).stem: pd.read_csv(report_dir / name)
        for name in contract["artifacts_sha256"]
        if name.endswith(".csv")
    }
    if (
        set(tables["style_accuracy"]["style"]) != STYLE_NAMES
        or set(tables["style_centrality"]["style"]) != STYLE_NAMES
    ):
        raise ValueError("Style-summary tables do not cover all four styles.")
    imported = output_dir / "style_summary"
    imported.mkdir(parents=True, exist_ok=True)
    for name in [*contract["artifacts_sha256"], "style_summary.json"]:
        if (report_dir / name).resolve() != (imported / name).resolve():
            copy2(report_dir / name, imported / name)
    return tables, {
        "contract_sha256": _digest(contract_path),
        "contract": contract,
        "directory": str(imported),
    }


def display_style_summary(imported_directory):
    """Display the already-rendered compact panels without recalculating style analyses."""
    from IPython.display import Image, display

    for stem in SUMMARY_STEMS:
        display(Image(filename=str(Path(imported_directory) / f"{stem}.png")))
