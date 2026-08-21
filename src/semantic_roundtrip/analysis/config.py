"""Validated configuration for analyzing selected persisted runs."""

from dataclasses import dataclass
from pathlib import Path
from typing import Annotated, Literal, Self

import yaml
from pydantic import Field, model_validator

from semantic_roundtrip.config import ConfigModel


STUDY_CONFIG_FILENAME = "study.yaml"
ConditionId = Annotated[str, Field(pattern=r"^[a-z][a-z0-9_]*$")]
GroupId = Annotated[str, Field(pattern=r"^[a-z][a-z0-9_]*$")]


class StudyDefinition(ConfigModel):
    """Identity and output location of one analysis."""

    name: str = Field(min_length=1)
    output_directory: Path = Path("results")


class StudyCondition(ConfigModel):
    """One named persisted run selected for the study."""

    run: Path
    label: str | None = Field(default=None, min_length=1)


class StudyGroup(ConfigModel):
    """Runs that jointly answer one research question."""

    kind: Literal["accuracy", "paired", "routes"]
    conditions: list[ConditionId] = Field(min_length=1)
    reference: ConditionId | None = None
    route: Literal["direct", "description"] = "direct"

    @model_validator(mode="after")
    def validate_group_shape(self) -> Self:
        if len(self.conditions) != len(set(self.conditions)):
            raise ValueError("Study-group conditions must be unique.")

        if self.kind == "paired":
            if len(self.conditions) < 2:
                raise ValueError("A paired group requires at least two conditions.")
            if self.reference is None:
                raise ValueError("A paired group requires a reference condition.")
            if self.reference not in self.conditions:
                raise ValueError(
                    "The paired-group reference must be one of its conditions."
                )
        elif self.reference is not None:
            raise ValueError("Only a paired group can define a reference condition.")

        return self


class StudyConfig(ConfigModel):
    """Complete reproducible selection and grouping of study runs."""

    schema_version: Literal[1]
    study: StudyDefinition
    conditions: dict[ConditionId, StudyCondition] = Field(min_length=1)
    groups: dict[GroupId, StudyGroup] = Field(min_length=1)

    @model_validator(mode="after")
    def validate_references(self) -> Self:
        known_conditions = set(self.conditions)
        used_conditions: set[str] = set()
        for group_id, group in self.groups.items():
            used_conditions.update(group.conditions)
            unknown = set(group.conditions) - known_conditions
            if unknown:
                names = ", ".join(sorted(unknown))
                raise ValueError(
                    f"Study group '{group_id}' references unknown conditions: {names}"
                )

        unused = known_conditions - used_conditions
        if unused:
            names = ", ".join(sorted(unused))
            raise ValueError(f"Study conditions are not used by any group: {names}")
        return self


@dataclass(frozen=True, slots=True)
class LoadedStudy:
    """Resolved study paths plus the exact input bytes used for the analysis."""

    directory: Path
    source_path: Path
    source_bytes: bytes
    config: StudyConfig
    run_directories: dict[str, Path]
    output_directory: Path


def load_study(directory: Path) -> LoadedStudy:
    """Load one study directory and resolve every selected run path."""
    directory = directory.resolve()
    if not directory.is_dir():
        raise NotADirectoryError(f"Study directory does not exist: {directory}")

    source_path = directory / STUDY_CONFIG_FILENAME
    source_bytes = source_path.read_bytes()
    raw_config = yaml.safe_load(source_bytes.decode("utf-8"))
    config = StudyConfig.model_validate(raw_config)

    run_directories: dict[str, Path] = {}
    seen_paths: set[Path] = set()
    for condition_id, condition in config.conditions.items():
        run_directory = condition.run
        if not run_directory.is_absolute():
            run_directory = directory / run_directory
        run_directory = run_directory.resolve()
        if not run_directory.is_dir():
            raise NotADirectoryError(
                f"Run directory for condition '{condition_id}' does not exist: "
                f"{run_directory}"
            )
        if run_directory in seen_paths:
            raise ValueError(
                f"Run directory is selected by more than one condition: "
                f"{run_directory}"
            )
        seen_paths.add(run_directory)
        run_directories[condition_id] = run_directory

    output_directory = config.study.output_directory
    if not output_directory.is_absolute():
        output_directory = directory / output_directory
    output_directory = output_directory.resolve()

    if directory == output_directory or directory.is_relative_to(output_directory):
        raise ValueError("The results directory must not replace the study directory.")
    for condition_id, run_directory in run_directories.items():
        if output_directory.is_relative_to(run_directory) or run_directory.is_relative_to(
            output_directory
        ):
            raise ValueError(
                f"The results directory must not overlap the run directory for "
                f"condition '{condition_id}'."
            )

    return LoadedStudy(
        directory=directory,
        source_path=source_path,
        source_bytes=source_bytes,
        config=config,
        run_directories=run_directories,
        output_directory=output_directory,
    )
