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
    prompt_seeds: list[Annotated[int, Field(ge=0)]] = Field(default_factory=list)
    image_seeds: list[Annotated[int, Field(ge=0)]] = Field(default_factory=list)
    retry_limit: int = Field(ge=0)

    @field_validator("prompt_seeds", "image_seeds")
    @classmethod
    def require_unique_seeds(cls, seeds: list[int]) -> list[int]:
        if len(seeds) != len(set(seeds)):
            raise ValueError("Every configured seed in a seed list must be unique.")
        return seeds


BackendAlias = Annotated[str, Field(min_length=1)]
StageName = Literal[
    "illustratability_rating",
    "prompt_generation",
    "image_generation",
    "verification",
    "title_guessing_direct",
    "image_description",
    "title_guessing_from_description",
]
PipelineStageName = StageName
PredictionInputKind = Literal["image", "description"]
ExecutionOrigin = Literal["local", "imported"]
ImageVerificationPolicy = Literal["strict", "title_aware"]


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


class IllustratabilityRatingStage(StageConfig):
    prompt_profile: Path


class ImageGenerationStage(StageConfig):
    pass


class PromptVerificationPolicy(ConfigModel):
    """Deterministic reference-title leakage policy for generated prompts."""

    policy: Literal["reference_title_absent"]


class ImageVerificationCheck(ConfigModel):
    """One image-verification policy and its versioned model instruction."""

    prompt_profile: Path


class ImageVerificationPolicies(ConfigModel):
    """Independently selectable image-verification policies."""

    strict: ImageVerificationCheck | None = None
    title_aware: ImageVerificationCheck | None = None

    @model_validator(mode="after")
    def require_at_least_one_policy(self) -> Self:
        if self.strict is None and self.title_aware is None:
            raise ValueError("Configure at least one image-verification policy.")
        return self


class VerificationStage(StageConfig):
    """Optional prompt check and zero, one, or two independent image checks."""

    prompt: PromptVerificationPolicy | None = None
    image: ImageVerificationPolicies | None = None

    @model_validator(mode="after")
    def require_at_least_one_check(self) -> Self:
        if self.prompt is None and self.image is None:
            raise ValueError("Configure at least one verification check.")
        return self


class ImageDescriptionStage(StageConfig):
    prompt_profile: Path


class TitleGuessingStage(StageConfig):
    prompt_profile: Path


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
    illustratability_rating: IllustratabilityRatingStage | None = None
    prompt_generation: PromptGenerationStage | None = None
    image_generation: ImageGenerationStage | None = None
    verification: VerificationStage | None = None
    image_description: ImageDescriptionStage | None = None
    title_guessing: TitleGuessingRoutes | None = None

    @model_validator(mode="after")
    def require_at_least_one_local_stage(self) -> Self:
        configured = (
            self.illustratability_rating,
            self.prompt_generation,
            self.image_generation,
            self.verification,
            self.image_description,
            None if self.title_guessing is None else self.title_guessing.direct,
            (
                None
                if self.title_guessing is None
                else self.title_guessing.from_description
            ),
        )
        if not any(stage is not None for stage in configured):
            raise ValueError("Configure at least one locally executed stage.")
        return self


class InputRunInheritance(ConfigModel):
    """Select completed work from one existing standalone run."""

    from_run: Path
    stages: list[StageName] = Field(min_length=1)

    @field_validator("stages")
    @classmethod
    def require_unique_stages(cls, stages: list[StageName]) -> list[StageName]:
        if len(stages) != len(set(stages)):
            raise ValueError("Every inherited stage may be listed only once.")
        return stages


class ResolvedRunInheritance(ConfigModel):
    """Concrete source identity frozen into an effective run snapshot."""

    source_kind: Literal["from_run", "from_entry", "from_job_entry"]
    source_run: Path
    source_run_id: str = Field(min_length=1)
    source_entry: str | None = None
    source_job: str | None = None
    stages: list[StageName] = Field(min_length=1)

    @field_validator("stages")
    @classmethod
    def require_unique_stages(cls, stages: list[StageName]) -> list[StageName]:
        if len(stages) != len(set(stages)):
            raise ValueError("Every inherited stage may be listed only once.")
        return stages


class InputAppConfig(ConfigModel):
    """Human-maintained experiment configuration with backend references."""

    schema_version: Literal[10]
    run: RunConfig
    dataset: InputDatasetConfig | None = None
    inherit: InputRunInheritance | None = None
    experiment: ExperimentConfig
    backends: dict[BackendAlias, BackendReference] = Field(default_factory=dict)
    stages: StagesConfig

    @model_validator(mode="after")
    def reject_two_dataset_sources(self) -> Self:
        if self.dataset is not None and self.inherit is not None:
            raise ValueError(
                "A configured dataset cannot be combined with run inheritance."
            )
        return self


class ResolvedAppConfig(ConfigModel):
    """Self-contained effective configuration stored with a run."""

    schema_version: Literal[10]
    configuration_kind: Literal["effective"] = "effective"
    run: RunConfig
    dataset: ResolvedDatasetConfig
    inherit: ResolvedRunInheritance | None = None
    experiment: ExperimentConfig
    backends: dict[BackendAlias, ResolvedBackend] = Field(default_factory=dict)
    stages: StagesConfig

class StageAdapterConfig(ConfigModel):
    """Fully merged adapter name and settings for one pipeline stage."""

    adapter: str = Field(min_length=1)
    settings: dict[str, Any]
