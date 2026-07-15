"""Persistence of input and effective experiment configurations."""

from pathlib import Path
from shutil import copy2

import yaml

from semantic_roundtrip.config import AppConfig


INPUT_CONFIG_FILENAME = "config_input.yaml"
EFFECTIVE_CONFIG_FILENAME = "config_snapshot.yaml"


def create_input_config_snapshot(
    config_path: Path,
    run_directory: Path,
) -> Path:
    """Copy the exact input configuration into the run directory."""
    snapshot_path = run_directory / INPUT_CONFIG_FILENAME

    if snapshot_path.exists():
        raise FileExistsError(
            f"Input configuration snapshot already exists: {snapshot_path}"
        )

    copy2(config_path, snapshot_path)
    return snapshot_path


def create_effective_config_snapshot(
    config: AppConfig,
    run_directory: Path,
) -> Path:
    """Write the validated configuration, including default values."""
    snapshot_path = run_directory / EFFECTIVE_CONFIG_FILENAME

    with snapshot_path.open("x", encoding="utf-8") as file:
        yaml.safe_dump(
            config.model_dump(mode="json"),
            file,
            sort_keys=False,
            allow_unicode=True,
        )

    return snapshot_path
