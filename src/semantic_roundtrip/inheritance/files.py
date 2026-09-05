"""Metadata-preserving copies of immutable experiment artifacts."""

import os
from collections.abc import Iterator
from pathlib import Path
from shutil import copy2


def _extended_windows_path(path: Path) -> str:
    value = str(path.absolute())
    if value.startswith("\\\\?\\"):
        return value
    if value.startswith("\\\\"):
        return "\\\\?\\UNC\\" + value[2:]
    return "\\\\?\\" + value


def native_path(path: str | Path) -> Path:
    """Adapt an IO argument, never a persisted logical path or provenance ID."""
    value = Path(path)
    return Path(_extended_windows_path(value)) if os.name == "nt" else value


def walk_artifact_paths(directory: Path) -> Iterator[Path]:
    """Walk deep provenance trees while returning ordinary logical paths."""
    for path in native_path(directory).rglob("*"):
        value = str(path)
        if os.name == "nt":
            if value.startswith("\\\\?\\UNC\\"):
                value = "\\\\" + value[8:]
            elif value.startswith("\\\\?\\"):
                value = value[4:]
        yield Path(value)


def copy_artifact(source: str | Path, destination: str | Path) -> Path:
    """Use Windows' long-path form only when a normal CopyFile2 path is too long.

    Stored paths and provenance IDs remain unchanged. This only adapts the OS
    arguments; copy2 still preserves the source's filesystem metadata.
    """
    source_path, destination_path = Path(source), Path(destination)
    if (
        os.name == "nt"
        and max(len(str(source_path.absolute())), len(str(destination_path.absolute())))
        >= 248
    ):
        copy2(
            _extended_windows_path(source_path),
            _extended_windows_path(destination_path),
        )
    else:
        copy2(source_path, destination_path)
    return destination_path
