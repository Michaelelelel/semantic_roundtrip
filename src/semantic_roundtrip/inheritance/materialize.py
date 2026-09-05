"""Materialize one source run into a self-contained derived target run."""

import hashlib
import json
import sqlite3
from pathlib import Path

from semantic_roundtrip.config import ResolvedAppConfig, StageName
from semantic_roundtrip.config_resolution import (
    configured_image_verification_policies,
    configured_stage_names,
)
from semantic_roundtrip.inheritance.dependencies import dependency_closure
from semantic_roundtrip.inheritance.files import (
    copy_artifact,
    native_path,
    walk_artifact_paths,
)
from semantic_roundtrip.inheritance.source import (
    load_source_run,
    resolve_stage_provenance,
)
from semantic_roundtrip.persistence.run.config_snapshot import (
    DESCRIPTION_TITLE_GUESSING_PROMPT_FILENAME,
    DIRECT_TITLE_GUESSING_PROMPT_FILENAME,
    EFFECTIVE_CONFIG_FILENAME,
    ILLUSTRATABILITY_PROMPT_PROFILE_FILENAME,
    IMAGE_DESCRIPTION_PROMPT_FILENAME,
    INPUT_CONFIG_FILENAME,
    PROMPT_PROFILE_FILENAME,
    PROMPT_TITLE_GUESSING_PROMPT_FILENAME,
    STRICT_IMAGE_VERIFICATION_PROMPT_FILENAME,
    TITLE_AWARE_IMAGE_VERIFICATION_PROMPT_FILENAME,
)
from semantic_roundtrip.persistence.run.manifest import MANIFEST_FILENAME
from semantic_roundtrip.persistence.run.schema import (
    connect_run_database,
    database_path_for_run,
    require_run_schema,
)
from semantic_roundtrip.persistence.run.workflow_snapshot import (
    IMAGE_GENERATION_WORKFLOW_FILENAME,
)
from semantic_roundtrip.persistence.sqlite import utc_now


class MaterializationError(RuntimeError):
    """The selected source cannot safely provide the requested work."""


def _rows(connection: sqlite3.Connection, table: str) -> list[sqlite3.Row]:
    return connection.execute(f"SELECT * FROM {table}").fetchall()


def _original(
    row: sqlite3.Row, run_column: str, id_column: str, run_id: str
) -> tuple[str, int]:
    origin_run_id = row[run_column]
    origin_id = row[id_column]
    return (
        run_id if origin_run_id is None else str(origin_run_id),
        int(row[0]) if origin_id is None else int(origin_id),
    )


def _failed_task(
    tasks: list[sqlite3.Row],
    stage: StageName,
    *,
    item_id: int | None = None,
    prompt_id: int | None = None,
    image_id: int | None = None,
    seed: int | None = None,
    task_key_prefix: str | None = None,
) -> bool:
    for task in tasks:
        if task["stage"] != stage or task["status"] != "failed":
            continue
        if task_key_prefix is not None and not str(task["task_key"]).startswith(
            task_key_prefix
        ):
            continue
        checks = (
            ("item_id", item_id),
            ("prompt_id", prompt_id),
            ("image_id", image_id),
            ("seed", seed),
        )
        if all(value is None or task[column] == value for column, value in checks):
            return True
    return False


def _validate_source(
    connection: sqlite3.Connection,
    config: ResolvedAppConfig,
    stages: tuple[StageName, ...],
    run_directory: Path | None = None,
    *,
    image_policies: tuple[str, ...] = (),
) -> None:
    available = set(configured_stage_names(config))
    if config.inherit is not None:
        available.update(dependency_closure(config.inherit.stages))
    missing = set(stages) - available
    if missing:
        raise MaterializationError(
            f"Source does not provide selected stages: {', '.join(sorted(missing))}."
        )
    placeholders = ", ".join("?" for _ in stages)
    unfinished = connection.execute(
        f"""
        SELECT task_key, stage, status
        FROM stage_tasks
        WHERE stage IN ({placeholders})
          AND status IN ('pending', 'running')
        ORDER BY task_id
        """,
        stages,
    ).fetchall()
    if unfinished:
        first = unfinished[0]
        raise MaterializationError(
            f"Inherited stage '{first['stage']}' still contains {first['status']} "
            f"task '{first['task_key']}'."
        )
    active_runtime = connection.execute(
        f"""
        SELECT stage
        FROM runtime_events
        WHERE stage IN ({placeholders}) AND status = 'started'
        LIMIT 1
        """,
        stages,
    ).fetchone()
    if active_runtime is not None:
        raise MaterializationError(
            f"Inherited stage '{active_runtime['stage']}' still has an active "
            "runtime event."
        )

    items = _rows(connection, "dataset_items")
    ratings = _rows(connection, "illustratability_ratings")
    prompts = _rows(connection, "prompts")
    images = _rows(connection, "images")
    prompt_verifications = _rows(connection, "prompt_verifications")
    image_verifications = _rows(connection, "image_verifications")
    descriptions = _rows(connection, "image_descriptions")
    predictions = _rows(connection, "predictions")
    prompt_predictions = _rows(connection, "prompt_predictions")
    tasks = _rows(connection, "stage_tasks")

    if len(items) != len(config.dataset.items):
        raise MaterializationError(
            "Source dataset rows do not match its effective configuration."
        )
    items_by_index = {int(row["item_index"]): row for row in items}
    for index, configured in enumerate(config.dataset.items):
        row = items_by_index.get(index)
        if row is None or (row["item_key"], row["domain"], row["title"]) != (
            configured.id,
            configured.domain,
            configured.title,
        ):
            raise MaterializationError(
                f"Source dataset item {index} differs from its snapshot."
            )

    rating_item_ids = {int(row["item_id"]) for row in ratings}
    if "illustratability_rating" in stages:
        for item in items:
            item_id = int(item["item_id"])
            if item_id not in rating_item_ids and not _failed_task(
                tasks,
                "illustratability_rating",
                item_id=item_id,
            ):
                raise MaterializationError(
                    "Source illustratability rating is missing without a terminal "
                    "task error."
                )

    prompt_lookup = {
        (int(row["item_id"]), int(row["prompt_index"])): row for row in prompts
    }
    if "prompt_generation" in stages:
        for item in items:
            for prompt_index, seed in enumerate(config.experiment.prompt_seeds):
                key = (int(item["item_id"]), prompt_index)
                if (
                    key in prompt_lookup
                    and int(prompt_lookup[key]["sampling_seed"]) != seed
                ):
                    raise MaterializationError(
                        "Source prompt seed differs from its snapshot."
                    )
                if key not in prompt_lookup and not _failed_task(
                    tasks,
                    "prompt_generation",
                    item_id=int(item["item_id"]),
                    seed=seed,
                ):
                    raise MaterializationError(
                        "Source prompt is missing without a terminal task error."
                    )

    image_lookup = {(int(row["prompt_id"]), int(row["seed"])): row for row in images}
    if "image_generation" in stages:
        for prompt in prompts:
            for seed in config.experiment.image_seeds:
                key = (int(prompt["prompt_id"]), seed)
                if key not in image_lookup and not _failed_task(
                    tasks,
                    "image_generation",
                    prompt_id=int(prompt["prompt_id"]),
                    seed=seed,
                ):
                    raise MaterializationError(
                        "Source image is missing without a terminal task error."
                    )

    prompt_verification_ids = {int(row["prompt_id"]) for row in prompt_verifications}
    image_verification_keys = {
        (int(row["image_id"]), str(row["policy"])) for row in image_verifications
    }
    description_ids = {int(row["image_id"]) for row in descriptions}
    prediction_keys = {
        (int(row["image_id"]), str(row["input_kind"])) for row in predictions
    }
    if "verification_prompt" in stages:
        for prompt in prompts:
            prompt_id = int(prompt["prompt_id"])
            if prompt_id not in prompt_verification_ids and not _failed_task(
                tasks,
                "verification_prompt",
                prompt_id=prompt_id,
                task_key_prefix="verification_prompt:reference_title_absent:",
            ):
                raise MaterializationError(
                    "Source prompt verification is missing without a terminal "
                    "task error."
                )

    required_image_policies = set(configured_image_verification_policies(config))
    required_image_policies.update(image_policies)
    if "verification_image" in stages and run_directory is not None:
        provider = resolve_stage_provenance(config, run_directory, "verification_image")
        if provider is not None:
            required_image_policies.update(
                configured_image_verification_policies(provider[0])
            )
    for task in tasks:
        task_key = str(task["task_key"])
        for policy in ("strict", "title_aware"):
            if task_key.startswith(f"verification_image:{policy}:"):
                required_image_policies.add(policy)
    required_image_policies.update(str(row["policy"]) for row in image_verifications)
    if "verification_image" in stages and images and not required_image_policies:
        raise MaterializationError(
            "Source has no identifiable image-verification policies."
        )
    for image in images:
        image_id = int(image["image_id"])
        if "verification_image" in stages:
            for policy in required_image_policies:
                if (
                    image_id,
                    policy,
                ) not in image_verification_keys and not _failed_task(
                    tasks,
                    "verification_image",
                    image_id=image_id,
                    task_key_prefix=f"verification_image:{policy}:",
                ):
                    raise MaterializationError(
                        f"Source {policy} image verification is missing without "
                        "a terminal task error."
                    )
        if (
            "title_guessing_direct" in stages
            and (image_id, "image") not in prediction_keys
            and not _failed_task(tasks, "title_guessing_direct", image_id=image_id)
        ):
            raise MaterializationError(
                "Source direct prediction is missing without a terminal task error."
            )
        if (
            "image_description" in stages
            and image_id not in description_ids
            and not _failed_task(tasks, "image_description", image_id=image_id)
        ):
            raise MaterializationError(
                "Source description is missing without a terminal task error."
            )

    if "title_guessing_from_description" in stages:
        for description in descriptions:
            image_id = int(description["image_id"])
            if (image_id, "description") not in prediction_keys and not _failed_task(
                tasks,
                "title_guessing_from_description",
                image_id=image_id,
            ):
                raise MaterializationError(
                    "Source description prediction is missing without a terminal "
                    "task error."
                )

    if "title_guessing_from_prompt" in stages:
        prediction_prompt_ids = {int(row["prompt_id"]) for row in prompt_predictions}
        for prompt in prompts:
            prompt_id = int(prompt["prompt_id"])
            if prompt_id not in prediction_prompt_ids and not _failed_task(
                tasks, "title_guessing_from_prompt", prompt_id=prompt_id
            ):
                raise MaterializationError(
                    "Source prompt prediction is missing without a terminal task error."
                )


def _copy_images(
    source_directory: Path,
    target_directory: Path,
    source_run_id: str,
    image_rows: list[sqlite3.Row],
) -> tuple[dict[int, str], list[Path]]:
    relative_paths: dict[int, str] = {}
    copied: list[Path] = []
    destination_directory = target_directory / "images" / "imported" / source_run_id
    native_path(destination_directory).mkdir(parents=True, exist_ok=True)
    try:
        for row in image_rows:
            image_id = int(row["image_id"])
            source_path = (source_directory / str(row["path"])).resolve()
            if not source_path.is_relative_to(source_directory.resolve()):
                raise MaterializationError(
                    "Inherited image path escapes its source run."
                )
            if not native_path(source_path).is_file():
                raise MaterializationError(
                    f"Inherited image file does not exist: {source_path}"
                )
            try:
                with native_path(source_path).open("rb"):
                    pass
            except OSError as error:
                raise MaterializationError(
                    f"Inherited image file is not readable: {source_path}"
                ) from error
            suffix = source_path.suffix or ".bin"
            destination = destination_directory / f"image_{image_id}{suffix}"
            with native_path(source_path).open("rb") as file:
                before = hashlib.file_digest(file, "sha256").hexdigest()
            copy_artifact(source_path, destination)
            copied.append(destination)
            with native_path(source_path).open("rb") as file:
                after = hashlib.file_digest(file, "sha256").hexdigest()
            with native_path(destination).open("rb") as file:
                copied_hash = hashlib.file_digest(file, "sha256").hexdigest()
            if before != after or before != copied_hash:
                raise MaterializationError("Source image changed during inheritance.")
            relative_paths[image_id] = destination.relative_to(
                target_directory
            ).as_posix()
    except Exception:
        for path in copied:
            native_path(path).unlink(missing_ok=True)
        raise
    return relative_paths, copied


def _copy_provenance(
    source_directory: Path, target_directory: Path, source_run_id: str
) -> list[Path]:
    copied: list[Path] = []
    destination_root = target_directory / "provenance" / source_run_id
    native_path(destination_root).mkdir(parents=True, exist_ok=True)
    candidates = [
        source_directory / INPUT_CONFIG_FILENAME,
        source_directory / EFFECTIVE_CONFIG_FILENAME,
        source_directory / MANIFEST_FILENAME,
        source_directory / ILLUSTRATABILITY_PROMPT_PROFILE_FILENAME,
        source_directory / PROMPT_PROFILE_FILENAME,
        source_directory / STRICT_IMAGE_VERIFICATION_PROMPT_FILENAME,
        source_directory / TITLE_AWARE_IMAGE_VERIFICATION_PROMPT_FILENAME,
        source_directory / IMAGE_DESCRIPTION_PROMPT_FILENAME,
        source_directory / DIRECT_TITLE_GUESSING_PROMPT_FILENAME,
        source_directory / DESCRIPTION_TITLE_GUESSING_PROMPT_FILENAME,
        source_directory / PROMPT_TITLE_GUESSING_PROMPT_FILENAME,
        source_directory / IMAGE_GENERATION_WORKFLOW_FILENAME,
        source_directory / "migration_record.json",
    ]
    source_provenance = source_directory / "provenance"
    if native_path(source_provenance).is_dir():
        candidates.extend(
            path
            for path in walk_artifact_paths(source_provenance)
            if native_path(path).is_file()
        )
    try:
        for source_path in candidates:
            if not native_path(source_path).is_file():
                if source_path.name == EFFECTIVE_CONFIG_FILENAME:
                    raise MaterializationError(
                        f"Inherited run is missing {source_path.name}."
                    )
                continue
            if source_provenance in source_path.parents:
                relative = Path("chain") / source_path.relative_to(source_provenance)
            else:
                relative = Path(source_path.name)
            destination = destination_root / relative
            native_path(destination.parent).mkdir(parents=True, exist_ok=True)
            copy_artifact(source_path, destination)
            copied.append(destination)
    except Exception:
        for path in reversed(copied):
            native_path(path).unlink(missing_ok=True)
        raise
    return copied


def _insert_materialized_rows(
    *,
    source: sqlite3.Connection,
    target: sqlite3.Connection,
    source_run_id: str,
    target_run_id: str,
    stages: tuple[StageName, ...],
    image_paths: dict[int, str],
    source_directory: Path,
) -> None:
    item_map: dict[int, int] = {}
    prompt_map: dict[int, int] = {}
    image_map: dict[int, int] = {}
    description_map: dict[int, int] = {}
    task_map: dict[int, int] = {}

    for row in _rows(source, "dataset_items"):
        origin_run_id, origin_item_id = _original(
            row, "origin_run_id", "origin_item_id", source_run_id
        )
        cursor = target.execute(
            """
            INSERT INTO dataset_items (
                run_id, item_index, item_key, domain, title,
                execution_origin, origin_run_id, origin_item_id
            ) VALUES (?, ?, ?, ?, ?, 'imported', ?, ?)
            """,
            (
                target_run_id,
                row["item_index"],
                row["item_key"],
                row["domain"],
                row["title"],
                origin_run_id,
                origin_item_id,
            ),
        )
        item_map[int(row["item_id"])] = int(cursor.lastrowid)

    if "illustratability_rating" in stages:
        for row in _rows(source, "illustratability_ratings"):
            origin_run_id, origin_rating_id = _original(
                row, "origin_run_id", "origin_rating_id", source_run_id
            )
            target.execute(
                """
                INSERT INTO illustratability_ratings (
                    item_id, score, backend_request_id, raw_response, created_at,
                    origin_run_id, origin_rating_id
                ) VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    item_map[int(row["item_id"])],
                    row["score"],
                    row["backend_request_id"],
                    row["raw_response"],
                    row["created_at"],
                    origin_run_id,
                    origin_rating_id,
                ),
            )

    if "prompt_generation" in stages:
        for row in _rows(source, "prompts"):
            origin_run_id, origin_prompt_id = _original(
                row, "origin_run_id", "origin_prompt_id", source_run_id
            )
            cursor = target.execute(
                """
                INSERT INTO prompts (
                    item_id, prompt_index, sampling_seed, text,
                    backend_request_id, raw_response, created_at,
                    origin_run_id, origin_prompt_id
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    item_map[int(row["item_id"])],
                    row["prompt_index"],
                    row["sampling_seed"],
                    row["text"],
                    row["backend_request_id"],
                    row["raw_response"],
                    row["created_at"],
                    origin_run_id,
                    origin_prompt_id,
                ),
            )
            prompt_map[int(row["prompt_id"])] = int(cursor.lastrowid)

    if "image_generation" in stages:
        for row in _rows(source, "images"):
            origin_run_id, origin_image_id = _original(
                row, "origin_run_id", "origin_image_id", source_run_id
            )
            cursor = target.execute(
                """
                INSERT INTO images (
                    prompt_id, seed, path, backend_job_id, raw_response,
                    origin_run_id, origin_image_id
                ) VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    prompt_map[int(row["prompt_id"])],
                    row["seed"],
                    image_paths[int(row["image_id"])],
                    row["backend_job_id"],
                    row["raw_response"],
                    origin_run_id,
                    origin_image_id,
                ),
            )
            image_map[int(row["image_id"])] = int(cursor.lastrowid)

    if "verification_prompt" in stages:
        for row in _rows(source, "prompt_verifications"):
            origin_run_id, origin_id = _original(
                row,
                "origin_run_id",
                "origin_prompt_verification_id",
                source_run_id,
            )
            target.execute(
                """
                INSERT INTO prompt_verifications (
                    prompt_id, policy, passed, reason, method, raw_response,
                    created_at, origin_run_id,
                    origin_prompt_verification_id
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    prompt_map[int(row["prompt_id"])],
                    row["policy"],
                    row["passed"],
                    row["reason"],
                    row["method"],
                    row["raw_response"],
                    row["created_at"],
                    origin_run_id,
                    origin_id,
                ),
            )
    if "verification_image" in stages:
        for row in _rows(source, "image_verifications"):
            origin_run_id, origin_id = _original(
                row,
                "origin_run_id",
                "origin_image_verification_id",
                source_run_id,
            )
            target.execute(
                """
                INSERT INTO image_verifications (
                    image_id, policy, passed, reason, method, raw_response,
                    created_at, origin_run_id,
                    origin_image_verification_id
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    image_map[int(row["image_id"])],
                    row["policy"],
                    row["passed"],
                    row["reason"],
                    row["method"],
                    row["raw_response"],
                    row["created_at"],
                    origin_run_id,
                    origin_id,
                ),
            )

    if "image_description" in stages:
        for row in _rows(source, "image_descriptions"):
            origin_run_id, origin_id = _original(
                row, "origin_run_id", "origin_description_id", source_run_id
            )
            cursor = target.execute(
                """
                INSERT INTO image_descriptions (
                    image_id, text, backend_request_id, raw_response, created_at,
                    origin_run_id, origin_description_id
                ) VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    image_map[int(row["image_id"])],
                    row["text"],
                    row["backend_request_id"],
                    row["raw_response"],
                    row["created_at"],
                    origin_run_id,
                    origin_id,
                ),
            )
            description_map[int(row["description_id"])] = int(cursor.lastrowid)

    prediction_kinds: list[str] = []
    if "title_guessing_direct" in stages:
        prediction_kinds.append("image")
    if "title_guessing_from_description" in stages:
        prediction_kinds.append("description")
    if prediction_kinds:
        for row in _rows(source, "predictions"):
            if row["input_kind"] not in prediction_kinds:
                continue
            origin_run_id, origin_id = _original(
                row, "origin_run_id", "origin_prediction_id", source_run_id
            )
            source_description_id = row["description_id"]
            target.execute(
                """
                INSERT INTO predictions (
                    image_id, description_id, input_kind, title, confidence,
                    confidence_type, raw_response, origin_run_id,
                    origin_prediction_id
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    image_map[int(row["image_id"])],
                    (
                        None
                        if source_description_id is None
                        else description_map[int(source_description_id)]
                    ),
                    row["input_kind"],
                    row["title"],
                    row["confidence"],
                    row["confidence_type"],
                    row["raw_response"],
                    origin_run_id,
                    origin_id,
                ),
            )

    if "title_guessing_from_prompt" in stages:
        for row in _rows(source, "prompt_predictions"):
            origin_run_id, origin_id = _original(
                row, "origin_run_id", "origin_prompt_prediction_id", source_run_id
            )
            target.execute(
                """
                INSERT INTO prompt_predictions (
                    prompt_id, title, confidence, confidence_type, raw_response,
                    origin_run_id, origin_prompt_prediction_id
                ) VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    prompt_map[int(row["prompt_id"])],
                    row["title"],
                    row["confidence"],
                    row["confidence_type"],
                    row["raw_response"],
                    origin_run_id,
                    origin_id,
                ),
            )

    selected = set(stages)
    for row in _rows(source, "stage_tasks"):
        if row["stage"] not in selected:
            continue
        origin_run_id, origin_id = _original(
            row, "origin_run_id", "origin_task_id", source_run_id
        )
        cursor = target.execute(
            """
            INSERT INTO stage_tasks (
                run_id, task_key, stage, status, item_id, prompt_id, image_id,
                seed, attempt, expected_outputs, completed_outputs, created_at,
                started_at, updated_at, finished_at, execution_origin,
                origin_run_id, origin_task_id
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?,
                      'imported', ?, ?)
            """,
            (
                target_run_id,
                row["task_key"],
                row["stage"],
                row["status"],
                None if row["item_id"] is None else item_map[int(row["item_id"])],
                (
                    None
                    if row["prompt_id"] is None
                    else prompt_map[int(row["prompt_id"])]
                ),
                (None if row["image_id"] is None else image_map[int(row["image_id"])]),
                row["seed"],
                row["attempt"],
                row["expected_outputs"],
                row["completed_outputs"],
                row["created_at"],
                row["started_at"],
                row["updated_at"],
                row["finished_at"],
                origin_run_id,
                origin_id,
            ),
        )
        task_map[int(row["task_id"])] = int(cursor.lastrowid)

    for row in _rows(source, "stage_errors"):
        if row["stage"] not in selected:
            continue
        origin_run_id, origin_id = _original(
            row, "origin_run_id", "origin_error_id", source_run_id
        )
        target.execute(
            """
            INSERT INTO stage_errors (
                run_id, task_id, stage, item_id, prompt_id, image_id, attempt,
                error_type, message, raw_response, created_at, execution_origin,
                origin_run_id, origin_error_id
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 'imported', ?, ?)
            """,
            (
                target_run_id,
                None if row["task_id"] is None else task_map[int(row["task_id"])],
                row["stage"],
                None if row["item_id"] is None else item_map[int(row["item_id"])],
                (
                    None
                    if row["prompt_id"] is None
                    else prompt_map[int(row["prompt_id"])]
                ),
                (None if row["image_id"] is None else image_map[int(row["image_id"])]),
                row["attempt"],
                row["error_type"],
                row["message"],
                row["raw_response"],
                row["created_at"],
                origin_run_id,
                origin_id,
            ),
        )

    for row in _rows(source, "runtime_events"):
        if row["stage"] not in selected:
            continue
        origin_run_id, origin_id = _original(
            row, "origin_run_id", "origin_runtime_event_id", source_run_id
        )
        target.execute(
            """
            INSERT INTO runtime_events (
                run_id, stage, backend_alias, controller, resource_group,
                model_id, action, status, started_at, finished_at, error_type,
                error_message, execution_origin, origin_run_id,
                origin_runtime_event_id
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 'imported', ?, ?)
            """,
            (
                target_run_id,
                row["stage"],
                row["backend_alias"],
                row["controller"],
                row["resource_group"],
                row["model_id"],
                row["action"],
                row["status"],
                row["started_at"],
                row["finished_at"],
                row["error_type"],
                row["error_message"],
                origin_run_id,
                origin_id,
            ),
        )

    source_record = source.execute("SELECT name FROM run_metadata").fetchone()
    target.execute(
        """
        INSERT INTO run_lineage (
            run_id, depth, source_run_id, source_run_name,
            source_run_directory, inherited_stages, materialized_at
        ) VALUES (?, 0, ?, ?, ?, ?, ?)
        """,
        (
            target_run_id,
            source_run_id,
            source_record["name"],
            str(source_directory),
            json.dumps(stages),
            utc_now(),
        ),
    )
    for row in _rows(source, "run_lineage"):
        target.execute(
            """
            INSERT INTO run_lineage (
                run_id, depth, source_run_id, source_run_name,
                source_run_directory, inherited_stages, materialized_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            (
                target_run_id,
                int(row["depth"]) + 1,
                row["source_run_id"],
                row["source_run_name"],
                row["source_run_directory"],
                row["inherited_stages"],
                row["materialized_at"],
            ),
        )


def materialize_inheritance(config: ResolvedAppConfig, target_directory: Path) -> bool:
    """Copy configured source work once; return whether copying was performed."""
    inheritance = config.inherit
    if inheritance is None:
        return False

    target_directory = target_directory.resolve()
    target_database_path = database_path_for_run(target_directory)
    target = connect_run_database(target_database_path)
    try:
        require_run_schema(target)
        target_record = target.execute("SELECT run_id FROM run_metadata").fetchone()
        if target_record is None:
            raise MaterializationError("Target run metadata is missing.")
        existing = target.execute(
            "SELECT source_run_id FROM run_lineage WHERE depth = 0"
        ).fetchone()
        if existing is not None:
            if existing["source_run_id"] != inheritance.source_run_id:
                raise MaterializationError(
                    "Target run was already materialized from a different source."
                )
            return False
    finally:
        target.close()

    source_run = load_source_run(inheritance.source_run)
    if source_run.run_id != inheritance.source_run_id:
        raise MaterializationError(
            "Configured source_run_id does not match the source database."
        )
    stages = dependency_closure(inheritance.stages)
    source = connect_run_database(
        database_path_for_run(source_run.directory), read_only=True
    )
    copied_files: list[Path] = []
    try:
        # Keep validation and every copied row in one WAL-compatible read snapshot.
        # Unrelated later stages in the source run may continue writing normally.
        source.execute("BEGIN")
        require_run_schema(source)
        record = source.execute("SELECT run_id FROM run_metadata").fetchone()
        if record is None or record["run_id"] != inheritance.source_run_id:
            raise MaterializationError(
                "Source identity changed before materialization."
            )
        _validate_source(source, source_run.config, stages, source_run.directory)
        image_rows = _rows(source, "images") if "image_generation" in stages else []
        image_paths, copied_images = _copy_images(
            source_run.directory,
            target_directory,
            source_run.run_id,
            image_rows,
        )
        copied_files.extend(copied_images)
        copied_files.extend(
            _copy_provenance(
                source_run.directory,
                target_directory,
                source_run.run_id,
            )
        )

        target = connect_run_database(target_database_path)
        try:
            require_run_schema(target)
            target.execute("BEGIN IMMEDIATE")
            target_record = target.execute("SELECT run_id FROM run_metadata").fetchone()
            assert target_record is not None
            _insert_materialized_rows(
                source=source,
                target=target,
                source_run_id=source_run.run_id,
                target_run_id=str(target_record["run_id"]),
                stages=stages,
                image_paths=image_paths,
                source_directory=source_run.directory,
            )
            target.commit()
        except Exception:
            target.rollback()
            raise
        finally:
            target.close()
    except Exception:
        for path in reversed(copied_files):
            native_path(path).unlink(missing_ok=True)
        raise
    finally:
        source.close()
    return True
