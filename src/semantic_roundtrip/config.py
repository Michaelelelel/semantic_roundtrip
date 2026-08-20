"""Validated input and effective experiment configuration models."""

from pathlib import Path
from typing import Annotated, Any, Literal, Self

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator


class ConfigModel(BaseModel):
    """Reject unknown configuration keys instead of silently ignoring typos."""

    model_config = ConfigDict(extra="forbid")


class RunConfig(ConfigModel):
    name: str = Field(min_length=1)
    output_directory: Path = Path("runs")


class DatasetItem(ConfigModel):
    id: Annotated[str, Field(pattern=r"^[a-z][a-z0-9_]*$")]
    domain: str = Field(min_length=1)
    title: str = Field(min_length=1)

    @field_validator("domain", "title")
    @classmethod
    def reject_whitespace_only_text(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("Dataset domain and title cannot be blank.")
        return value


def _require_unique_item_ids(items: list[DatasetItem]) -> None:
    item_ids = [item.id for item in items]
    if len(item_ids) != len(set(item_ids)):
        raise ValueError("Every dataset item ID must be unique.")


class DatasetProfile(ConfigModel):
    """Reusable, versioned title collection referenced by experiments."""

    schema_version: Literal[1]
    dataset_id: Annotated[str, Field(pattern=r"^[a-z][a-z0-9_]*$")]
    items: list[DatasetItem] = Field(min_length=1)

    @model_validator(mode="after")
    def require_unique_item_ids(self) -> Self:
        _require_unique_item_ids(self.items)
        return self


class InputDatasetConfig(ConfigModel):
    """Dataset profile reference or an inline dataset for a small smoke run."""

    profile: Path | None = None
    dataset_id: (
        Annotated[
            str,
            Field(pattern=r"^[a-z][a-z0-9_]*$"),
        ]
        | None
    ) = None
    items: list[DatasetItem] | None = Field(default=None, min_length=1)

    @model_validator(mode="after")
    def require_profile_or_complete_inline_dataset(self) -> Self:
        if self.profile is not None:
            if self.dataset_id is not None or self.items is not None:
                raise ValueError(
                    "A dataset profile cannot be combined with dataset_id or items."
                )
            return self

        if self.dataset_id is None or self.items is None:
            raise ValueError("An inline dataset requires both dataset_id and items.")
        _require_unique_item_ids(self.items)
        return self


class ResolvedDatasetConfig(ConfigModel):
    """Self-contained title collection stored in the effective snapshot."""

    dataset_id: Annotated[str, Field(pattern=r"^[a-z][a-z0-9_]*$")]
    source_profile: Path | None = None
    items: list[DatasetItem] = Field(min_length=1)

    @model_validator(mode="after")
    def require_unique_item_ids(self) -> Self:
        _require_unique_item_ids(self.items)
        return self


class ExperimentConfig(ConfigModel):
    prompt_seeds: list[Annotated[int, Field(ge=0)]] = Field(min_length=1)
    image_seeds: list[Annotated[int, Field(ge=0)]] = Field(min_length=1)
    retry_limit: int = Field(ge=0)

    @field_validator("prompt_seeds", "image_seeds")
    @classmethod
    def require_unique_seeds(cls, seeds: list[int]) -> list[int]:
        if len(seeds) != len(set(seeds)):
            raise ValueError("Every configured seed in a seed list must be unique.")
        return seeds


BackendAlias = Annotated[str, Field(min_length=1)]
StageName = Literal[
    "prompt_generation",
    "image_generation",
    "verification",
    "title_guessing_direct",
    "image_description",
    "title_guessing_from_description",
]
PipelineStageName = StageName | Literal["evaluation"]
PredictionInputKind = Literal["image", "description"]


class BackendReference(ConfigModel):
    """Reference a reusable backend profile from an input configuration."""

    profile: Path


class RuntimeSpec(ConfigModel):
    """Describe runtime ownership without coupling it to inference adapters."""

    controller: Literal[
        "none",
        "llama_cpp_router",
        "comfyui",
    ]
    control_url: str | None = None
    resource_group: str = Field(min_length=1)

    @model_validator(mode="after")
    def require_local_control_url(self) -> Self:
        if self.controller in {"llama_cpp_router", "comfyui"} and not self.control_url:
            raise ValueError(
                f"Runtime controller '{self.controller}' requires control_url."
            )
        return self


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


class ImageDescriptionStage(StageConfig):
    template_path: Path


class TitleGuessingStage(StageConfig):
    template_path: Path | None = None


class TitleGuessingRoutes(ConfigModel):
    """The independently configurable routes used to reconstruct a title."""

    direct: TitleGuessingStage | None = None
    from_description: TitleGuessingStage | None = None

    @model_validator(mode="after")
    def require_at_least_one_route(self) -> Self:
        if self.direct is None and self.from_description is None:
            raise ValueError("Configure at least one title-guessing route.")
        return self


class StagesConfig(ConfigModel):
    prompt_generation: PromptGenerationStage
    image_generation: ImageGenerationStage
    verification: VerificationStage
    image_description: ImageDescriptionStage | None = None
    title_guessing: TitleGuessingRoutes

    @model_validator(mode="after")
    def require_consistent_title_routes(self) -> Self:
        uses_description = self.title_guessing.from_description is not None
        has_description_stage = self.image_description is not None

        if uses_description and not has_description_stage:
            raise ValueError(
                "title_guessing.from_description requires image_description."
            )
        if not uses_description and has_description_stage:
            raise ValueError(
                "image_description requires title_guessing.from_description."
            )
        return self


class InputAppConfig(ConfigModel):
    """Human-maintained experiment configuration with backend references."""

    schema_version: Literal[6]
    run: RunConfig
    dataset: InputDatasetConfig
    experiment: ExperimentConfig
    backends: dict[BackendAlias, BackendReference] = Field(min_length=1)
    stages: StagesConfig


class ResolvedAppConfig(ConfigModel):
    """Self-contained effective configuration stored with a run."""

    schema_version: Literal[6]
    configuration_kind: Literal["effective"] = "effective"
    run: RunConfig
    dataset: ResolvedDatasetConfig
    experiment: ExperimentConfig
    backends: dict[BackendAlias, ResolvedBackend] = Field(min_length=1)
    stages: StagesConfig


class StageAdapterConfig(ConfigModel):
    """Fully merged adapter name and settings for one pipeline stage."""

    adapter: str = Field(min_length=1)
    settings: dict[str, Any]
