"""Resolve input backend profiles into self-contained run configurations."""

from pathlib import Path
from typing import Any

import yaml

from semantic_roundtrip.config import (
    BackendProfile,
    InputAppConfig,
    ResolvedAppConfig,
    ResolvedBackend,
    StageAdapterConfig,
    StageName,
)


STAGE_NAMES: tuple[StageName, ...] = (
    "prompt_generation",
    "image_generation",
    "verification",
    "title_guessing",
)


def _read_yaml(path: Path) -> Any:
    with path.open("r", encoding="utf-8") as file:
        return yaml.safe_load(file)


def _load_backend_profile(path: Path) -> BackendProfile:
    return BackendProfile.model_validate(_read_yaml(path))


def resolve_stage_adapter(
    config: ResolvedAppConfig,
    stage_name: StageName,
) -> StageAdapterConfig:
    """Merge one stage's backend settings and scientific parameters."""
    stage = getattr(config.stages, stage_name)
    backend = config.backends.get(stage.backend)
    if backend is None:
        raise ValueError(
            f"Stage '{stage_name}' references unknown backend '{stage.backend}'."
        )

    duplicate_settings = set(backend.settings) & set(stage.parameters)
    if duplicate_settings:
        names = ", ".join(sorted(duplicate_settings))
        raise ValueError(
            f"Backend '{stage.backend}' and stage '{stage_name}' both configure: "
            f"{names}. Keep each setting in one place."
        )

    settings = backend.settings | stage.parameters
    template_path = getattr(stage, "template_path", None)
    if template_path is not None:
        if "template_path" in settings:
            raise ValueError(
                f"Stage '{stage_name}' must configure template_path with its "
                "dedicated field, not in backend settings or parameters."
            )
        settings["template_path"] = template_path

    return StageAdapterConfig(
        adapter=backend.adapter,
        settings=settings,
    )


def _validate_resolved_config(config: ResolvedAppConfig) -> None:
    for stage_name in STAGE_NAMES:
        resolve_stage_adapter(config, stage_name)


def load_input_config(path: Path) -> ResolvedAppConfig:
    """Load an experiment and resolve every referenced backend profile."""
    input_config = InputAppConfig.model_validate(_read_yaml(path))
    base_directory = path.resolve().parent
    profile_cache: dict[Path, BackendProfile] = {}
    resolved_backends: dict[str, ResolvedBackend] = {}

    for alias, reference in input_config.backends.items():
        profile_path = reference.profile
        if not profile_path.is_absolute():
            profile_path = (base_directory / profile_path).resolve()

        profile = profile_cache.get(profile_path)
        if profile is None:
            profile = _load_backend_profile(profile_path)
            profile_cache[profile_path] = profile

        resolved_backends[alias] = ResolvedBackend(
            source_profile=reference.profile,
            adapter=profile.adapter,
            settings=profile.settings,
            runtime=profile.runtime,
        )

    raw_resolved = input_config.model_dump(mode="python")
    raw_resolved["configuration_kind"] = "effective"
    raw_resolved["backends"] = resolved_backends
    resolved_config = ResolvedAppConfig.model_validate(raw_resolved)
    _validate_resolved_config(resolved_config)
    return resolved_config


def load_effective_config(path: Path) -> ResolvedAppConfig:
    """Load a self-contained snapshot without reopening backend profiles."""
    config = ResolvedAppConfig.model_validate(_read_yaml(path))
    _validate_resolved_config(config)
    return config
