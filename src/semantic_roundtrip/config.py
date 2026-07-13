from pathlib import Path

import yaml
from pydantic import BaseModel, Field


class RunConfig(BaseModel):
    name: str = Field(min_length=1)
    output_directory: Path = Path("runs")


class DatasetItem(BaseModel):
    domain: str
    title: str


class DatasetConfig(BaseModel):
    items: list[DatasetItem]


class ExperimentConfig(BaseModel):
    prompts_per_title: int = Field(gt=0)
    seeds_per_prompt: int = Field(gt=0)
    retry_limit: int = Field(ge=0)


class StageConfig(BaseModel):
    adapter: str = Field(min_length=1)


class StagesConfig(BaseModel):
    prompt_generation: StageConfig
    image_generation: StageConfig
    verification: StageConfig
    title_guessing: StageConfig


class AppConfig(BaseModel):
    run: RunConfig
    dataset: DatasetConfig
    experiment: ExperimentConfig
    stages: StagesConfig


def load_config(path: Path) -> AppConfig:
    with path.open("r", encoding="utf-8") as file:
        raw_config = yaml.safe_load(file)

    return AppConfig.model_validate(raw_config)