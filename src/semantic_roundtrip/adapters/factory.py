"""Create independently configured provider adapters."""

from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

from semantic_roundtrip.adapters.base import (
    ImageGenerator,
    ImageTitleGuesser,
    ImageVerifier,
    PromptGenerator,
)
from semantic_roundtrip.adapters.comfyui import build_comfyui_image_generator
from semantic_roundtrip.adapters.mock import (
    build_mock_image_generator,
    build_mock_image_title_guesser,
    build_mock_image_verifier,
    build_mock_prompt_generator,
)
from semantic_roundtrip.adapters.openai_compatible import (
    build_openai_compatible_image_title_guesser,
    build_openai_compatible_image_verifier,
    build_openai_compatible_prompt_generator,
)
from semantic_roundtrip.config import ResolvedAppConfig, StageAdapterConfig
from semantic_roundtrip.config_resolution import resolve_stage_adapter


@dataclass(frozen=True, slots=True)
class AdapterBundle:
    """The four adapters required by the current direct-image pipeline."""

    prompt_generator: PromptGenerator
    image_generator: ImageGenerator
    image_verifier: ImageVerifier
    image_title_guesser: ImageTitleGuesser


PromptGeneratorBuilder = Callable[[dict[str, Any]], PromptGenerator]
ImageGeneratorBuilder = Callable[[dict[str, Any]], ImageGenerator]
ImageVerifierBuilder = Callable[[dict[str, Any]], ImageVerifier]
ImageTitleGuesserBuilder = Callable[[dict[str, Any]], ImageTitleGuesser]


PROMPT_GENERATORS: dict[str, PromptGeneratorBuilder] = {
    "mock": build_mock_prompt_generator,
    "openai_compatible": build_openai_compatible_prompt_generator,
}

IMAGE_GENERATORS: dict[str, ImageGeneratorBuilder] = {
    "mock": build_mock_image_generator,
    "comfyui": build_comfyui_image_generator,
}

IMAGE_VERIFIERS: dict[str, ImageVerifierBuilder] = {
    "mock": build_mock_image_verifier,
    "openai_compatible": build_openai_compatible_image_verifier,
}

IMAGE_TITLE_GUESSERS: dict[str, ImageTitleGuesserBuilder] = {
    "mock": build_mock_image_title_guesser,
    "openai_compatible": build_openai_compatible_image_title_guesser,
}


def _unsupported_adapter(
    *,
    stage: str,
    adapter: str,
    registry: dict[str, object],
) -> ValueError:
    available = ", ".join(sorted(registry))
    return ValueError(
        f"Unknown {stage} adapter '{adapter}'. Available adapters: {available}"
    )


def create_prompt_generator(
    selection: StageAdapterConfig,
) -> PromptGenerator:
    builder = PROMPT_GENERATORS.get(selection.adapter)
    if builder is None:
        raise _unsupported_adapter(
            stage="prompt-generation",
            adapter=selection.adapter,
            registry=PROMPT_GENERATORS,
        )
    return builder(selection.settings)


def create_image_generator(
    selection: StageAdapterConfig,
) -> ImageGenerator:
    builder = IMAGE_GENERATORS.get(selection.adapter)
    if builder is None:
        raise _unsupported_adapter(
            stage="image-generation",
            adapter=selection.adapter,
            registry=IMAGE_GENERATORS,
        )
    return builder(selection.settings)


def create_image_verifier(
    selection: StageAdapterConfig,
) -> ImageVerifier:
    builder = IMAGE_VERIFIERS.get(selection.adapter)
    if builder is None:
        raise _unsupported_adapter(
            stage="verification",
            adapter=selection.adapter,
            registry=IMAGE_VERIFIERS,
        )
    return builder(selection.settings)


def create_image_title_guesser(
    selection: StageAdapterConfig,
) -> ImageTitleGuesser:
    builder = IMAGE_TITLE_GUESSERS.get(selection.adapter)
    if builder is None:
        raise _unsupported_adapter(
            stage="image title-guessing",
            adapter=selection.adapter,
            registry=IMAGE_TITLE_GUESSERS,
        )
    return builder(selection.settings)


def create_adapters(config: ResolvedAppConfig) -> AdapterBundle:
    """Create adapters for the currently implemented direct-image route."""
    if config.stages.title_guessing.input != "image":
        raise ValueError(
            "Description-based title guessing is configured but is not "
            "executable until the image-description pipeline phase."
        )

    return AdapterBundle(
        prompt_generator=create_prompt_generator(
            resolve_stage_adapter(config, "prompt_generation")
        ),
        image_generator=create_image_generator(
            resolve_stage_adapter(config, "image_generation")
        ),
        image_verifier=create_image_verifier(
            resolve_stage_adapter(config, "verification")
        ),
        image_title_guesser=create_image_title_guesser(
            resolve_stage_adapter(config, "title_guessing")
        ),
    )
