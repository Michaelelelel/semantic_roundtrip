"""Resolve input profiles into self-contained run configurations."""

from pathlib import Path
from typing import Any

import yaml

from semantic_roundtrip.config import (
    BackendProfile,
    DatasetProfile,
    ImageVerificationPolicy,
    InputAppConfig,
    PipelineStageName,
    ResolvedAppConfig,
    ResolvedBackend,
    ResolvedDatasetConfig,
    ResolvedRunInheritance,
    StageAdapterConfig,
    StageConfig,
    StageName,
)
from semantic_roundtrip.inheritance.dependencies import dependency_closure

STAGE_NAMES: tuple[StageName, ...] = (
    "illustratability_rating",
    "prompt_generation",
    "image_generation",
    "verification",
    "title_guessing_direct",
    "image_description",
    "title_guessing_from_description",
)
IMAGE_VERIFICATION_POLICIES: tuple[ImageVerificationPolicy, ...] = (
    "strict",
    "title_aware",
)


def _read_yaml(path: Path) -> Any:
    with path.open("r", encoding="utf-8") as file:
        return yaml.safe_load(file)


def _load_backend_profile(path: Path) -> BackendProfile:
    return BackendProfile.model_validate(_read_yaml(path))


def _load_dataset_profile(path: Path) -> DatasetProfile:
    return DatasetProfile.model_validate(_read_yaml(path))


def get_stage_config(
    config: ResolvedAppConfig,
    stage_name: StageName,
) -> StageConfig | None:
    """Return the configuration represented by one executable stage name."""
    if stage_name == "title_guessing_direct":
        return (
            None
            if config.stages.title_guessing is None
            else config.stages.title_guessing.direct
        )
    if stage_name == "title_guessing_from_description":
        return (
            None
            if config.stages.title_guessing is None
            else config.stages.title_guessing.from_description
        )
    return getattr(config.stages, stage_name)


def configured_stage_names(config: ResolvedAppConfig) -> tuple[StageName, ...]:
    """Return only stages that this run executes locally."""
    return tuple(
        stage_name
        for stage_name in STAGE_NAMES
        if get_stage_config(config, stage_name) is not None
    )


def configured_image_verification_policies(
    config: ResolvedAppConfig,
) -> tuple[ImageVerificationPolicy, ...]:
    """Return image checks configured for local execution, in stable order."""
    verification = config.stages.verification
    if verification is None or verification.image is None:
        return ()
    return tuple(
        policy
        for policy in IMAGE_VERIFICATION_POLICIES
        if getattr(verification.image, policy) is not None
    )


def resolve_stage_adapter(
    config: ResolvedAppConfig,
    stage_name: StageName,
    *,
    image_verification_policy: ImageVerificationPolicy | None = None,
) -> StageAdapterConfig:
    """Merge one stage's backend settings and scientific parameters."""
    stage = get_stage_config(config, stage_name)
    if stage is None:
        raise ValueError(f"Optional stage '{stage_name}' is not configured.")

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
    if stage_name == "verification":
        if image_verification_policy is None:
            raise ValueError(
                "Resolving verification requires an explicit image policy."
            )
        image = config.stages.verification.image
        check = None if image is None else getattr(image, image_verification_policy)
        if check is None:
            raise ValueError(
                f"Image-verification policy '{image_verification_policy}' is not "
                "configured."
            )
        template_path = check.template_path
    elif image_verification_policy is not None:
        raise ValueError(
            "image_verification_policy is valid only for the verification stage."
        )
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
        if get_stage_config(config, stage_name) is None:
            continue
        if stage_name == "verification":
            verification = config.stages.verification
            assert verification is not None
            if verification.backend not in config.backends:
                raise ValueError(
                    "Verification references unknown backend "
                    f"'{verification.backend}'."
                )
            for policy in configured_image_verification_policies(config):
                resolve_stage_adapter(
                    config,
                    stage_name,
                    image_verification_policy=policy,
                )
        else:
            resolve_stage_adapter(
                config,
                stage_name,
            )

    local_stages = set(configured_stage_names(config))
    imported_stages: set[StageName] = set()
    if config.inherit is not None:
        imported_stages.update(dependency_closure(config.inherit.stages))
    overlap = local_stages & imported_stages
    if overlap:
        names = ", ".join(sorted(overlap))
        raise ValueError(
            f"Stages cannot be both imported and executed locally: {names}."
        )

    available = local_stages | imported_stages
    for stage_name in local_stages:
        missing = set(dependency_closure((stage_name,))) - available
        if missing:
            names = ", ".join(sorted(missing))
            raise ValueError(
                f"Local stage '{stage_name}' is missing dependencies: {names}."
            )

    if "prompt_generation" in available and not config.experiment.prompt_seeds:
        raise ValueError(
            "Prompt generation requires at least one configured prompt seed."
        )
    image_dependent = available & {
        "image_generation",
        "verification",
        "title_guessing_direct",
        "image_description",
        "title_guessing_from_description",
    }
    if image_dependent and not config.experiment.image_seeds:
        raise ValueError(
            "Image-dependent stages require at least one configured image seed."
        )


def _resolve_dataset(
    input_config: InputAppConfig,
    base_directory: Path,
) -> ResolvedDatasetConfig:
    dataset = input_config.dataset
    if dataset is None:
        raise ValueError("A root experiment requires a configured dataset.")
    if dataset.profile is None:
        if dataset.dataset_id is None or dataset.items is None:
            raise ValueError("Inline dataset was not fully configured.")
        return ResolvedDatasetConfig(
            dataset_id=dataset.dataset_id,
            items=dataset.items,
        )

    profile_path = dataset.profile
    if not profile_path.is_absolute():
        profile_path = (base_directory / profile_path).resolve()
    profile = _load_dataset_profile(profile_path)
    return ResolvedDatasetConfig(
        dataset_id=profile.dataset_id,
        source_profile=dataset.profile,
        items=profile.items,
    )


def _resolve_standalone_inheritance(
    input_config: InputAppConfig,
    base_directory: Path,
) -> tuple[ResolvedDatasetConfig, ResolvedRunInheritance, ResolvedAppConfig]:
    if input_config.inherit is None:
        raise ValueError("This experiment has no standalone inheritance reference.")

    from semantic_roundtrip.inheritance.source import load_source_run

    source_path = input_config.inherit.from_run
    if not source_path.is_absolute():
        source_path = (base_directory / source_path).resolve()
    source = load_source_run(source_path)
    inheritance = ResolvedRunInheritance(
        source_kind="from_run",
        source_run=source.directory,
        source_run_id=source.run_id,
        stages=input_config.inherit.stages,
    )
    return source.config.dataset, inheritance, source.config


def _validate_source_compatibility(
    config: ResolvedAppConfig,
    source_config: ResolvedAppConfig | None,
) -> None:
    if config.inherit is None or source_config is None:
        return
    imported = set(dependency_closure(config.inherit.stages))
    if "prompt_generation" in imported and (
        config.experiment.prompt_seeds != source_config.experiment.prompt_seeds
    ):
        raise ValueError(
            "Inherited prompts require the same prompt_seeds as the source run."
        )
    if "image_generation" in imported and (
        config.experiment.image_seeds != source_config.experiment.image_seeds
    ):
        raise ValueError(
            "Inherited images require the same image_seeds as the source run."
        )


def load_input_config(
    path: Path,
    *,
    inherited_dataset: ResolvedDatasetConfig | None = None,
    resolved_inheritance: ResolvedRunInheritance | None = None,
    source_config: ResolvedAppConfig | None = None,
) -> ResolvedAppConfig:
    """Load an experiment and resolve all referenced profiles."""
    input_config = InputAppConfig.model_validate(_read_yaml(path))
    path = path.resolve()
    base_directory = path.parent
    if input_config.inherit is not None and resolved_inheritance is not None:
        raise ValueError(
            "Experiment inheritance and job-entry inheritance cannot be combined."
        )

    if input_config.inherit is not None:
        inherited_dataset, resolved_inheritance, source_config = (
            _resolve_standalone_inheritance(input_config, base_directory)
        )

    if input_config.dataset is not None:
        if inherited_dataset is not None or resolved_inheritance is not None:
            raise ValueError(
                "A job-derived experiment must omit its own dataset and inheritance."
            )
        resolved_dataset = _resolve_dataset(input_config, base_directory)
    else:
        if inherited_dataset is None or resolved_inheritance is None:
            raise ValueError(
                "An experiment without a dataset requires one resolved source run."
            )
        resolved_dataset = inherited_dataset
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
    raw_resolved["dataset"] = resolved_dataset
    raw_resolved["inherit"] = resolved_inheritance
    raw_resolved["backends"] = resolved_backends
    resolved_config = ResolvedAppConfig.model_validate(raw_resolved)
    _validate_resolved_config(resolved_config)
    _validate_source_compatibility(resolved_config, source_config)
    return resolved_config


def load_effective_config(path: Path) -> ResolvedAppConfig:
    """Load a self-contained snapshot without reopening source profiles."""
    config = ResolvedAppConfig.model_validate(_read_yaml(path))
    _validate_resolved_config(config)
    return config


def expected_stage_outputs(config: ResolvedAppConfig) -> dict[PipelineStageName, int]:
    """Calculate outputs expected only from stages executed by this run."""
    prompt_count = len(config.dataset.items) * len(config.experiment.prompt_seeds)
    image_count = prompt_count * len(config.experiment.image_seeds)
    expected: dict[PipelineStageName, int] = {}

    counts: dict[StageName, int] = {
        "illustratability_rating": len(config.dataset.items),
        "prompt_generation": prompt_count,
        "image_generation": image_count,
        "verification": (
            (prompt_count if config.stages.verification.prompt is not None else 0)
            + image_count * len(configured_image_verification_policies(config))
            if config.stages.verification is not None
            else 0
        ),
        "title_guessing_direct": image_count,
        "image_description": image_count,
        "title_guessing_from_description": image_count,
    }
    for stage_name in configured_stage_names(config):
        expected[stage_name] = counts[stage_name]
    return expected


def expected_output_count(config: ResolvedAppConfig, stage_name: StageName) -> int:
    """Return the theoretical output count for any one pipeline stage."""
    prompt_count = len(config.dataset.items) * len(config.experiment.prompt_seeds)
    image_count = prompt_count * len(config.experiment.image_seeds)
    if stage_name == "illustratability_rating":
        return len(config.dataset.items)
    if stage_name == "prompt_generation":
        return prompt_count
    if stage_name == "verification":
        verification = config.stages.verification
        if verification is None:
            return 0
        return (
            (prompt_count if verification.prompt is not None else 0)
            + image_count * len(configured_image_verification_policies(config))
        )
    return image_count
