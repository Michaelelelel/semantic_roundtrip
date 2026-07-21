"""Creation of a human-readable run manifest."""

import json
from pathlib import Path

from semantic_roundtrip.persistence.run_manager import RunContext
from semantic_roundtrip.prompting import LoadedPromptProfile


MANIFEST_FILENAME = "manifest.json"
MANIFEST_SCHEMA_VERSION = 2


def _relative_path(path: Path, run_directory: Path) -> str:
    return path.relative_to(run_directory).as_posix()


def create_manifest(
    run_context: RunContext,
    run_name: str,
    input_config_path: Path,
    effective_config_path: Path,
    database_path: Path,
    images_directory: Path,
    prompt_profile_path: Path,
    loaded_prompt_profile: LoadedPromptProfile,
) -> Path:
    """Write the static identity and artifact index for a run."""
    manifest_path = run_context.directory / MANIFEST_FILENAME
    manifest = {
        "manifest_schema_version": MANIFEST_SCHEMA_VERSION,
        "run_id": run_context.run_id,
        "run_name": run_name,
        "created_at": run_context.created_at.isoformat(),
        "prompt_profile": {
            "path": _relative_path(
                prompt_profile_path,
                run_context.directory,
            ),
            "profile_id": loaded_prompt_profile.profile.profile_id,
            "version": loaded_prompt_profile.profile.version,
        },
        "artifacts": {
            "input_config": _relative_path(
                input_config_path,
                run_context.directory,
            ),
            "effective_config": _relative_path(
                effective_config_path,
                run_context.directory,
            ),
            "database": _relative_path(
                database_path,
                run_context.directory,
            ),
            "images": _relative_path(
                images_directory,
                run_context.directory,
            ),
        },
    }

    with manifest_path.open("x", encoding="utf-8") as file:
        json.dump(
            manifest,
            file,
            indent=2,
            ensure_ascii=False,
        )
        file.write("\n")

    return manifest_path
