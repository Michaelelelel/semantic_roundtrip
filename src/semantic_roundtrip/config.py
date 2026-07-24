"""Validated input and effective experiment configuration models."""

from pathlib import Path
from typing import Annotated, Any, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator


class ConfigModel(BaseModel):
    """Reject unknown configuration keys instead of silently ignoring typos."""

    model_config = ConfigDict(extra="forbid")


class RunConfig(ConfigModel):
    name: str = Field(min_length=1)
    output_directory: Path = Path("runs")


class DatasetItem(ConfigModel):
    domain: str
    title: str


class DatasetConfig(ConfigModel):
    items: list[DatasetItem] = Field(min_length=1)


class ExperimentConfig(ConfigModel):
    prompts_per_title: int = Field(gt=0)
    prompt_seed: int = Field(default=0, ge=0)
    image_seeds: list[Annotated[int, Field(ge=0)]] = Field(min_length=1)
    retry_limit: int = Field(ge=0)

    @field_validator("image_seeds")
    @classmethod
    def require_unique_image_seeds(cls, seeds: list[int]) -> list[int]:
        if len(seeds) != len(set(seeds)):
            raise ValueError("Every configured image seed must be unique.")
        return seeds


BackendAlias = Annotated[str, Field(min_length=1)]
StageName = Literal[
    "prompt_generation",
    "image_generation",
    "verification",
    "title_guessing",
]


class BackendReference(ConfigModel):
    """Reference a reusable backend profile from an input configuration."""

    profile: Path


class RuntimeSpec(ConfigModel):
    """Describe runtime ownership without coupling it to inference adapters."""

    controller: Literal[
        "none",
        "llama_cpp_router",
        "comfyui",
        "managed_api",
    ]
    control_url: str | None = None
    resource_group: str = Field(min_length=1)


class BackendProfile(ConfigModel):
    """Reusable details for calling one model or inference service."""

    schema_version: Literal[1]
    adapter: str = Field(min_length=1)
    settings: dict[str, Any] = Field(default_factory=dict)
    runtime: RuntimeSpec


class ResolvedBackend(ConfigModel):
    """A self-contained backend with its source retained only as provenance."""

    source_profile: Path
    adapter: str = Field(min_length=1)
    settings: dict[str, Any] = Field(default_factory=dict)
    runtime: RuntimeSpec


class StageConfig(ConfigModel):
    """Settings shared by all experiment stages."""

    backend: BackendAlias
    parameters: dict[str, Any] = Field(default_factory=dict)


class PromptGenerationStage(StageConfig):
    prompt_profile: Path


class ImageGenerationStage(StageConfig):
    pass


class VerificationStage(StageConfig):
    template_path: Path | None = None


class TitleGuessingStage(StageConfig):
    template_path: Path | None = None


class StagesConfig(ConfigModel):
    prompt_generation: PromptGenerationStage
    image_generation: ImageGenerationStage
    verification: VerificationStage
    title_guessing: TitleGuessingStage


class EvaluationConfig(ConfigModel):
    failed_verification: Literal["count_as_failure", "exclude"]


class InputAppConfig(ConfigModel):
    """Human-maintained experiment configuration with backend references."""

    schema_version: Literal[1]
    run: RunConfig
    dataset: DatasetConfig
    experiment: ExperimentConfig
    backends: dict[BackendAlias, BackendReference] = Field(min_length=1)
    stages: StagesConfig
    evaluation: EvaluationConfig


class ResolvedAppConfig(ConfigModel):
    """Self-contained effective configuration stored with a run."""

    schema_version: Literal[1]
    configuration_kind: Literal["effective"] = "effective"
    run: RunConfig
    dataset: DatasetConfig
    experiment: ExperimentConfig
    backends: dict[BackendAlias, ResolvedBackend] = Field(min_length=1)
    stages: StagesConfig
    evaluation: EvaluationConfig


class StageAdapterConfig(ConfigModel):
    """Fully merged adapter name and settings for one pipeline stage."""

    adapter: str = Field(min_length=1)
    settings: dict[str, Any]
