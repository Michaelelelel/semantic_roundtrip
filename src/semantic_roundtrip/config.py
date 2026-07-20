"""Validated experiment configuration models."""

from pathlib import Path
from typing import Annotated, Any, Literal

import yaml
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
    seeds: list[Annotated[int, Field(ge=0)]] = Field(min_length=1)
    retry_limit: int = Field(ge=0)

    @field_validator("seeds")
    @classmethod
    def require_unique_seeds(cls, seeds: list[int]) -> list[int]:
        if len(seeds) != len(set(seeds)):
            raise ValueError("Every configured seed must be unique.")
        return seeds


class AdapterSelection(ConfigModel):
    """Select one registered adapter and provide its private settings."""

    adapter: str = Field(min_length=1)
    settings: dict[str, Any] = Field(default_factory=dict)


class StagesConfig(ConfigModel):
    prompt_generation: AdapterSelection
    image_generation: AdapterSelection
    verification: AdapterSelection
    title_guessing: AdapterSelection


class EvaluationConfig(ConfigModel):
    failed_verification: Literal["count_as_failure", "exclude"]


class AppConfig(ConfigModel):
    run: RunConfig
    dataset: DatasetConfig
    experiment: ExperimentConfig
    stages: StagesConfig
    evaluation: EvaluationConfig


def load_config(path: Path) -> AppConfig:
    """Load and validate a YAML experiment configuration."""
    with path.open("r", encoding="utf-8") as file:
        raw_config = yaml.safe_load(file)

    return AppConfig.model_validate(raw_config)
