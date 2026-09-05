"""Read current SQLite runs and jobs into four analysis tables."""

from __future__ import annotations

import json
import sqlite3
from collections.abc import Iterable
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import pandas as pd

from semantic_roundtrip.analysis.statistics import score_observations
from semantic_roundtrip.config import ResolvedAppConfig, StageName
from semantic_roundtrip.config_resolution import (
    configured_image_verification_policies,
    configured_stage_names,
    get_stage_config,
    load_effective_config,
)
from semantic_roundtrip.inheritance.dependencies import dependency_closure
from semantic_roundtrip.inheritance.source import resolve_stage_provenance
from semantic_roundtrip.job import JOB_SNAPSHOT_FILENAME, load_job_snapshot
from semantic_roundtrip.persistence.job.database import (
    read_job_entries,
    read_job_record,
)
from semantic_roundtrip.persistence.job.schema import job_database_path
from semantic_roundtrip.persistence.run.config_snapshot import EFFECTIVE_CONFIG_FILENAME
from semantic_roundtrip.persistence.run.schema import (
    connect_run_database,
    database_path_for_run,
    require_run_schema,
)


@dataclass(frozen=True, slots=True)
class AnalysisTables:
    """The four small tables used by the thesis notebook."""

    observations: pd.DataFrame
    ratings: pd.DataFrame
    errors: pd.DataFrame
    timings: pd.DataFrame


def _rows(connection: sqlite3.Connection, table: str) -> list[dict[str, Any]]:
    return [dict(row) for row in connection.execute(f"SELECT * FROM {table}")]


def _map(
    rows: list[dict[str, Any]],
    columns: tuple[str, ...],
    label: str,
) -> dict[tuple[object, ...], dict[str, Any]]:
    result: dict[tuple[object, ...], dict[str, Any]] = {}
    for row in rows:
        key = tuple(row[column] for column in columns)
        if key in result:
            raise ValueError(f"Duplicate {label} key in run database: {key}")
        result[key] = row
    return result


def _title_length_group(title: str) -> str:
    words = len(title.split())
    return "short" if words == 1 else "medium" if words <= 3 else "long"


def _local_model(config: ResolvedAppConfig, stage: StageName) -> str | None:
    stage_config = get_stage_config(config, stage)
    if stage_config is None or stage == "verification_prompt":
        return None
    backend = config.backends[stage_config.backend]
    value = (
        backend.settings.get("model_id")
        or backend.settings.get("checkpoint")
        or backend.adapter
    )
    return str(value)


def _stage_models(
    config: ResolvedAppConfig,
    runtime_rows: list[dict[str, Any]],
    run_directory: Path,
) -> dict[str, str | None]:
    stages = (
        "illustratability_rating",
        "prompt_generation",
        "image_generation",
        "verification_prompt",
        "verification_image",
        "title_guessing_direct",
        "title_guessing_from_prompt",
        "image_description",
        "title_guessing_from_description",
    )
    result: dict[str, str | None] = {}
    for stage in stages:
        model_ids = {
            str(row["model_id"])
            for row in runtime_rows
            if row["stage"] == stage and row["model_id"] is not None
        }
        if len(model_ids) > 1:
            raise ValueError(f"Stage '{stage}' contains several model IDs.")
        result[stage] = next(iter(model_ids), None) or _local_model(config, stage)
        if result[stage] is None and stage != "verification_prompt":
            provenance = resolve_stage_provenance(config, run_directory, stage)
            if provenance is not None:
                result[stage] = _local_model(provenance[0], stage)
    return result


def _available_stages(
    config: ResolvedAppConfig,
    tasks: list[dict[str, Any]],
    lineage: list[dict[str, Any]],
) -> set[str]:
    available = set(configured_stage_names(config))
    available.update(str(row["stage"]) for row in tasks)
    for row in lineage:
        available.update(dependency_closure(json.loads(row["inherited_stages"])))
    return available


def _verification_checks(
    config: ResolvedAppConfig,
    tasks: list[dict[str, Any]],
    run_directory: Path,
) -> tuple[bool, frozenset[str]]:
    prompt = config.stages.verification_prompt is not None
    image = set(configured_image_verification_policies(config))
    prompt |= (
        resolve_stage_provenance(config, run_directory, "verification_prompt")
        is not None
    )
    image_source = resolve_stage_provenance(config, run_directory, "verification_image")
    if image_source is not None:
        image.update(configured_image_verification_policies(image_source[0]))
    for row in tasks:
        if row["stage"] == "verification_prompt":
            prompt = True
        if row["stage"] != "verification_image":
            continue
        task_key = str(row["task_key"])
        for policy in ("strict", "title_aware"):
            if f":{policy}:" in task_key:
                image.add(policy)
    return prompt, frozenset(image)


def _image_path(run_directory: Path, stored_path: str) -> str:
    path = Path(stored_path)
    resolved = (path if path.is_absolute() else run_directory / path).resolve()
    if not resolved.is_file():
        raise FileNotFoundError(f"Run references a missing image: {resolved}")
    return str(resolved)


def _error_rows(
    connection: sqlite3.Connection,
    run_id: str,
) -> list[dict[str, Any]]:
    rows = connection.execute(
        """
        SELECT
            errors.*,
            COALESCE(errors.item_id, tasks.item_id) AS matched_item_id,
            COALESCE(errors.prompt_id, tasks.prompt_id) AS matched_prompt_id,
            COALESCE(errors.image_id, tasks.image_id) AS matched_image_id,
            tasks.seed,
            tasks.task_key,
            tasks.status AS task_status,
            tasks.execution_origin AS task_execution_origin
        FROM stage_errors AS errors
        LEFT JOIN stage_tasks AS tasks ON tasks.task_id = errors.task_id
        ORDER BY errors.error_id
        """
    ).fetchall()
    normalized: list[dict[str, Any]] = []
    for raw in rows:
        row = dict(raw)
        row["item_id"] = row.pop("matched_item_id")
        row["prompt_id"] = row.pop("matched_prompt_id")
        row["image_id"] = row.pop("matched_image_id")
        row["terminal_error"] = row["task_status"] == "failed"
        row["recovered"] = row["task_status"] == "completed"
        origin_run = row["origin_run_id"] or run_id
        origin_error = row["origin_error_id"] or row["error_id"]
        row["provenance_error_key"] = f"{origin_run}:{origin_error}"
        normalized.append(row)
    return normalized


def _latest_error(
    errors: list[dict[str, Any]],
    *,
    item_id: int,
    prompt_id: int | None,
    image_id: int | None,
    prompt_seed: int,
    image_seed: int | None,
    route_stage: str,
) -> dict[str, Any] | None:
    relevant = {
        "prompt_generation",
        route_stage,
    }
    if route_stage != "title_guessing_from_prompt":
        relevant.add("image_generation")
    if route_stage == "title_guessing_from_description":
        relevant.add("image_description")
    for row in reversed(errors):
        if row["stage"] not in relevant:
            continue
        if image_id is not None and row["image_id"] == image_id:
            return row
        if (
            prompt_id is not None
            and row["prompt_id"] == prompt_id
            and (row["stage"] != "image_generation" or row["seed"] == image_seed)
        ):
            return row
        if (
            row["item_id"] == item_id
            and row["stage"] == "prompt_generation"
            and row["seed"] == prompt_seed
        ):
            return row
    return None


def _timing_rows(
    tasks: list[dict[str, Any]],
    runtime: list[dict[str, Any]],
    run_id: str,
) -> list[dict[str, Any]]:
    result: list[dict[str, Any]] = []
    for row in tasks:
        origin_run = row["origin_run_id"] or run_id
        origin_id = row["origin_task_id"] or row["task_id"]
        result.append(
            {
                "kind": "task",
                "stage": row["stage"],
                "action": "execute",
                "status": row["status"],
                "started_at": row["started_at"],
                "finished_at": row["finished_at"],
                "execution_origin": row["execution_origin"],
                "model_id": None,
                "provenance_timing_key": f"task:{origin_run}:{origin_id}",
            }
        )
    for row in runtime:
        origin_run = row["origin_run_id"] or run_id
        origin_id = row["origin_runtime_event_id"] or row["runtime_event_id"]
        result.append(
            {
                "kind": "runtime",
                "stage": row["stage"],
                "action": row["action"],
                "status": row["status"],
                "started_at": row["started_at"],
                "finished_at": row["finished_at"],
                "execution_origin": row["execution_origin"],
                "model_id": row["model_id"],
                "provenance_timing_key": f"runtime:{origin_run}:{origin_id}",
            }
        )
    return result


def load_run(path: str | Path) -> AnalysisTables:
    """Load one completed current-schema run without modifying it."""
    run_directory = Path(path).expanduser().resolve()
    config = load_effective_config(run_directory / EFFECTIVE_CONFIG_FILENAME)
    connection = connect_run_database(
        database_path_for_run(run_directory), read_only=True
    )
    try:
        require_run_schema(connection)
        metadata_row = connection.execute("SELECT * FROM run_metadata").fetchone()
        if metadata_row is None:
            raise ValueError("Run metadata is missing.")
        metadata = dict(metadata_row)
        if metadata["status"] != "completed":
            raise ValueError(
                f"Analysis requires a completed run, got '{metadata['status']}'."
            )
        if metadata["name"] != config.run.name:
            raise ValueError("Run database and effective configuration names differ.")

        table_names = [
            "dataset_items",
            "illustratability_ratings",
            "prompts",
            "images",
            "image_descriptions",
            "predictions",
            "prompt_predictions",
            "stage_tasks",
            "runtime_events",
            "run_lineage",
        ]
        table_names.extend(["prompt_verifications", "image_verifications"])
        tables = {name: _rows(connection, name) for name in table_names}
        errors = _error_rows(connection, metadata["run_id"])
    finally:
        connection.close()

    unfinished = [
        row for row in tables["stage_tasks"] if row["status"] in {"pending", "running"}
    ]
    if unfinished:
        raise ValueError(f"Run contains unfinished task '{unfinished[0]['task_key']}'.")

    items = tables["dataset_items"]
    if len(items) != len(config.dataset.items):
        raise ValueError("Run dataset table is incomplete.")
    items_by_index = {int(row["item_index"]): row for row in items}
    items_by_id = {int(row["item_id"]): row for row in items}
    for index, configured in enumerate(config.dataset.items):
        row = items_by_index.get(index)
        if row is None or (row["item_key"], row["domain"], row["title"]) != (
            configured.id,
            configured.domain,
            configured.title,
        ):
            raise ValueError(f"Dataset item {index} differs from the run snapshot.")

    models = _stage_models(config, tables["runtime_events"], run_directory)
    base = {
        "condition": metadata["name"],
        "run_id": metadata["run_id"],
        "run_name": metadata["name"],
        "run_directory": str(run_directory),
        "dataset_id": config.dataset.dataset_id,
    }

    ratings: list[dict[str, Any]] = []
    for row in tables["illustratability_ratings"]:
        item = items_by_id[int(row["item_id"])]
        ratings.append(
            {
                **base,
                "rating_model": models["illustratability_rating"],
                "item_key": item["item_key"],
                "item_index": int(item["item_index"]),
                "domain": item["domain"],
                "title": item["title"],
                "title_length_group": _title_length_group(item["title"]),
                "score": int(row["score"]),
                "backend_request_id": row["backend_request_id"],
                "raw_response": row["raw_response"],
            }
        )

    available = _available_stages(config, tables["stage_tasks"], tables["run_lineage"])
    prompt_verification_configured, image_policies = _verification_checks(
        config,
        tables["stage_tasks"],
        run_directory,
    )
    routes = []
    if "title_guessing_direct" in available:
        routes.append(("direct", "image", "title_guessing_direct"))
    if "title_guessing_from_description" in available:
        routes.append(("description", "description", "title_guessing_from_description"))

    prompts = _map(tables["prompts"], ("item_id", "prompt_index"), "prompt")
    images = _map(tables["images"], ("prompt_id", "seed"), "image")
    prompt_verifications = _map(
        tables["prompt_verifications"],
        ("prompt_id", "policy"),
        "prompt verification",
    )
    image_verifications = _map(
        tables["image_verifications"],
        ("image_id", "policy"),
        "image verification",
    )
    descriptions = _map(tables["image_descriptions"], ("image_id",), "description")
    predictions = _map(tables["predictions"], ("image_id", "input_kind"), "prediction")
    prompt_predictions = _map(
        tables["prompt_predictions"], ("prompt_id",), "prompt prediction"
    )

    observations: list[dict[str, Any]] = []
    for item_index, configured in enumerate(config.dataset.items):
        item = items_by_index[item_index]
        item_id = int(item["item_id"])
        for prompt_index, prompt_seed in enumerate(config.experiment.prompt_seeds):
            prompt = prompts.get((item_id, prompt_index))
            if prompt is not None and int(prompt["sampling_seed"]) != prompt_seed:
                raise ValueError("Stored prompt seed differs from the run snapshot.")
            prompt_id = None if prompt is None else int(prompt["prompt_id"])
            prompt_verification = (
                None
                if prompt_id is None
                else prompt_verifications.get((prompt_id, "reference_title_absent"))
            )
            prompt_origin_run = (
                None
                if prompt is None
                else prompt["origin_run_id"] or metadata["run_id"]
            )
            prompt_origin_id = (
                None if prompt is None else prompt["origin_prompt_id"] or prompt_id
            )
            if "title_guessing_from_prompt" in available:
                prediction = prompt_predictions.get((prompt_id,))
                error = _latest_error(
                    errors,
                    item_id=item_id,
                    prompt_id=prompt_id,
                    image_id=None,
                    prompt_seed=prompt_seed,
                    image_seed=None,
                    route_stage="title_guessing_from_prompt",
                )
                observations.append(
                    {
                        **base,
                        "item_key": configured.id,
                        "item_index": item_index,
                        "domain": configured.domain,
                        "expected_title": configured.title,
                        "title_length_group": _title_length_group(configured.title),
                        "prompt_index": prompt_index,
                        "prompt_seed": prompt_seed,
                        "prompt_id": prompt_id,
                        "prompt_text": None if prompt is None else prompt["text"],
                        "origin_prompt_run_id": prompt_origin_run,
                        "origin_prompt_id": prompt_origin_id,
                        "image_seed": None,
                        "image_id": None,
                        "image_path": None,
                        "origin_image_run_id": None,
                        "origin_image_id": None,
                        "route": "prompt",
                        "prompt_model": models["prompt_generation"],
                        "image_model": None,
                        "verifier_model": None,
                        "description_model": None,
                        "prediction_model": models["title_guessing_from_prompt"],
                        "prompt_verification_configured": prompt_verification_configured,
                        "prompt_verification_passed": (
                            None
                            if prompt_verification is None
                            else bool(prompt_verification["passed"])
                        ),
                        "prompt_verification_reason": (
                            None
                            if prompt_verification is None
                            else prompt_verification["reason"]
                        ),
                        "prompt_verification_method": (
                            None
                            if prompt_verification is None
                            else prompt_verification["method"]
                        ),
                        **{
                            f"{policy}_image_verification_{field}": (
                                False if field == "configured" else None
                            )
                            for policy in ("strict", "title_aware")
                            for field in ("configured", "passed", "reason", "method")
                        },
                        "image_description": None,
                        "prediction_id": (
                            None
                            if prediction is None
                            else prediction["prompt_prediction_id"]
                        ),
                        "origin_prediction_run_id": (
                            None
                            if prediction is None
                            else prediction["origin_run_id"] or metadata["run_id"]
                        ),
                        "origin_prediction_id": (
                            None
                            if prediction is None
                            else prediction["origin_prompt_prediction_id"]
                            or prediction["prompt_prediction_id"]
                        ),
                        "prediction_execution_origin": (
                            None
                            if prediction is None
                            else "imported"
                            if prediction["origin_run_id"] is not None
                            else "local"
                        ),
                        "predicted_title": None
                        if prediction is None
                        else prediction["title"],
                        "confidence": None
                        if prediction is None
                        else prediction["confidence"],
                        "confidence_type": None
                        if prediction is None
                        else prediction["confidence_type"],
                        "prediction_raw_response": None
                        if prediction is None
                        else prediction["raw_response"],
                        "prediction_status": (
                            "completed"
                            if prediction is not None
                            else "failed"
                            if error is not None
                            else "missing"
                        ),
                        "error_stage": None if error is None else error["stage"],
                        "error_type": None if error is None else error["error_type"],
                        "error_message": None if error is None else error["message"],
                    }
                )
            for image_seed in config.experiment.image_seeds:
                image = (
                    None if prompt_id is None else images.get((prompt_id, image_seed))
                )
                image_id = None if image is None else int(image["image_id"])
                strict_verification = (
                    None
                    if image_id is None
                    else image_verifications.get((image_id, "strict"))
                )
                title_aware_verification = (
                    None
                    if image_id is None
                    else image_verifications.get((image_id, "title_aware"))
                )
                description = (
                    None if image_id is None else descriptions.get((image_id,))
                )
                for route, input_kind, route_stage in routes:
                    prediction = (
                        None
                        if image_id is None
                        else predictions.get((image_id, input_kind))
                    )
                    error = _latest_error(
                        errors,
                        item_id=item_id,
                        prompt_id=prompt_id,
                        image_id=image_id,
                        prompt_seed=prompt_seed,
                        image_seed=image_seed,
                        route_stage=route_stage,
                    )
                    observations.append(
                        {
                            **base,
                            "item_key": configured.id,
                            "item_index": item_index,
                            "domain": configured.domain,
                            "expected_title": configured.title,
                            "title_length_group": _title_length_group(configured.title),
                            "prompt_index": prompt_index,
                            "prompt_seed": prompt_seed,
                            "prompt_id": prompt_id,
                            "prompt_text": None if prompt is None else prompt["text"],
                            "origin_prompt_run_id": prompt_origin_run,
                            "origin_prompt_id": prompt_origin_id,
                            "image_seed": image_seed,
                            "image_id": image_id,
                            "origin_image_run_id": (
                                None
                                if image is None
                                else image["origin_run_id"] or metadata["run_id"]
                            ),
                            "origin_image_id": (
                                None
                                if image is None
                                else image["origin_image_id"] or image_id
                            ),
                            "image_path": (
                                None
                                if image is None
                                else _image_path(run_directory, image["path"])
                            ),
                            "route": route,
                            "prompt_model": models["prompt_generation"],
                            "image_model": models["image_generation"],
                            "verifier_model": models["verification_image"],
                            "description_model": models["image_description"],
                            "prediction_model": models[route_stage],
                            "prompt_verification_configured": (
                                prompt_verification_configured
                            ),
                            "prompt_verification_passed": (
                                None
                                if prompt_verification is None
                                else bool(prompt_verification["passed"])
                            ),
                            "prompt_verification_reason": (
                                None
                                if prompt_verification is None
                                else prompt_verification["reason"]
                            ),
                            "prompt_verification_method": (
                                None
                                if prompt_verification is None
                                else prompt_verification["method"]
                            ),
                            "strict_image_verification_passed": (
                                None
                                if strict_verification is None
                                else bool(strict_verification["passed"])
                            ),
                            "strict_image_verification_configured": (
                                "strict" in image_policies
                            ),
                            "strict_image_verification_reason": (
                                None
                                if strict_verification is None
                                else strict_verification["reason"]
                            ),
                            "strict_image_verification_method": (
                                None
                                if strict_verification is None
                                else strict_verification["method"]
                            ),
                            "title_aware_image_verification_configured": (
                                "title_aware" in image_policies
                            ),
                            "title_aware_image_verification_passed": (
                                None
                                if title_aware_verification is None
                                else bool(title_aware_verification["passed"])
                            ),
                            "title_aware_image_verification_reason": (
                                None
                                if title_aware_verification is None
                                else title_aware_verification["reason"]
                            ),
                            "title_aware_image_verification_method": (
                                None
                                if title_aware_verification is None
                                else title_aware_verification["method"]
                            ),
                            "image_description": (
                                None if description is None else description["text"]
                            ),
                            "prediction_id": (
                                None
                                if prediction is None
                                else prediction["prediction_id"]
                            ),
                            "predicted_title": (
                                None if prediction is None else prediction["title"]
                            ),
                            "origin_prediction_run_id": (
                                None
                                if prediction is None
                                else prediction["origin_run_id"] or metadata["run_id"]
                            ),
                            "origin_prediction_id": (
                                None
                                if prediction is None
                                else prediction["origin_prediction_id"]
                                or prediction["prediction_id"]
                            ),
                            "prediction_execution_origin": (
                                None
                                if prediction is None
                                else "imported"
                                if prediction["origin_run_id"] is not None
                                else "local"
                            ),
                            "confidence": (
                                None if prediction is None else prediction["confidence"]
                            ),
                            "confidence_type": (
                                None
                                if prediction is None
                                else prediction["confidence_type"]
                            ),
                            "prediction_raw_response": (
                                None
                                if prediction is None
                                else prediction["raw_response"]
                            ),
                            "prediction_status": (
                                "completed"
                                if prediction is not None
                                else "failed"
                                if error is not None
                                else "missing"
                            ),
                            "error_stage": None if error is None else error["stage"],
                            "error_type": (
                                None if error is None else error["error_type"]
                            ),
                            "error_message": None
                            if error is None
                            else error["message"],
                        }
                    )

    for row in errors:
        row.update(base)
    timings = _timing_rows(
        tables["stage_tasks"], tables["runtime_events"], metadata["run_id"]
    )
    for row in timings:
        row.update(base)

    timing_frame = pd.DataFrame.from_records(timings)
    if not timing_frame.empty:
        started = pd.to_datetime(timing_frame["started_at"], utc=True)
        finished = pd.to_datetime(timing_frame["finished_at"], utc=True)
        timing_frame["duration_seconds"] = (finished - started).dt.total_seconds()
        timing_frame["unique_provenance"] = ~timing_frame[
            "provenance_timing_key"
        ].duplicated()

    return AnalysisTables(
        observations=score_observations(pd.DataFrame.from_records(observations)),
        ratings=pd.DataFrame.from_records(ratings),
        errors=pd.DataFrame.from_records(errors),
        timings=timing_frame,
    )


def _with_metadata(frame: pd.DataFrame, values: dict[str, object]) -> pd.DataFrame:
    result = frame.copy()
    for name, value in values.items():
        result[name] = value
    return result


def _concat(frames: list[pd.DataFrame]) -> pd.DataFrame:
    nonempty = [frame for frame in frames if not frame.empty]
    return pd.concat(nonempty, ignore_index=True) if nonempty else pd.DataFrame()


def load_job(
    path: str | Path,
    entries: Iterable[str | int] | None = None,
) -> AnalysisTables:
    """Load explicitly selected entries from one persisted sequential job."""
    job_directory = Path(path).expanduser().resolve()
    record = read_job_record(job_database_path(job_directory))
    snapshot = load_job_snapshot(job_directory / JOB_SNAPSHOT_FILENAME)
    persisted = read_job_entries(job_database_path(job_directory), job_directory)
    if len(snapshot.entries) != len(persisted):
        raise ValueError("Job snapshot and database entry counts differ.")
    by_name = {entry.name: entry for entry in snapshot.entries}
    if len(by_name) != len(snapshot.entries):
        raise ValueError("Job snapshot contains duplicate entry names.")

    requested = None if entries is None else set(entries)
    selected = []
    for configured, stored in zip(snapshot.entries, persisted, strict=True):
        if requested is not None and (
            configured.name not in requested and configured.index not in requested
        ):
            continue
        selected.append((configured, stored))
    if requested is not None and len(selected) != len(requested):
        found = {entry.name for entry, _ in selected} | {
            entry.index for entry, _ in selected
        }
        raise ValueError(f"Unknown job entries: {sorted(requested - found, key=str)}")

    grouped: dict[str, list[pd.DataFrame]] = {
        "observations": [],
        "ratings": [],
        "errors": [],
        "timings": [],
    }
    for configured, stored in selected:
        tables = load_run(stored.run_directory)
        metadata = {
            "job_id": record.job_id,
            "job_name": record.name,
            "job_directory": str(job_directory),
            "entry_index": configured.index,
            "entry_name": configured.name,
            "condition": configured.name,
        }
        for name, frames in grouped.items():
            frames.append(_with_metadata(getattr(tables, name), metadata))

    timing_frame = _concat(grouped["timings"])
    if not timing_frame.empty:
        timing_frame["unique_provenance"] = ~timing_frame[
            "provenance_timing_key"
        ].duplicated()
    return AnalysisTables(
        observations=_concat(grouped["observations"]),
        ratings=_concat(grouped["ratings"]),
        errors=_concat(grouped["errors"]),
        timings=timing_frame,
    )
