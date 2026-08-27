"""Read selected schema-v9 SQLite runs into analysis-ready DataFrames."""

from __future__ import annotations

import json
import sqlite3
from collections.abc import Iterable
from pathlib import Path
from typing import Any

import pandas as pd

from semantic_roundtrip.analysis.config import LoadedStudy, StudyCondition, load_study
from semantic_roundtrip.analysis.models import StudyFrames
from semantic_roundtrip.config import ResolvedAppConfig, StageName
from semantic_roundtrip.config_resolution import (
    configured_stage_names,
    get_stage_config,
    load_effective_config,
)
from semantic_roundtrip.evaluation import (
    title_exact_match,
    title_normalized_exact_match,
)
from semantic_roundtrip.inheritance.dependencies import dependency_closure
from semantic_roundtrip.persistence.run.config_snapshot import EFFECTIVE_CONFIG_FILENAME
from semantic_roundtrip.persistence.run.schema import (
    connect_run_database,
    database_path_for_run,
    require_run_schema,
)


def _dict_rows(
    connection: sqlite3.Connection,
    query: str,
    parameters: Iterable[object] = (),
) -> list[dict[str, Any]]:
    return [
        dict(row) for row in connection.execute(query, tuple(parameters)).fetchall()
    ]


def _unique_map(
    rows: list[dict[str, Any]],
    columns: tuple[str, ...],
    label: str,
) -> dict[tuple[object, ...], dict[str, Any]]:
    result: dict[tuple[object, ...], dict[str, Any]] = {}
    for row in rows:
        key = tuple(row[column] for column in columns)
        if key in result:
            raise ValueError(f"Duplicate {label} key in persisted run: {key}")
        result[key] = row
    return result


def _title_length_group(title: str) -> str:
    words = len(title.split())
    if words <= 1:
        return "short"
    if words <= 3:
        return "medium"
    return "long"


def _local_model(config: ResolvedAppConfig, stage: StageName) -> str | None:
    stage_config = get_stage_config(config, stage)
    if stage_config is None:
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
) -> dict[StageName, str | None]:
    result: dict[StageName, str | None] = {}
    stage_names: tuple[StageName, ...] = (
        "prompt_generation",
        "image_generation",
        "verification",
        "title_guessing_direct",
        "image_description",
        "title_guessing_from_description",
    )
    for stage in stage_names:
        values = {
            str(row["model_id"])
            for row in runtime_rows
            if row["stage"] == stage and row["model_id"] is not None
        }
        if len(values) > 1:
            raise ValueError(
                f"Run contains multiple model IDs for stage '{stage}': {sorted(values)}"
            )
        result[stage] = next(iter(values), None) or _local_model(config, stage)
    return result


def _available_stages(
    config: ResolvedAppConfig,
    task_rows: list[dict[str, Any]],
    lineage_rows: list[dict[str, Any]],
) -> set[str]:
    available = set(configured_stage_names(config))
    available.update(str(row["stage"]) for row in task_rows)
    for row in lineage_rows:
        inherited = json.loads(str(row["inherited_stages"]))
        available.update(dependency_closure(inherited))
    return available


def _resolve_image_path(run_directory: Path, stored_path: str) -> Path:
    path = Path(stored_path)
    return (path if path.is_absolute() else run_directory / path).resolve()


def _latest_error(
    error_rows: list[dict[str, Any]],
    *,
    item_id: int,
    prompt_id: int | None,
    image_id: int | None,
    image_seed: int,
    route_stage: str,
) -> dict[str, Any] | None:
    relevant = {
        "prompt_generation",
        "image_generation",
        "verification",
        route_stage,
    }
    if route_stage == "title_guessing_from_description":
        relevant.add("image_description")
    for row in reversed(error_rows):
        if row["stage"] not in relevant:
            continue
        if image_id is not None and row["image_id"] == image_id:
            return row
        if (
            image_id is None
            and prompt_id is not None
            and row["prompt_id"] == prompt_id
            and row["stage"] == "image_generation"
            and row["seed"] == image_seed
        ):
            return row
        if prompt_id is None and row["item_id"] == item_id:
            return row
    return None


def _load_condition(
    condition_id: str,
    condition: StudyCondition,
    run_directory: Path,
) -> tuple[
    list[dict[str, Any]],
    dict[str, Any],
    list[dict[str, Any]],
    list[dict[str, Any]],
    list[dict[str, Any]],
]:
    config = load_effective_config(run_directory / EFFECTIVE_CONFIG_FILENAME)
    connection = connect_run_database(
        database_path_for_run(run_directory),
        read_only=True,
    )
    try:
        require_run_schema(connection)
        metadata = dict(connection.execute("SELECT * FROM run_metadata").fetchone())
        if metadata["status"] != "completed":
            raise ValueError(
                f"Condition '{condition_id}' uses run status "
                f"'{metadata['status']}'; final analysis requires completed runs."
            )
        if metadata["name"] != config.run.name:
            raise ValueError(
                f"Condition '{condition_id}' has different DB and snapshot names."
            )

        items = _dict_rows(
            connection,
            "SELECT * FROM dataset_items ORDER BY item_index",
        )
        prompts = _dict_rows(connection, "SELECT * FROM prompts ORDER BY prompt_id")
        images = _dict_rows(connection, "SELECT * FROM images ORDER BY image_id")
        verifications = _dict_rows(
            connection,
            "SELECT * FROM verifications ORDER BY verification_id",
        )
        descriptions = _dict_rows(
            connection,
            "SELECT * FROM image_descriptions ORDER BY description_id",
        )
        predictions = _dict_rows(
            connection,
            "SELECT * FROM predictions ORDER BY prediction_id",
        )
        tasks = _dict_rows(connection, "SELECT * FROM stage_tasks ORDER BY task_id")
        errors = _dict_rows(
            connection,
            """
            SELECT
                errors.*,
                COALESCE(errors.item_id, tasks.item_id) AS matched_item_id,
                COALESCE(errors.prompt_id, tasks.prompt_id) AS matched_prompt_id,
                COALESCE(errors.image_id, tasks.image_id) AS matched_image_id,
                tasks.seed AS seed
            FROM stage_errors AS errors
            LEFT JOIN stage_tasks AS tasks ON tasks.task_id = errors.task_id
            ORDER BY errors.error_id
            """,
        )
        runtimes = _dict_rows(
            connection,
            "SELECT * FROM runtime_events ORDER BY runtime_event_id",
        )
        lineage = _dict_rows(
            connection,
            "SELECT * FROM run_lineage ORDER BY depth, lineage_id",
        )
    finally:
        connection.close()

    unfinished = [row for row in tasks if row["status"] in {"pending", "running"}]
    if unfinished:
        row = unfinished[0]
        raise ValueError(
            f"Condition '{condition_id}' contains unfinished task "
            f"'{row['task_key']}' ({row['status']})."
        )

    available = _available_stages(config, tasks, lineage)
    route_stages = {
        "direct": "title_guessing_direct",
        "description": "title_guessing_from_description",
    }
    for route in condition.routes:
        if route_stages[route] not in available:
            raise ValueError(
                f"Condition '{condition_id}' declares unavailable route '{route}'."
            )

    if len(items) != len(config.dataset.items):
        raise ValueError(f"Condition '{condition_id}' has an incomplete dataset table.")
    items_by_index = {int(row["item_index"]): row for row in items}
    for index, configured in enumerate(config.dataset.items):
        row = items_by_index.get(index)
        if row is None or (
            row["item_key"],
            row["domain"],
            row["title"],
        ) != (configured.id, configured.domain, configured.title):
            raise ValueError(
                f"Condition '{condition_id}' dataset differs from its snapshot."
            )

    prompts_by_key = _unique_map(prompts, ("item_id", "prompt_index"), "prompt")
    images_by_key = _unique_map(images, ("prompt_id", "seed"), "image")
    verifications_by_image = _unique_map(
        verifications,
        ("image_id",),
        "verification",
    )
    descriptions_by_image = _unique_map(
        descriptions,
        ("image_id",),
        "description",
    )
    predictions_by_key = _unique_map(
        predictions,
        ("image_id", "input_kind"),
        "prediction",
    )
    stage_models = _stage_models(config, runtimes)

    normalized_errors: list[dict[str, Any]] = []
    for row in errors:
        normalized = dict(row)
        normalized["item_id"] = row["matched_item_id"]
        normalized["prompt_id"] = row["matched_prompt_id"]
        normalized["image_id"] = row["matched_image_id"]
        normalized["condition_id"] = condition_id
        normalized["run_id"] = metadata["run_id"]
        normalized_errors.append(normalized)

    observations: list[dict[str, Any]] = []
    verifier_rows: list[dict[str, Any]] = []
    for item_index, configured_item in enumerate(config.dataset.items):
        item = items_by_index[item_index]
        item_id = int(item["item_id"])
        for prompt_index, prompt_seed in enumerate(config.experiment.prompt_seeds):
            prompt = prompts_by_key.get((item_id, prompt_index))
            if prompt is not None and int(prompt["sampling_seed"]) != prompt_seed:
                raise ValueError(
                    f"Condition '{condition_id}' stores the wrong prompt seed for "
                    f"{configured_item.id}:{prompt_index}."
                )
            prompt_id = None if prompt is None else int(prompt["prompt_id"])
            for image_seed in config.experiment.image_seeds:
                image = (
                    None
                    if prompt_id is None
                    else images_by_key.get((prompt_id, image_seed))
                )
                image_id = None if image is None else int(image["image_id"])
                image_path: Path | None = None
                if image is not None:
                    image_path = _resolve_image_path(run_directory, str(image["path"]))
                    if not image_path.is_file():
                        raise FileNotFoundError(
                            f"Condition '{condition_id}' references a missing image: "
                            f"{image_path}"
                        )
                verification = (
                    None
                    if image_id is None
                    else verifications_by_image.get((image_id,))
                )
                description = (
                    None if image_id is None else descriptions_by_image.get((image_id,))
                )
                common = {
                    "condition_id": condition_id,
                    "condition_label": condition.label or condition_id,
                    "design": condition.design,
                    "pg": condition.pg,
                    "bg": condition.bg,
                    "bb": condition.bb,
                    "bi": condition.bi,
                    "run_id": metadata["run_id"],
                    "run_name": metadata["name"],
                    "run_directory": str(run_directory),
                    "dataset_id": config.dataset.dataset_id,
                    "item_key": configured_item.id,
                    "item_index": item_index,
                    "domain": configured_item.domain,
                    "expected_title": configured_item.title,
                    "title_length_group": _title_length_group(configured_item.title),
                    "prompt_index": prompt_index,
                    "prompt_seed": prompt_seed,
                    "prompt_id": prompt_id,
                    "prompt_text": None if prompt is None else prompt["text"],
                    "image_seed": image_seed,
                    "image_id": image_id,
                    "image_path": None if image_path is None else str(image_path),
                    "verification_passed": (
                        None if verification is None else bool(verification["passed"])
                    ),
                    "verification_reason": (
                        None if verification is None else verification["reason"]
                    ),
                    "image_description": (
                        None if description is None else description["text"]
                    ),
                    "prompt_model": stage_models["prompt_generation"],
                    "image_model": stage_models["image_generation"],
                    "verifier_model": stage_models["verification"],
                    "description_model": stage_models["image_description"],
                }
                verifier_rows.append(dict(common))

                for route in condition.routes:
                    input_kind = "image" if route == "direct" else "description"
                    route_stage = route_stages[route]
                    prediction = (
                        None
                        if image_id is None
                        else predictions_by_key.get((image_id, input_kind))
                    )
                    error = _latest_error(
                        normalized_errors,
                        item_id=item_id,
                        prompt_id=prompt_id,
                        image_id=image_id,
                        image_seed=image_seed,
                        route_stage=route_stage,
                    )
                    predicted_title = (
                        None if prediction is None else str(prediction["title"])
                    )
                    strict = (
                        None
                        if predicted_title is None
                        else title_exact_match(configured_item.title, predicted_title)
                    )
                    normalized = (
                        None
                        if predicted_title is None
                        else title_normalized_exact_match(
                            configured_item.title,
                            predicted_title,
                        )
                    )
                    passed = verification is not None and bool(verification["passed"])
                    observations.append(
                        {
                            **common,
                            "route": route,
                            "prediction_model": stage_models[route_stage],
                            "prediction_status": (
                                "completed"
                                if prediction is not None
                                else "failed"
                                if error is not None
                                else "missing"
                            ),
                            "prediction_id": (
                                None
                                if prediction is None
                                else prediction["prediction_id"]
                            ),
                            "predicted_title": predicted_title,
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
                            "strict_exact_match": strict,
                            "normalized_exact_match": normalized,
                            "end_to_end_strict_score": int(passed and strict is True),
                            "end_to_end_normalized_score": int(
                                passed and normalized is True
                            ),
                            "error_stage": None if error is None else error["stage"],
                            "error_type": None
                            if error is None
                            else error["error_type"],
                            "error_message": None
                            if error is None
                            else error["message"],
                        }
                    )

    run_row = {
        "condition_id": condition_id,
        "condition_label": condition.label or condition_id,
        "design": condition.design,
        "pg": condition.pg,
        "bg": condition.bg,
        "bb": condition.bb,
        "bi": condition.bi,
        "routes": tuple(condition.routes),
        "run_id": metadata["run_id"],
        "run_name": metadata["name"],
        "run_directory": str(run_directory),
        "status": metadata["status"],
        "created_at": metadata["created_at"],
        "started_at": metadata["started_at"],
        "finished_at": metadata["finished_at"],
        "dataset_id": config.dataset.dataset_id,
        "title_count": len(config.dataset.items),
        "prompt_seeds": tuple(config.experiment.prompt_seeds),
        "image_seeds": tuple(config.experiment.image_seeds),
        "retry_limit": config.experiment.retry_limit,
        "prompt_model": stage_models["prompt_generation"],
        "image_model": stage_models["image_generation"],
        "verifier_model": stage_models["verification"],
        "description_model": stage_models["image_description"],
        "direct_model": stage_models["title_guessing_direct"],
        "description_title_model": stage_models["title_guessing_from_description"],
    }

    normalized_runtimes: list[dict[str, Any]] = []
    for row in runtimes:
        runtime = dict(row)
        runtime["condition_id"] = condition_id
        runtime["run_directory"] = str(run_directory)
        origin_run_id = row["origin_run_id"] or metadata["run_id"]
        origin_event_id = row["origin_runtime_event_id"] or row["runtime_event_id"]
        runtime["provenance_event_key"] = f"{origin_run_id}:{origin_event_id}"
        runtime["condition_runtime_eligible"] = row["execution_origin"] == "local"
        normalized_runtimes.append(runtime)

    return observations, run_row, normalized_errors, verifier_rows, normalized_runtimes


def load_study_frames(study: LoadedStudy | Path) -> StudyFrames:
    """Load all selected runs read-only and return normalized DataFrames."""
    loaded = load_study(study) if isinstance(study, Path) else study
    observations: list[dict[str, Any]] = []
    runs: list[dict[str, Any]] = []
    errors: list[dict[str, Any]] = []
    verifier: list[dict[str, Any]] = []
    runtimes: list[dict[str, Any]] = []

    for condition_id, condition in loaded.config.conditions.items():
        values = _load_condition(
            condition_id,
            condition,
            loaded.run_directories[condition_id],
        )
        condition_observations, run, condition_errors, checks, runtime = values
        observations.extend(condition_observations)
        runs.append(run)
        errors.extend(condition_errors)
        verifier.extend(checks)
        runtimes.extend(runtime)

    runtime_frame = pd.DataFrame.from_records(runtimes)
    if not runtime_frame.empty:
        started = pd.to_datetime(runtime_frame["started_at"], utc=True)
        finished = pd.to_datetime(runtime_frame["finished_at"], utc=True)
        runtime_frame["duration_seconds"] = (finished - started).dt.total_seconds()
        runtime_frame["study_runtime_eligible"] = ~runtime_frame[
            "provenance_event_key"
        ].duplicated(keep="first")

    return StudyFrames(
        observations=pd.DataFrame.from_records(observations),
        runs=pd.DataFrame.from_records(runs),
        errors=pd.DataFrame.from_records(errors),
        verifier=pd.DataFrame.from_records(verifier).drop_duplicates(
            subset=["condition_id", "item_key", "prompt_seed", "image_seed"]
        ),
        runtimes=runtime_frame,
    )
