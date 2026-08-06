"""Persistence of ComfyUI workflows used by experiment runs."""

from pathlib import Path
from shutil import copy2
from typing import Any

from semantic_roundtrip.config import ResolvedAppConfig, ResolvedBackend


IMAGE_GENERATION_WORKFLOW_FILENAME = "image_generation_workflow.json"


def _image_generation_backend(
    config: ResolvedAppConfig,
) -> tuple[str, ResolvedBackend]:
    backend_alias = config.stages.image_generation.backend
    return backend_alias, config.backends[backend_alias]


def create_workflow_snapshots(
    config: ResolvedAppConfig,
    run_directory: Path,
) -> dict[str, Path]:
    """Copy every external workflow required by the configured run."""
    _, backend = _image_generation_backend(config)
    if backend.adapter != "comfyui":
        return {}

    workflow_path = backend.settings.get("workflow_path")
    if not isinstance(workflow_path, (str, Path)):
        raise ValueError("ComfyUI settings require workflow_path.")

    snapshot_path = run_directory / IMAGE_GENERATION_WORKFLOW_FILENAME
    copy2(Path(workflow_path), snapshot_path)
    return {"image_generation": snapshot_path}


def use_workflow_snapshots(
    config: ResolvedAppConfig,
    run_directory: Path,
) -> ResolvedAppConfig:
    """Point configured backends to workflows copied into the run."""
    snapshot_path = run_directory / IMAGE_GENERATION_WORKFLOW_FILENAME
    if not snapshot_path.is_file():
        return config

    backend_alias, backend = _image_generation_backend(config)
    if backend.adapter != "comfyui":
        return config

    settings: dict[str, Any] = backend.settings | {
        "workflow_path": snapshot_path,
    }
    resolved_backend = backend.model_copy(update={"settings": settings})
    backends = config.backends | {backend_alias: resolved_backend}
    return config.model_copy(update={"backends": backends})
