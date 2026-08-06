"""Resolve runtime targets and create their controllers."""

from typing import Any

from semantic_roundtrip.config import ResolvedAppConfig, StageName
from semantic_roundtrip.config_resolution import get_stage_config
from semantic_roundtrip.runtime.base import RuntimeController, RuntimeTarget
from semantic_roundtrip.runtime.comfyui import ComfyUIRuntimeController
from semantic_roundtrip.runtime.llama_cpp_router import LlamaCppRouterController
from semantic_roundtrip.runtime.no_op import NoOpRuntimeController


def resolve_runtime_target(
    config: ResolvedAppConfig,
    stage: StageName,
) -> RuntimeTarget:
    """Resolve the runtime identity used by one configured pipeline stage."""
    stage_config = get_stage_config(config, stage)
    if stage_config is None:
        raise ValueError(f"Optional stage '{stage}' is not configured.")

    backend_alias = stage_config.backend
    backend = config.backends[backend_alias]
    runtime = backend.runtime
    control_url = (
        None if runtime.control_url is None else runtime.control_url.rstrip("/")
    )
    model_id = _optional_text_setting(backend.settings, "model_id")
    model_reference = model_id

    if runtime.controller in {"llama_cpp_router", "comfyui"} and model_id is None:
        raise ValueError(
            f"Runtime backend '{backend_alias}' requires settings.model_id."
        )

    return RuntimeTarget(
        stage=stage,
        backend_alias=backend_alias,
        controller=runtime.controller,
        control_url=control_url,
        resource_group=runtime.resource_group,
        model_id=model_id,
        model_reference=model_reference,
    )


def create_runtime_controller(target: RuntimeTarget) -> RuntimeController:
    """Create the controller selected by one resolved runtime target."""
    if target.controller in {"none", "managed_api"}:
        return NoOpRuntimeController()
    if target.control_url is None:
        raise ValueError(
            f"Runtime controller '{target.controller}' requires a control URL."
        )
    if target.controller == "llama_cpp_router":
        return LlamaCppRouterController(target.control_url)
    if target.controller == "comfyui":
        return ComfyUIRuntimeController(target.control_url)
    raise ValueError(f"Unsupported runtime controller: {target.controller}")


def _optional_text_setting(
    settings: dict[str, Any],
    name: str,
) -> str | None:
    value = settings.get(name)
    if value is None:
        return None
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"Backend setting '{name}' must be non-empty text.")
    return value
