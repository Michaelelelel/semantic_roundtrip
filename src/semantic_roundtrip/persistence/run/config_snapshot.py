"""Persistence of input and effective experiment configurations."""

from pathlib import Path
from shutil import copy2

import yaml

from semantic_roundtrip.config import ResolvedAppConfig
from semantic_roundtrip.prompting import LoadedPromptProfile

INPUT_CONFIG_FILENAME = "config_input.yaml"
EFFECTIVE_CONFIG_FILENAME = "config_snapshot.yaml"
PROMPT_PROFILE_FILENAME = "prompt_profile.yaml"
VERIFICATION_PROMPT_FILENAME = "verification_prompt.txt"
IMAGE_DESCRIPTION_PROMPT_FILENAME = "image_description_prompt.txt"
DIRECT_TITLE_GUESSING_PROMPT_FILENAME = "title_guessing_direct_prompt.txt"
DESCRIPTION_TITLE_GUESSING_PROMPT_FILENAME = (
    "title_guessing_from_description_prompt.txt"
)


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


def create_prompt_snapshots(
    config: ResolvedAppConfig,
    loaded_profile: LoadedPromptProfile | None,
    run_directory: Path,
) -> dict[str, Path]:
    """Copy every prompt file referenced by this experiment."""
    snapshots: dict[str, Path] = {}
    if loaded_profile is not None:
        snapshots["prompt_generation"] = create_prompt_profile_snapshot(
            loaded_profile,
            run_directory,
        )
    title_guessing = config.stages.title_guessing
    configured_prompts = {
        "verification": (
            (
                None
                if config.stages.verification is None
                else config.stages.verification.template_path
            ),
            VERIFICATION_PROMPT_FILENAME,
        ),
        "image_description": (
            (
                None
                if config.stages.image_description is None
                else config.stages.image_description.template_path
            ),
            IMAGE_DESCRIPTION_PROMPT_FILENAME,
        ),
        "title_guessing_direct": (
            (
                None
                if title_guessing is None or title_guessing.direct is None
                else title_guessing.direct.template_path
            ),
            DIRECT_TITLE_GUESSING_PROMPT_FILENAME,
        ),
        "title_guessing_from_description": (
            (
                None
                if title_guessing is None or title_guessing.from_description is None
                else title_guessing.from_description.template_path
            ),
            DESCRIPTION_TITLE_GUESSING_PROMPT_FILENAME,
        ),
    }
    for name, (source_path, filename) in configured_prompts.items():
        if source_path is None:
            continue
        snapshot_path = run_directory / filename
        copy2(source_path, snapshot_path)
        snapshots[name] = snapshot_path

    return snapshots


def use_prompt_snapshots(
    config: ResolvedAppConfig,
    run_directory: Path,
) -> ResolvedAppConfig:
    """Use copied prompt files when resuming a new-format run."""
    prompt_generation = config.stages.prompt_generation
    prompt_generation_path = run_directory / PROMPT_PROFILE_FILENAME
    if prompt_generation is not None and prompt_generation_path.is_file():
        prompt_generation = prompt_generation.model_copy(
            update={"prompt_profile": prompt_generation_path}
        )

    verification = config.stages.verification
    verification_path = run_directory / VERIFICATION_PROMPT_FILENAME
    if verification is not None and verification_path.is_file():
        verification = verification.model_copy(
            update={"template_path": verification_path}
        )

    image_description = config.stages.image_description
    image_description_path = run_directory / IMAGE_DESCRIPTION_PROMPT_FILENAME
    if image_description is not None and image_description_path.is_file():
        image_description = image_description.model_copy(
            update={"template_path": image_description_path}
        )

    title_guessing = config.stages.title_guessing
    direct_title_guessing = None if title_guessing is None else title_guessing.direct
    direct_title_guessing_path = run_directory / DIRECT_TITLE_GUESSING_PROMPT_FILENAME
    if direct_title_guessing is not None and direct_title_guessing_path.is_file():
        direct_title_guessing = direct_title_guessing.model_copy(
            update={"template_path": direct_title_guessing_path}
        )

    description_title_guessing = (
        None if title_guessing is None else title_guessing.from_description
    )
    description_title_guessing_path = (
        run_directory / DESCRIPTION_TITLE_GUESSING_PROMPT_FILENAME
    )
    if (
        description_title_guessing is not None
        and description_title_guessing_path.is_file()
    ):
        description_title_guessing = description_title_guessing.model_copy(
            update={"template_path": description_title_guessing_path}
        )

    if title_guessing is not None:
        title_guessing = title_guessing.model_copy(
            update={
                "direct": direct_title_guessing,
                "from_description": description_title_guessing,
            }
        )

    stages = config.stages.model_copy(
        update={
            "prompt_generation": prompt_generation,
            "verification": verification,
            "image_description": image_description,
            "title_guessing": title_guessing,
        }
    )

    return config.model_copy(update={"stages": stages})
