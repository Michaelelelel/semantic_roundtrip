"""Persistence of input and effective experiment configurations."""

from pathlib import Path
import re
from shutil import copy2

import yaml

from semantic_roundtrip.config import ResolvedAppConfig
from semantic_roundtrip.prompting import LoadedPromptProfile


INPUT_CONFIG_FILENAME = "config_input.yaml"
EFFECTIVE_CONFIG_FILENAME = "config_snapshot.yaml"
PROMPT_PROFILE_FILENAME = "prompt_profile.yaml"
VERIFICATION_PROMPT_FILENAME = "verification_prompt.txt"
TITLE_GUESSING_PROMPT_FILENAME = "title_guessing_prompt.txt"


def create_input_config_snapshot(
    config_path: Path,
    run_directory: Path,
) -> Path:
    """Copy the exact input configuration into the run directory."""
    snapshot_path = run_directory / INPUT_CONFIG_FILENAME

    if snapshot_path.exists():
        raise FileExistsError(
            f"Input configuration snapshot already exists: {snapshot_path}"
        )

    copy2(config_path, snapshot_path)
    return snapshot_path


def create_effective_config_snapshot(
    config: ResolvedAppConfig,
    run_directory: Path,
) -> Path:
    """Write the validated configuration, including default values."""
    snapshot_path = run_directory / EFFECTIVE_CONFIG_FILENAME

    with snapshot_path.open("x", encoding="utf-8") as file:
        yaml.safe_dump(
            config.model_dump(mode="json", exclude_none=True),
            file,
            sort_keys=False,
            allow_unicode=True,
        )

    return snapshot_path


def create_prompt_profile_snapshot(
    loaded_profile: LoadedPromptProfile,
    run_directory: Path,
) -> Path:
    """Write the exact validated prompt profile used by the run."""
    snapshot_path = run_directory / PROMPT_PROFILE_FILENAME

    with snapshot_path.open("xb") as file:
        file.write(loaded_profile.source_bytes)

    return snapshot_path


def _chat_template_filename(alias: str, source_path: Path) -> str:
    safe_alias = re.sub(r"[^a-zA-Z0-9_-]+", "-", alias).strip("-")
    suffix = source_path.suffix or ".txt"
    return f"{safe_alias or 'backend'}_chat_template{suffix}"


def create_prompt_snapshots(
    config: ResolvedAppConfig,
    loaded_profile: LoadedPromptProfile,
    run_directory: Path,
) -> dict[str, Path]:
    """Copy every prompt file referenced by this experiment."""
    snapshots = {
        "prompt_generation": create_prompt_profile_snapshot(
            loaded_profile,
            run_directory,
        )
    }
    configured_prompts = {
        "verification": (
            config.stages.verification.template_path,
            VERIFICATION_PROMPT_FILENAME,
        ),
        "title_guessing": (
            config.stages.title_guessing.template_path,
            TITLE_GUESSING_PROMPT_FILENAME,
        ),
    }
    for name, (source_path, filename) in configured_prompts.items():
        if source_path is None:
            continue
        snapshot_path = run_directory / filename
        copy2(source_path, snapshot_path)
        snapshots[name] = snapshot_path

    for alias, backend in config.backends.items():
        configured_path = backend.settings.get("chat_template_path")
        if configured_path is None:
            continue
        source_path = Path(configured_path)
        snapshot_path = run_directory / _chat_template_filename(alias, source_path)
        copy2(source_path, snapshot_path)
        snapshots[f"{alias}_chat_template"] = snapshot_path

    return snapshots


def use_prompt_snapshots(
    config: ResolvedAppConfig,
    run_directory: Path,
) -> ResolvedAppConfig:
    """Use copied prompt files when resuming a new-format run."""
    prompt_generation = config.stages.prompt_generation
    prompt_generation_path = run_directory / PROMPT_PROFILE_FILENAME
    if prompt_generation_path.is_file():
        prompt_generation = prompt_generation.model_copy(
            update={"prompt_profile": prompt_generation_path}
        )

    verification = config.stages.verification
    verification_path = run_directory / VERIFICATION_PROMPT_FILENAME
    if verification_path.is_file():
        verification = verification.model_copy(
            update={"template_path": verification_path}
        )

    title_guessing = config.stages.title_guessing
    title_guessing_path = run_directory / TITLE_GUESSING_PROMPT_FILENAME
    if title_guessing_path.is_file():
        title_guessing = title_guessing.model_copy(
            update={"template_path": title_guessing_path}
        )

    stages = config.stages.model_copy(
        update={
            "prompt_generation": prompt_generation,
            "verification": verification,
            "title_guessing": title_guessing,
        }
    )

    backends = dict(config.backends)
    for alias, backend in backends.items():
        configured_path = backend.settings.get("chat_template_path")
        if configured_path is None:
            continue
        snapshot_path = run_directory / _chat_template_filename(
            alias,
            Path(configured_path),
        )
        if snapshot_path.is_file():
            settings = dict(backend.settings)
            settings["chat_template_path"] = snapshot_path
            backends[alias] = backend.model_copy(update={"settings": settings})

    return config.model_copy(
        update={
            "stages": stages,
            "backends": backends,
        }
    )
