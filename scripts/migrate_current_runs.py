"""One-shot, copy-only conversion of completed schema-10/database-11 jobs.

This is deliberately not imported by the application. Older scientific formats
are rejected, not interpreted as the current study. Run without --apply first.
"""

from __future__ import annotations

import argparse
import copy
import hashlib
import json
import shutil
import sqlite3
import sys
import uuid
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import yaml

from semantic_roundtrip.config import InputAppConfig, ResolvedAppConfig
from semantic_roundtrip.evaluation import (
    title_exact_match,
    title_normalized_exact_match,
)
from semantic_roundtrip.inheritance.files import (
    copy_artifact,
    native_path,
    walk_artifact_paths,
)
from semantic_roundtrip.job.config import InputJobConfig, ResolvedJobConfig
from semantic_roundtrip.persistence.run.schema import PROMPT_PREDICTIONS_SCHEMA

CONVERTER_VERSION = "split_verification_prompt_baseline_v1"
RUN_DB = "pipeline_state.sqlite"
JOB_DB = "job_state.sqlite"
CONFIG = "config_snapshot.yaml"
OLD_STAGES = {
    "illustratability_rating",
    "prompt_generation",
    "image_generation",
    "verification",
    "title_guessing_direct",
    "image_description",
    "title_guessing_from_description",
}


def fail(message: str) -> None:
    raise ValueError(message)


def read_yaml(path: Path) -> dict[str, Any]:
    value = yaml.safe_load(native_path(path).read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        fail(f"Expected a YAML mapping: {path}")
    return value


def digest(path: Path) -> str:
    with native_path(path).open("rb") as file:
        return hashlib.file_digest(file, "sha256").hexdigest()


def connect(path: Path) -> sqlite3.Connection:
    connection = sqlite3.connect(path.resolve().as_uri() + "?mode=ro", uri=True)
    connection.row_factory = sqlite3.Row
    connection.execute("PRAGMA query_only = ON")
    connection.execute("PRAGMA foreign_keys = ON")
    connection.execute("BEGIN")
    return connection


def rows(connection: sqlite3.Connection, table: str) -> list[dict[str, Any]]:
    return [
        dict(row)
        for row in connection.execute(f'SELECT * FROM "{table}" ORDER BY rowid')
    ]


def database_rows(connection: sqlite3.Connection) -> dict[str, list[dict[str, Any]]]:
    tables = connection.execute(
        "SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%' ORDER BY name"
    )
    return {row[0]: rows(connection, row[0]) for row in tables}


def database_checks(connection: sqlite3.Connection, version: int) -> None:
    actual = connection.execute("PRAGMA user_version").fetchone()[0]
    if actual != version:
        fail(f"Unsupported database schema {actual}; expected exactly {version}.")
    if [row[0] for row in connection.execute("PRAGMA integrity_check")] != ["ok"]:
        fail("SQLite integrity check failed.")
    if connection.execute("PRAGMA foreign_key_check").fetchall():
        fail("SQLite foreign-key check failed.")


def inside(root: Path, relative: str) -> Path:
    path = (root / relative).resolve()
    if not path.is_relative_to(root.resolve()):
        fail(f"Artifact escapes its directory: {relative}")
    return path


def file_hashes(directory: Path) -> dict[str, str]:
    result = {}
    for path in sorted(walk_artifact_paths(directory)):
        if native_path(path).is_symlink():
            fail(f"Symbolic links are not accepted in migration sources: {path}")
        if native_path(path).is_file() and not path.name.endswith(("-wal", "-shm")):
            result[path.relative_to(directory).as_posix()] = digest(path)
    return result


def verification_lanes(
    run_id: str,
    snapshots: dict[str, dict[str, Any]],
    visiting: frozenset[str] = frozenset(),
) -> tuple[str, ...]:
    if run_id in visiting or run_id not in snapshots:
        fail(f"Missing or cyclic original stage provenance for {run_id}.")
    config = snapshots[run_id]
    verification = config["stages"].get("verification")
    found: set[str] = set()
    if verification:
        if verification.get("prompt"):
            found.add("verification_prompt")
        if verification.get("image"):
            found.add("verification_image")
    inheritance = config.get("inherit")
    if inheritance and "verification" in inheritance["stages"]:
        found.update(
            verification_lanes(
                inheritance["source_run_id"], snapshots, visiting | {run_id}
            )
        )
    return tuple(
        lane for lane in ("verification_prompt", "verification_image") if lane in found
    )


def map_stages(stages: list[str], lanes: tuple[str, ...]) -> list[str]:
    if any(stage not in OLD_STAGES for stage in stages) or len(stages) != len(
        set(stages)
    ):
        fail("Unknown or duplicate original stage name.")
    if "verification" in stages and not lanes:
        fail("Cannot resolve configured checks for inherited verification.")
    result = []
    for stage in stages:
        result.extend(lanes if stage == "verification" else [stage])
    return result


def convert_config(
    original: dict[str, Any],
    snapshots: dict[str, dict[str, Any]],
    source_id: str | None = None,
) -> dict[str, Any]:
    if original.get("schema_version") != 10:
        fail(
            "Only experiment schema 10 is supported; no legacy prompt conversion is attempted."
        )
    converted = copy.deepcopy(original)
    converted["schema_version"] = 11
    stages = converted["stages"]
    verification = stages.pop("verification", None)
    if verification:
        if verification.get("prompt"):
            stages["verification_prompt"] = verification["prompt"]
        if verification.get("image"):
            stages["verification_image"] = {
                "backend": verification["backend"],
                "parameters": verification.get("parameters", {}),
                "policies": verification["image"],
            }
    inheritance = converted.get("inherit")
    if inheritance:
        source_id = inheritance.get("source_run_id", source_id)
        if source_id is None and inheritance.get("from_run"):
            source_id = (
                str(inheritance["from_run"])
                .replace("\\", "/")
                .rstrip("/")
                .split("/")[-1]
            )
        lanes = verification_lanes(source_id, snapshots) if source_id else ()
        inheritance["stages"] = map_stages(inheritance["stages"], lanes)
    model = (
        ResolvedAppConfig
        if converted.get("configuration_kind") == "effective"
        else InputAppConfig
    )
    model.model_validate(converted)
    return converted


def split_task(row: dict[str, Any]) -> tuple[str, str]:
    key = row["task_key"]
    if key.startswith("verification:prompt:reference_title_absent:"):
        if row["prompt_id"] is None or row["image_id"] is not None:
            fail("Prompt-verification task has inconsistent artifact references.")
        return "verification_prompt", key.replace(
            "verification:prompt:", "verification_prompt:", 1
        )
    for policy in ("strict", "title_aware"):
        if key.startswith(f"verification:image:{policy}:"):
            if row["prompt_id"] is None or row["image_id"] is None:
                fail("Image-verification task has inconsistent artifact references.")
            return "verification_image", key.replace(
                "verification:image:", "verification_image:", 1
            )
    fail(f"Ambiguous grouped verification task: {key}")


def mapped_tables(
    original: dict[str, list[dict[str, Any]]],
    run_id: str,
    snapshots: dict[str, dict[str, Any]],
) -> dict[str, list[dict[str, Any]]]:
    result = copy.deepcopy(original)
    tasks = {row["task_id"]: row for row in result["stage_tasks"]}
    for task in tasks.values():
        if task["stage"] == "verification":
            task["stage"], task["task_key"] = split_task(task)
    if len({row["task_key"] for row in tasks.values()}) != len(tasks):
        fail("Converted task keys collide.")
    for error in result["stage_errors"]:
        if error["stage"] != "verification":
            continue
        task = tasks.get(error["task_id"])
        if task is None or task["stage"] not in {
            "verification_prompt",
            "verification_image",
        }:
            fail("Cannot assign grouped verification error to a known task.")
        if any(error[key] != task[key] for key in ("item_id", "prompt_id", "image_id")):
            fail("Verification error and task artifact references disagree.")
        error["stage"] = task["stage"]
    for event in result["runtime_events"]:
        if event["stage"] == "verification":
            if "verification_image" not in verification_lanes(run_id, snapshots):
                fail("Grouped runtime event has no image-verification provider.")
            # The old runner activated only the image verifier's model. Do not
            # duplicate its load/reuse/unload event or invent prompt CPU runtime.
            event["stage"] = "verification_image"
    for lineage in result["run_lineage"]:
        lineage["inherited_stages"] = json.dumps(
            map_stages(
                json.loads(lineage["inherited_stages"]),
                verification_lanes(lineage["source_run_id"], snapshots),
            )
        )
    result["prompt_predictions"] = []
    return result


def metric_counts(
    tables: dict[str, list[dict[str, Any]]], config: dict[str, Any]
) -> dict[str, Any]:
    """Check all four old-route endpoint numerators, without generating outputs."""
    items = {row["item_id"]: row for row in tables["dataset_items"]}
    prompts = {row["prompt_id"]: row for row in tables["prompts"]}
    images = {row["image_id"]: row for row in tables["images"]}
    prompt_pass = {
        row["prompt_id"]: row["passed"] for row in tables["prompt_verifications"]
    }
    image_pass = {
        (row["image_id"], row["policy"]): row["passed"]
        for row in tables["image_verifications"]
    }
    result: dict[str, Any] = {
        "planned_per_image_route": len(config["dataset"]["items"])
        * len(config["experiment"]["prompt_seeds"])
        * len(config["experiment"]["image_seeds"])
    }
    for kind in ("image", "description"):
        predictions = [
            row for row in tables["predictions"] if row["input_kind"] == kind
        ]
        result[f"{kind}_predictions"] = len(predictions)
        for policy in ("strict", "title_aware"):
            for match_name, match in (
                ("strict", title_exact_match),
                ("normalized", title_normalized_exact_match),
            ):
                correct = 0
                for prediction in predictions:
                    image = images[prediction["image_id"]]
                    prompt = prompts[image["prompt_id"]]
                    title = items[prompt["item_id"]]["title"]
                    correct += (
                        bool(prompt_pass.get(prompt["prompt_id"]))
                        and bool(image_pass.get((image["image_id"], policy)))
                        and match(title, prediction["title"])
                    )
                result[f"{kind}_{policy}_{match_name}_correct"] = correct
    return result


def write_mapped_database(
    connection: sqlite3.Connection,
    converted: dict[str, list[dict[str, Any]]],
) -> None:
    """Apply only the declared SQL mappings inside the caller's transaction."""
    connection.execute(PROMPT_PREDICTIONS_SCHEMA.strip().rstrip(";"))
    for table, identity, columns in (
        ("stage_tasks", "task_id", ("stage", "task_key")),
        ("stage_errors", "error_id", ("stage",)),
        ("runtime_events", "runtime_event_id", ("stage",)),
        ("run_lineage", "lineage_id", ("inherited_stages",)),
    ):
        assignments = ", ".join(f"{column}=?" for column in columns)
        for row in converted[table]:
            connection.execute(
                f"UPDATE {table} SET {assignments} WHERE {identity}=?",
                (*[row[column] for column in columns], row[identity]),
            )
    connection.execute("PRAGMA user_version=12")
    database_checks(connection, 12)
    if database_rows(connection) != converted:
        fail("Converted database differs outside the declared stage-name mappings.")


def original_image_policies(
    run_id: str, snapshots: dict[str, dict[str, Any]]
) -> tuple[str, ...]:
    visited = set()
    while run_id not in visited:
        visited.add(run_id)
        config = snapshots[run_id]
        image = config["stages"].get("verification", {}).get("image")
        if image:
            return tuple(
                policy for policy in ("strict", "title_aware") if image.get(policy)
            )
        inheritance = config.get("inherit")
        if inheritance is None or "verification" not in inheritance["stages"]:
            return ()
        run_id = inheritance["source_run_id"]
    fail("Cyclic original image-verification provenance.")


def validate_in_memory(
    path: Path,
    original_tables: dict[str, list[dict[str, Any]]],
    snapshots: dict[str, dict[str, Any]],
) -> None:
    """Prove full-output and failure accounting during the read-only dry run."""
    from semantic_roundtrip.config_resolution import configured_stage_names
    from semantic_roundtrip.inheritance.dependencies import dependency_closure
    from semantic_roundtrip.inheritance.materialize import (
        MaterializationError,
        _validate_source,
    )

    original = connect(path)
    memory = sqlite3.connect(":memory:")
    memory.row_factory = sqlite3.Row
    try:
        if database_rows(original) != original_tables:
            fail("Source database changed during preflight.")
        original.backup(memory)
        memory.execute("PRAGMA foreign_keys=ON")
        memory.execute("BEGIN")
        run_id = path.parent.name
        write_mapped_database(memory, mapped_tables(original_tables, run_id, snapshots))
        config = ResolvedAppConfig.model_validate(
            convert_config(snapshots[run_id], snapshots)
        )
        available = set(configured_stage_names(config))
        if config.inherit:
            available.update(dependency_closure(config.inherit.stages))
        try:
            _validate_source(
                memory,
                config,
                tuple(sorted(available)),
                image_policies=original_image_policies(run_id, snapshots),
            )
        except MaterializationError as error:
            fail(str(error))
    finally:
        memory.close()
        original.close()


@dataclass
class JobAudit:
    directory: Path
    job_id: str
    hashes: dict[str, str]
    snapshots: dict[str, dict[str, Any]]
    changes: dict[str, dict[str, Any]]
    databases: dict[str, dict[str, list[dict[str, Any]]]]
    metrics: dict[str, dict[str, Any]]


def preflight(directory: Path) -> JobAudit:
    directory = directory.resolve(strict=True)
    hashes = file_hashes(directory)
    if any(path.startswith("migration/") for path in hashes):
        fail("This source already has a conversion record; refusing repeat migration.")
    job_connection = connect(directory / JOB_DB)
    try:
        database_checks(job_connection, 4)
        job_tables = database_rows(job_connection)
    finally:
        job_connection.close()
    metadata = job_tables["job_metadata"]
    if len(metadata) != 1 or metadata[0]["status"] != "completed":
        fail("Migration requires a fully completed job, not a running or paused job.")
    job_id = metadata[0]["job_id"]
    if directory.name != job_id:
        fail("The selected directory name and stored job ID disagree.")
    job_snapshot = read_yaml(directory / "job_snapshot.yaml")
    if job_snapshot.get("schema_version") != 4:
        fail("Only job snapshot schema 4 is supported.")
    entries = sorted(job_tables["job_entries"], key=lambda row: row["entry_index"])
    if len(entries) != len(job_snapshot["entries"]) or any(
        row["status"] != "completed" for row in entries
    ):
        fail("Every child job entry must be completed and present in the snapshot.")
    snapshots: dict[str, dict[str, Any]] = {}
    for path in (
        path for path in walk_artifact_paths(directory) if path.name == CONFIG
    ):
        config = read_yaml(path)
        if config.get("schema_version") != 10:
            fail(
                f"Expected experiment schema 10, found {config.get('schema_version')}: {path}"
            )
        run_id = path.parent.name
        if run_id in snapshots and snapshots[run_id] != config:
            fail(f"Conflicting bundled configuration snapshots: {run_id}")
        snapshots[run_id] = config
    changes: dict[str, dict[str, Any]] = {}
    for path in (
        path for path in walk_artifact_paths(directory) if path.suffix == ".yaml"
    ):
        if path.name not in {CONFIG, "config_input.yaml"}:
            continue
        original = read_yaml(path)
        if original.get("schema_version") != 10:
            fail(f"Unsupported original experiment input schema: {path}")
        parent_config = snapshots.get(path.parent.name, {})
        source_id = parent_config.get("inherit", {}).get("source_run_id")
        changes[path.relative_to(directory).as_posix()] = convert_config(
            original, snapshots, source_id
        )
    databases = {JOB_DB: job_tables}
    metrics = {}
    child_configs = []
    for index, entry in enumerate(entries):
        configured = job_snapshot["entries"][index]
        if entry["entry_index"] != index or configured["index"] != index:
            fail("Job entries do not have contiguous matching indexes.")
        child = inside(directory, entry["run_directory"])
        config = read_yaml(child / CONFIG)
        child_configs.append(config)
        connection = connect(child / RUN_DB)
        try:
            database_checks(connection, 11)
            tables = database_rows(connection)
        finally:
            connection.close()
        run_meta = tables["run_metadata"]
        if (
            len(run_meta) != 1
            or run_meta[0]["status"] != "completed"
            or run_meta[0]["pause_requested"]
        ):
            fail("Every source run must be completed without a pause request.")
        if (
            run_meta[0]["run_id"] != child.name
            or run_meta[0]["name"] != config["run"]["name"]
        ):
            fail("Run identity differs between path, database and effective snapshot.")
        if any(
            task["status"] not in {"completed", "failed"}
            for task in tables["stage_tasks"]
        ):
            fail("A source still has non-terminal work.")
        if any(event["status"] == "started" for event in tables["runtime_events"]):
            fail("A source still has an active runtime event.")
        if any(
            row["stage"] not in OLD_STAGES
            for table in ("stage_tasks", "stage_errors", "runtime_events")
            for row in tables[table]
        ):
            fail(
                "Unexpected source stage; this converter only supports the grouped-verification format."
            )
        roster = [
            (row["item_key"], row["domain"], row["title"])
            for row in sorted(
                tables["dataset_items"], key=lambda row: row["item_index"]
            )
        ]
        if roster != [
            (row["id"], row["domain"], row["title"])
            for row in config["dataset"]["items"]
        ]:
            fail("Dataset roster differs from the frozen snapshot.")
        for prompt in tables["prompts"]:
            if (
                prompt["sampling_seed"]
                != config["experiment"]["prompt_seeds"][prompt["prompt_index"]]
            ):
                fail("Stored prompt seed differs from the frozen snapshot.")
        for image in tables["images"]:
            if (
                image["seed"] not in config["experiment"]["image_seeds"]
                or not native_path(inside(child, image["path"])).is_file()
            ):
                fail("Missing image artifact or unexpected image seed.")
        manifest = json.loads((child / "manifest.json").read_text(encoding="utf-8"))
        if (
            manifest.get("manifest_schema_version") != 6
            or manifest.get("run_id") != child.name
        ):
            fail("Unexpected run manifest version or identity.")
        for group in ("prompts", "workflows"):
            for artifact in manifest["artifacts"].get(group, {}).values():
                if not native_path(inside(child, artifact)).is_file():
                    fail(f"Missing snapshotted {group} artifact: {artifact}")
        relative = (child / RUN_DB).relative_to(directory).as_posix()
        # Fully derive and validate all name mappings before any destination write.
        validate_in_memory(child / RUN_DB, tables, snapshots)
        databases[relative] = tables
        metrics[child.name] = metric_counts(tables, config)
    for filename in ("job_input.yaml", "job_snapshot.yaml"):
        document = read_yaml(directory / filename)
        if document.get("schema_version") != 4:
            fail(f"Unsupported original job format: {filename}")
        converted = copy.deepcopy(document)
        converted["schema_version"] = 5
        selected = converted.get("entries", converted.get("experiments", []))
        if len(selected) != len(child_configs):
            fail("Job input and child counts disagree.")
        for entry, config in zip(selected, child_configs, strict=True):
            inheritance = entry.get("inherit")
            if inheritance:
                source_id = config.get("inherit", {}).get("source_run_id")
                inheritance["stages"] = map_stages(
                    inheritance["stages"], verification_lanes(source_id, snapshots)
                )
        model = ResolvedJobConfig if filename == "job_snapshot.yaml" else InputJobConfig
        model.model_validate(converted)
        changes[filename] = converted
    actual_databases = {path for path in hashes if path.endswith(".sqlite")}
    if actual_databases != set(databases):
        fail("Unexpected or missing SQLite files in the selected job tree.")
    return JobAudit(directory, job_id, hashes, snapshots, changes, databases, metrics)


def backup_database(source: Path, destination: Path, expected: dict[str, Any]) -> None:
    original = connect(source)
    try:
        if database_rows(original) != expected:
            fail("Source database changed after preflight.")
        target = sqlite3.connect(destination)
        try:
            original.backup(target)
        finally:
            target.close()
    finally:
        original.close()


def write_json(path: Path, data: Any) -> None:
    with native_path(path).open("x", encoding="utf-8") as file:
        json.dump(data, file, ensure_ascii=False, indent=2)
        file.write("\n")


def apply_conversion(audit: JobAudit, output_root: Path) -> Path:
    destination = output_root / audit.job_id
    if destination.exists():
        fail(f"Destination already exists; no overwrite is allowed: {destination}")
    if output_root.is_relative_to(audit.directory) or audit.directory.is_relative_to(
        destination
    ):
        fail("Source and destination trees must not overlap.")
    if file_hashes(audit.directory) != audit.hashes:
        fail("Source files changed after preflight.")
    output_root.mkdir(parents=True, exist_ok=True)
    operation_id = uuid.uuid4().hex
    staging = output_root / f".{audit.job_id}.migrating-{operation_id}"
    shutil.copytree(
        native_path(audit.directory),
        native_path(staging),
        ignore=shutil.ignore_patterns("*.sqlite", "*-wal", "*-shm"),
        copy_function=copy_artifact,
    )
    evidence = staging / "migration" / "originals"
    native_path(evidence).mkdir(parents=True)
    try:
        for relative, expected in audit.databases.items():
            target_db = staging / relative
            backup_database(audit.directory / relative, target_db, expected)
            original_copy = evidence / relative
            native_path(original_copy.parent).mkdir(parents=True, exist_ok=True)
            copy_artifact(target_db, original_copy)
            if relative == JOB_DB:
                continue
            run_id = target_db.parent.name
            converted = mapped_tables(expected, run_id, audit.snapshots)
            target = sqlite3.connect(target_db)
            target.row_factory = sqlite3.Row
            try:
                target.execute("PRAGMA foreign_keys = ON")
                target.execute("BEGIN IMMEDIATE")
                write_mapped_database(target, converted)
                if (
                    metric_counts(database_rows(target), audit.snapshots[run_id])
                    != audit.metrics[run_id]
                ):
                    fail("Existing image/description endpoint counts changed.")
                target.commit()
            except BaseException:
                target.rollback()
                raise
            finally:
                target.close()
            write_json(
                target_db.parent / "migration_record.json",
                {
                    "converter": CONVERTER_VERSION,
                    "operation_id": operation_id,
                    "source_directory": str(audit.directory / Path(relative).parent),
                    "source_database_sha256": audit.hashes[relative],
                    "original_experiment_schema": 10,
                    "original_database_schema": 11,
                    "target_experiment_schema": 11,
                    "target_database_schema": 12,
                    "scientific_outputs_unchanged": True,
                },
            )
        for relative, document in audit.changes.items():
            target = staging / relative
            original_copy = evidence / relative
            native_path(original_copy.parent).mkdir(parents=True, exist_ok=True)
            copy_artifact(target, original_copy)
            native_path(target).write_text(
                yaml.safe_dump(document, sort_keys=False, allow_unicode=True),
                encoding="utf-8",
            )
        # Existing snapshots retain their historical source locations. Bundled
        # translated provenance makes a converted copy self-contained for reads.
        from semantic_roundtrip.config_resolution import (
            configured_stage_names,
            load_effective_config,
        )
        from semantic_roundtrip.inheritance.dependencies import dependency_closure
        from semantic_roundtrip.inheritance.materialize import _validate_source

        for relative in audit.databases:
            if relative == JOB_DB:
                continue
            child = (staging / relative).parent
            config = load_effective_config(child / CONFIG)
            available = set(configured_stage_names(config))
            if config.inherit:
                available.update(dependency_closure(config.inherit.stages))
            connection = connect(child / RUN_DB)
            try:
                _validate_source(connection, config, tuple(sorted(available)), child)
            finally:
                connection.close()
        for relative, expected_hash in audit.hashes.items():
            if (
                relative not in audit.changes
                and relative not in audit.databases
                and digest(staging / relative) != expected_hash
            ):
                fail(f"Unchanged artifact differs after copying: {relative}")
        if file_hashes(audit.directory) != audit.hashes:
            fail(
                "Original source changed during conversion; converted copy is not published."
            )
        script = Path(__file__).resolve()
        copy_artifact(script, staging / "migration" / script.name)
        write_json(
            staging / "migration" / "report.json",
            {
                "converter": CONVERTER_VERSION,
                "script_sha256": digest(script),
                "operation_id": operation_id,
                "converted_at": datetime.now(UTC).isoformat(),
                "source_job": str(audit.directory),
                "destination_job": str(destination),
                "job_id": audit.job_id,
                "source_sha256": audit.hashes,
                "changed_yaml": sorted(audit.changes),
                "database_schemas": {"run": "11->12", "job": "4->4"},
                "metrics_before_and_after": audit.metrics,
                "unchanged_outputs_and_artifacts_validated": True,
                "verification_runtime_mapping": "image only; no duplicated events or synthetic CPU time",
                "historical_source_paths_preserved": True,
                "destination_sha256_before_report": file_hashes(staging),
            },
        )
        if destination.exists():
            fail("Destination appeared during conversion; refusing overwrite.")
        staging.rename(destination)
    except BaseException:
        # Leave only a visibly incomplete, uniquely named staging directory for
        # diagnosis. Never publish it, delete source data, or reset run statuses.
        print(
            f"Conversion failed; incomplete staging copy retained at {staging}",
            file=sys.stderr,
        )
        raise
    return destination


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--source-job",
        type=Path,
        action="append",
        required=True,
        help="Explicit completed job directory; repeat for multiple jobs.",
    )
    parser.add_argument(
        "--destination-root",
        "--output-root",
        dest="output_root",
        type=Path,
        required=True,
        help="Separate parent for new converted job copies.",
    )
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument(
        "--dry-run",
        action="store_true",
        help="Read-only validation (also the default).",
    )
    mode.add_argument(
        "--apply",
        action="store_true",
        help="Create and validate new copies; originals are never edited.",
    )
    args = parser.parse_args()
    output_root = args.output_root.expanduser().resolve()
    audits = [preflight(path.expanduser()) for path in args.source_job]
    if len({audit.job_id for audit in audits}) != len(audits):
        fail("Every selected job must have a unique ID.")
    for audit in audits:
        if (output_root / audit.job_id).exists() or output_root.is_relative_to(
            audit.directory
        ):
            fail(
                "Destination exists or overlaps a source; nothing will be overwritten."
            )
    result = {
        "mode": "apply" if args.apply else "dry-run",
        "converter": CONVERTER_VERSION,
        "jobs": [
            {
                "job_id": audit.job_id,
                "source": str(audit.directory),
                "destination": str(output_root / audit.job_id),
                "runs": len(audit.metrics),
                "metrics": audit.metrics,
            }
            for audit in audits
        ],
    }
    if args.apply:
        for audit in audits:
            apply_conversion(audit, output_root)
    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    try:
        main()
    except (ValueError, OSError, sqlite3.Error) as error:
        print(f"Migration refused: {error}", file=sys.stderr)
        raise SystemExit(1) from error
