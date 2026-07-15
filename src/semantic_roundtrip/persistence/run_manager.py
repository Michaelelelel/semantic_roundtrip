"""Creation and identification of experiment runs."""

from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
import re
from uuid import uuid4

import yaml

from semantic_roundtrip.config import AppConfig


@dataclass(frozen=True)
class RunContext:
    """The stable identity and filesystem location of one experiment run."""

    run_id: str
    directory: Path

def create_run_id(name: str) -> str:
    """Create a readable, unique identifier for a new experiment run.

    The timestamp is always UTC. The random suffix prevents collisions when
    multiple runs start at the same time.
    """

    timestamp = datetime.now()

    timestamp_text = timestamp.strftime("%Y%m%dT%H%M%SZ")

    readable_name = re.sub(
        r"[^a-zA-Z0-9]+",
        "-",
        name,
    ).strip("-").lower()

    random_suffix = uuid4().hex[:8]

    return f"{timestamp_text}_{readable_name}_{random_suffix}"


def create_run_directory(base_path: Path, run_id: str) -> Path:
    """Create and return a new run directory without overwriting anything."""
    base_path = Path(base_path)

    run_directory = base_path / run_id
    run_directory.mkdir(parents=True, exist_ok=False)
    return run_directory

def create_run(base_path: Path, name: str) -> RunContext:
    """Create a new run and return its identity and directory."""
    for _ in range(5):
        run_id = create_run_id(name)
        try:
            directory = create_run_directory(base_path, run_id)
            return RunContext(run_id=run_id, directory=directory)
        except FileExistsError:
            # A UUID collision is unlikely, but retry.
            continue

    raise RuntimeError("Could not create a unique run directory.")

def create_config_snapshot(config: AppConfig, run_directory: Path,):
    """Create a snapshot of the current configuration in the run directory."""
    snapshot_path = run_directory / "config_snapshot.yaml"

    with snapshot_path.open("x", encoding="utf-8") as file:
        yaml.safe_dump(
            config.model_dump(mode="json"),
            file,
            sort_keys=False,
            allow_unicode=True,
        )

    return snapshot_path