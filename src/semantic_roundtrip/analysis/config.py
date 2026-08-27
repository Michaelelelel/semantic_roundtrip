"""Validated study selection with unambiguous persisted-run resolution."""

import sqlite3
from dataclasses import dataclass
from pathlib import Path
from typing import Annotated, Literal, Self

import yaml
from pydantic import Field, model_validator

from semantic_roundtrip.config import ConfigModel
from semantic_roundtrip.persistence.run.schema import DATABASE_FILENAME

ConditionId = Annotated[str, Field(pattern=r"^[a-z][a-z0-9_]*$")]
Route = Literal["direct", "description"]


class StudyDefinition(ConfigModel):
    """Identity and output location for one frozen study revision."""

    name: str = Field(min_length=1)
    revision: str = Field(min_length=1)
    output_directory: Path = Path("results")


class StudyCondition(ConfigModel):
    """One scientific condition and exactly one persisted-run selector."""

    run_name: str | None = Field(default=None, min_length=1)
    run: Path | None = None
    design: str = Field(min_length=1)
    pg: str = Field(min_length=1)
    bg: str = Field(min_length=1)
    bb: str | None = Field(default=None, min_length=1)
    bi: str = Field(min_length=1)
    routes: list[Route] = Field(min_length=1)
    label: str | None = Field(default=None, min_length=1)

    @model_validator(mode="after")
    def require_one_selector_and_unique_routes(self) -> Self:
        if (self.run_name is None) == (self.run is None):
            raise ValueError("A condition requires exactly one of run_name or run.")
        if len(self.routes) != len(set(self.routes)):
            raise ValueError("Condition routes must be unique.")
        if "description" in self.routes and self.bb is None:
            raise ValueError("A description route requires a BB model label.")
        return self


class StudyConfig(ConfigModel):
    """Complete, declarative selection used by the thesis notebook."""

    schema_version: Literal[2]
    study: StudyDefinition
    run_roots: list[Path] = Field(min_length=1)
    conditions: dict[ConditionId, StudyCondition] = Field(min_length=1)


@dataclass(frozen=True, slots=True)
class LoadedStudy:
    """Resolved study paths and the exact configuration bytes used."""

    source_path: Path
    source_bytes: bytes
    config: StudyConfig
    run_roots: tuple[Path, ...]
    run_directories: dict[str, Path]
    output_directory: Path


def _read_run_name(database_path: Path) -> str | None:
    """Read only the name while scanning, ignoring unrelated old run schemas."""
    try:
        uri = f"file:{database_path.resolve().as_posix()}?mode=ro"
        connection = sqlite3.connect(uri, uri=True)
        try:
            row = connection.execute("SELECT name FROM run_metadata").fetchone()
        finally:
            connection.close()
    except sqlite3.Error:
        return None
    return None if row is None else str(row[0])


def _resolve_relative(path: Path, base_directory: Path) -> Path:
    return (path if path.is_absolute() else base_directory / path).resolve()


def _find_named_run(run_name: str, roots: tuple[Path, ...]) -> Path:
    matches: set[Path] = set()
    for root in roots:
        for database_path in root.rglob(DATABASE_FILENAME):
            if _read_run_name(database_path) == run_name:
                matches.add(database_path.parent.resolve())
    if not matches:
        raise FileNotFoundError(
            f"No run named '{run_name}' was found below the configured run_roots."
        )
    if len(matches) > 1:
        locations = "\n".join(f"- {path}" for path in sorted(matches))
        raise ValueError(
            f"Run name '{run_name}' is ambiguous. Select one explicit run path:\n"
            f"{locations}"
        )
    return matches.pop()


def load_study(path: Path) -> LoadedStudy:
    """Load a schema-v2 study file and resolve each condition exactly once."""
    source_path = path.resolve()
    if source_path.is_dir():
        source_path = source_path / "study.yaml"
    source_bytes = source_path.read_bytes()
    config = StudyConfig.model_validate(yaml.safe_load(source_bytes.decode("utf-8")))
    base_directory = source_path.parent

    run_roots = tuple(
        _resolve_relative(root, base_directory) for root in config.run_roots
    )
    for root in run_roots:
        if not root.is_dir():
            raise NotADirectoryError(f"Study run_root does not exist: {root}")

    run_directories: dict[str, Path] = {}
    selected_paths: dict[Path, str] = {}
    for condition_id, condition in config.conditions.items():
        if condition.run_name is not None:
            run_directory = _find_named_run(condition.run_name, run_roots)
        else:
            assert condition.run is not None
            run_directory = _resolve_relative(condition.run, base_directory)
        if not (run_directory / DATABASE_FILENAME).is_file():
            raise FileNotFoundError(
                f"Condition '{condition_id}' is not a persisted run: {run_directory}"
            )
        previous = selected_paths.get(run_directory)
        if previous is not None:
            raise ValueError(
                f"Conditions '{previous}' and '{condition_id}' select the same run."
            )
        selected_paths[run_directory] = condition_id
        run_directories[condition_id] = run_directory

    output_directory = _resolve_relative(
        config.study.output_directory,
        base_directory,
    )
    for condition_id, run_directory in run_directories.items():
        if output_directory == run_directory or output_directory.is_relative_to(
            run_directory
        ):
            raise ValueError(
                f"Study output overlaps condition '{condition_id}': {run_directory}"
            )

    return LoadedStudy(
        source_path=source_path,
        source_bytes=source_bytes,
        config=config,
        run_roots=run_roots,
        run_directories=run_directories,
        output_directory=output_directory,
    )
