"""Persistence of input and effective experiment configurations."""

from pathlib import Path
from shutil import copy2

import yaml

from semantic_roundtrip.config import ResolvedAppConfig
from semantic_roundtrip.prompting import LoadedPromptProfile

INPUT_CONFIG_FILENAME = "config_input.yaml"
EFFECTIVE_CONFIG_FILENAME = "config_snapshot.yaml"
PROMPT_PROFILE_FILENAME = "prompt_profile.yaml"
ILLUSTRATABILITY_PROMPT_PROFILE_FILENAME = "illustratability_prompt_profile.yaml"
STRICT_IMAGE_VERIFICATION_PROMPT_FILENAME = "verification_image_strict_profile.yaml"
TITLE_AWARE_IMAGE_VERIFICATION_PROMPT_FILENAME = (
    "verification_image_title_aware_profile.yaml"
)
IMAGE_DESCRIPTION_PROMPT_FILENAME = "image_description_profile.yaml"
DIRECT_TITLE_GUESSING_PROMPT_FILENAME = "title_guessing_direct_profile.yaml"
DESCRIPTION_TITLE_GUESSING_PROMPT_FILENAME = (
    "title_guessing_from_description_profile.yaml"
)
PROMPT_TITLE_GUESSING_PROMPT_FILENAME = "title_guessing_from_prompt_profile.yaml"


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
    *,
    loaded_illustratability_profile: LoadedPromptProfile | None = None,
) -> dict[str, Path]:
    """Copy every prompt profile referenced by this experiment."""
    snapshots: dict[str, Path] = {}
    if loaded_illustratability_profile is not None:
        snapshot_path = run_directory / ILLUSTRATABILITY_PROMPT_PROFILE_FILENAME
        with snapshot_path.open("xb") as file:
            file.write(loaded_illustratability_profile.source_bytes)
        snapshots["illustratability_rating"] = snapshot_path
    if loaded_profile is not None:
        snapshots["prompt_generation"] = create_prompt_profile_snapshot(
            loaded_profile,
            run_directory,
        )
    title_guessing = config.stages.title_guessing
    configured_prompts: dict[str, tuple[Path | None, str]] = {
        "image_description": (
            (
                None
                if config.stages.image_description is None
                else config.stages.image_description.prompt_profile
            ),
            IMAGE_DESCRIPTION_PROMPT_FILENAME,
        ),
        "title_guessing_direct": (
            (
                None
                if title_guessing is None or title_guessing.direct is None
                else title_guessing.direct.prompt_profile
            ),
            DIRECT_TITLE_GUESSING_PROMPT_FILENAME,
        ),
        "title_guessing_from_description": (
            (
                None
                if title_guessing is None or title_guessing.from_description is None
                else title_guessing.from_description.prompt_profile
            ),
            DESCRIPTION_TITLE_GUESSING_PROMPT_FILENAME,
        ),
        "title_guessing_from_prompt": (
            (
                None
                if title_guessing is None or title_guessing.from_prompt is None
                else title_guessing.from_prompt.prompt_profile
            ),
            PROMPT_TITLE_GUESSING_PROMPT_FILENAME,
        ),
    }
    verification = config.stages.verification_image
    if verification is not None:
        if verification.policies.strict is not None:
            configured_prompts["verification_image_strict"] = (
                verification.policies.strict.prompt_profile,
                STRICT_IMAGE_VERIFICATION_PROMPT_FILENAME,
            )
        if verification.policies.title_aware is not None:
            configured_prompts["verification_image_title_aware"] = (
                verification.policies.title_aware.prompt_profile,
                TITLE_AWARE_IMAGE_VERIFICATION_PROMPT_FILENAME,
            )
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
    """Use copied prompt profiles when resuming a run."""
    illustratability_rating = config.stages.illustratability_rating
    illustratability_path = run_directory / ILLUSTRATABILITY_PROMPT_PROFILE_FILENAME
    if illustratability_rating is not None and illustratability_path.is_file():
        illustratability_rating = illustratability_rating.model_copy(
            update={"prompt_profile": illustratability_path}
        )

    prompt_generation = config.stages.prompt_generation
    prompt_generation_path = run_directory / PROMPT_PROFILE_FILENAME
    if prompt_generation is not None and prompt_generation_path.is_file():
        prompt_generation = prompt_generation.model_copy(
            update={"prompt_profile": prompt_generation_path}
        )

    verification = config.stages.verification_image
    if verification is not None:
        image_updates = {}
        strict_path = run_directory / STRICT_IMAGE_VERIFICATION_PROMPT_FILENAME
        if verification.policies.strict is not None and strict_path.is_file():
            image_updates["strict"] = verification.policies.strict.model_copy(
                update={"prompt_profile": strict_path}
            )
        title_aware_path = (
            run_directory / TITLE_AWARE_IMAGE_VERIFICATION_PROMPT_FILENAME
        )
        if verification.policies.title_aware is not None and title_aware_path.is_file():
            image_updates["title_aware"] = verification.policies.title_aware.model_copy(
                update={"prompt_profile": title_aware_path}
            )
        if image_updates:
            verification = verification.model_copy(
                update={
                    "policies": verification.policies.model_copy(update=image_updates)
                }
            )

    image_description = config.stages.image_description
    image_description_path = run_directory / IMAGE_DESCRIPTION_PROMPT_FILENAME
    if image_description is not None and image_description_path.is_file():
        image_description = image_description.model_copy(
            update={"prompt_profile": image_description_path}
        )

    title_guessing = config.stages.title_guessing
    direct_title_guessing = None if title_guessing is None else title_guessing.direct
    direct_title_guessing_path = run_directory / DIRECT_TITLE_GUESSING_PROMPT_FILENAME
    if direct_title_guessing is not None and direct_title_guessing_path.is_file():
        direct_title_guessing = direct_title_guessing.model_copy(
            update={"prompt_profile": direct_title_guessing_path}
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
            update={"prompt_profile": description_title_guessing_path}
        )

    prompt_title_guessing = (
        None if title_guessing is None else title_guessing.from_prompt
    )
    prompt_title_guessing_path = run_directory / PROMPT_TITLE_GUESSING_PROMPT_FILENAME
    if prompt_title_guessing is not None and prompt_title_guessing_path.is_file():
        prompt_title_guessing = prompt_title_guessing.model_copy(
            update={"prompt_profile": prompt_title_guessing_path}
        )

    if title_guessing is not None:
        title_guessing = title_guessing.model_copy(
            update={
                "direct": direct_title_guessing,
                "from_description": description_title_guessing,
                "from_prompt": prompt_title_guessing,
            }
        )

    stages = config.stages.model_copy(
        update={
            "illustratability_rating": illustratability_rating,
            "prompt_generation": prompt_generation,
            "verification_image": verification,
            "image_description": image_description,
            "title_guessing": title_guessing,
        }
    )

    return config.model_copy(update={"stages": stages})
