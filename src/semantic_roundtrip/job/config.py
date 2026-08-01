"""Configuration and planning for persisted multi-experiment jobs."""

import os
import re
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Literal

import yaml
from pydantic import Field

from semantic_roundtrip.adapters.factory import create_adapters
from semantic_roundtrip.config import ConfigModel, ResolvedAppConfig
from semantic_roundtrip.config_resolution import (
    expected_stage_outputs,
    load_input_config,
)
from semantic_roundtrip.prompting import load_prompt_profile


JOB_INPUT_FILENAME = "job_input.yaml"
JOB_SNAPSHOT_FILENAME = "job_snapshot.yaml"
JOB_DATABASE_FILENAME = "job_state.sqlite"
JOB_RUNS_DIRECTORY = "runs"


class JobDefinition(ConfigModel):
    """Identity and failure policy for one job."""

    name: str = Field(min_length=1)
    output_directory: Path = Path("runs")
    continue_on_error: bool = False


class JobExperimentReference(ConfigModel):
    """One named experiment configuration in an input job."""

    name: str = Field(min_length=1)
    config: Path


class InputJobConfig(ConfigModel):
    """Human-maintained job configuration."""

    schema_version: Literal[2]
    job: JobDefinition
    experiments: list[JobExperimentReference] = Field(min_length=1)


class BackendSummary(ConfigModel):
    """Small backend identity stored with each job entry."""

    alias: str
    adapter: str
    model_id: str | None = None
    controller: str
    resource_group: str


class ResolvedJobEntry(ConfigModel):
    """One planned child run in a frozen job snapshot."""

    index: int = Field(ge=0)
    name: str = Field(min_length=1)
    source_config: Path
    backends: tuple[BackendSummary, ...]


class ResolvedJobConfig(ConfigModel):
    """Frozen job policy and immutable entry metadata used for resume."""

    schema_version: Literal[2]
    configuration_kind: Literal["effective"] = "effective"
    job: JobDefinition
    entries: list[ResolvedJobEntry] = Field(min_length=1)


@dataclass(frozen=True, slots=True)
class LoadedJobExperiment:
    """Resolved input entry before the job artifact directory exists."""

    index: int
    name: str
    source_reference: Path
    source_path: Path
    config: ResolvedAppConfig


@dataclass(frozen=True, slots=True)
class LoadedJobConfig:
    """Validated job input and all resolved experiment configurations."""

    source_path: Path
    input_config: InputJobConfig
    experiments: tuple[LoadedJobExperiment, ...]


@dataclass(frozen=True, slots=True)
class JobPlanEntry:
    """Expected work and model stack for one job entry."""

    index: int
    name: str
    config_path: Path
    expected_outputs: dict[str, int]
    backends: tuple[BackendSummary, ...]


@dataclass(frozen=True, slots=True)
class JobPlan:
    """Preflight summary for a complete job."""

    name: str
    entries: tuple[JobPlanEntry, ...]
    expected_outputs: dict[str, int]
    model_stacks: tuple[str, ...]
    missing_credentials: tuple[str, ...]
    missing_runtime_models: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class JobContext:
    """Stable identity and filesystem location of one persisted job."""

    job_id: str
    directory: Path
    created_at: datetime


def _read_yaml(path: Path) -> object:
    with path.open("r", encoding="utf-8") as file:
        return yaml.safe_load(file)


def backend_summaries(config: ResolvedAppConfig) -> tuple[BackendSummary, ...]:
    """Return stable, display-friendly identities for resolved backends."""
    summaries: list[BackendSummary] = []
    for alias, backend in sorted(config.backends.items()):
        configured_model_id = backend.settings.get("model_id")
        model_id = None if configured_model_id is None else str(configured_model_id)
        summaries.append(
            BackendSummary(
                alias=alias,
                adapter=backend.adapter,
                model_id=model_id,
                controller=backend.runtime.controller,
                resource_group=backend.runtime.resource_group,
            )
        )
    return tuple(summaries)


def load_job_config(path: Path) -> LoadedJobConfig:
    """Load a job and fully validate every referenced experiment."""
    path = path.resolve()
    input_config = InputJobConfig.model_validate(_read_yaml(path))
    names = [entry.name for entry in input_config.experiments]
    if len(names) != len(set(names)):
        raise ValueError("Every job experiment name must be unique.")

    base_directory = path.parent
    experiments: list[LoadedJobExperiment] = []
    for index, entry in enumerate(input_config.experiments):
        source_path = entry.config
        if not source_path.is_absolute():
            source_path = (base_directory / source_path).resolve()
        if not source_path.is_file():
            raise FileNotFoundError(
                f"Job experiment config does not exist: {source_path}"
            )

        config = load_input_config(source_path)
        load_prompt_profile(config.stages.prompt_generation.prompt_profile)
        create_adapters(config)
        experiments.append(
            LoadedJobExperiment(
                index=index,
                name=entry.name,
                source_reference=entry.config,
                source_path=source_path,
                config=config,
            )
        )

    return LoadedJobConfig(
        source_path=path,
        input_config=input_config,
        experiments=tuple(experiments),
    )


def load_job_snapshot(path: Path) -> ResolvedJobConfig:
    """Load a frozen job without reopening source experiment configurations."""
    config = ResolvedJobConfig.model_validate(_read_yaml(path))
    indexes = [entry.index for entry in config.entries]
    if indexes != list(range(len(indexes))):
        raise ValueError("Job snapshot entry indexes are not contiguous.")
    return config


def create_resolved_job_config(
    loaded: LoadedJobConfig,
) -> ResolvedJobConfig:
    """Build the frozen job policy and experiment-entry metadata."""
    entries = [
        ResolvedJobEntry(
            index=entry.index,
            name=entry.name,
            source_config=entry.source_reference,
            backends=backend_summaries(entry.config),
        )
        for entry in loaded.experiments
    ]
    return ResolvedJobConfig(
        schema_version=loaded.input_config.schema_version,
        job=loaded.input_config.job,
        entries=entries,
    )


def _runtime_catalog_model_ids(directory: Path) -> set[str]:
    model_ids: set[str] = set()
    if not directory.is_dir():
        return model_ids

    section_pattern = re.compile(r"^\[([^]]+)]\s*$")
    for path in sorted(directory.glob("*.ini")):
        for line in path.read_text(encoding="utf-8").splitlines():
            match = section_pattern.match(line.strip())
            if match is not None and match.group(1) != "*":
                model_ids.add(match.group(1))
    return model_ids


def _model_stack(backends: tuple[BackendSummary, ...]) -> str:
    parts = [
        (f"{backend.adapter}:{backend.model_id or 'default'}@{backend.resource_group}")
        for backend in backends
    ]
    return " | ".join(parts)


def plan_job(
    loaded: LoadedJobConfig,
    *,
    deployment_directory: Path = Path("configs/deployments"),
) -> JobPlan:
    """Calculate expected work and preflight warnings without creating a job."""
    totals = {
        "prompt_generation": 0,
        "image_generation": 0,
        "verification": 0,
        "image_description": 0,
        "title_guessing": 0,
        "evaluation": 0,
    }
    entries: list[JobPlanEntry] = []
    model_stacks: list[str] = []
    missing_credentials: set[str] = set()
    missing_runtime_models: set[str] = set()
    catalog_model_ids = _runtime_catalog_model_ids(deployment_directory)

    for entry in loaded.experiments:
        expected = expected_stage_outputs(entry.config)
        for stage, count in expected.items():
            totals[stage] += count

        summaries = backend_summaries(entry.config)
        stack = _model_stack(summaries)
        if not model_stacks or model_stacks[-1] != stack:
            model_stacks.append(stack)

        for backend in entry.config.backends.values():
            credential_name = backend.settings.get("api_key_env")
            if isinstance(credential_name, str) and not os.environ.get(credential_name):
                missing_credentials.add(credential_name)

            if backend.runtime.controller == "llama_cpp_router":
                model_id = backend.settings.get("model_id")
                if isinstance(model_id, str) and model_id not in catalog_model_ids:
                    missing_runtime_models.add(model_id)

        entries.append(
            JobPlanEntry(
                index=entry.index,
                name=entry.name,
                config_path=entry.source_path,
                expected_outputs=expected,
                backends=summaries,
            )
        )

    return JobPlan(
        name=loaded.input_config.job.name,
        entries=tuple(entries),
        expected_outputs=totals,
        model_stacks=tuple(model_stacks),
        missing_credentials=tuple(sorted(missing_credentials)),
        missing_runtime_models=tuple(sorted(missing_runtime_models)),
    )
