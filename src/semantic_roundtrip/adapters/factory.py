"""Create independently configured provider adapters."""

from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

from semantic_roundtrip.adapters.base import (
    ImageGenerator,
    ImageVerifier,
    PromptGenerator,
    TitleGuesser,
)
from semantic_roundtrip.adapters.comfyui import build_comfyui_image_generator
from semantic_roundtrip.adapters.llama_cpp_vision import (
    build_llama_cpp_image_verifier,
    build_llama_cpp_title_guesser,
)
from semantic_roundtrip.adapters.mock import (
    build_mock_image_generator,
    build_mock_image_verifier,
    build_mock_prompt_generator,
    build_mock_title_guesser,
)
from semantic_roundtrip.adapters.openai_compatible import (
    build_openai_compatible_prompt_generator,
)
from semantic_roundtrip.config import AdapterSelection, StagesConfig


@dataclass(frozen=True, slots=True)
class AdapterBundle:
    """The four adapters required by one pipeline run."""

    prompt_generator: PromptGenerator
    image_generator: ImageGenerator
    image_verifier: ImageVerifier
    title_guesser: TitleGuesser


PromptGeneratorBuilder = Callable[[dict[str, Any]], PromptGenerator]
ImageGeneratorBuilder = Callable[[dict[str, Any]], ImageGenerator]
ImageVerifierBuilder = Callable[[dict[str, Any]], ImageVerifier]
TitleGuesserBuilder = Callable[[dict[str, Any]], TitleGuesser]


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
    "llama_cpp_vision": build_llama_cpp_image_verifier,
}

TITLE_GUESSERS: dict[str, TitleGuesserBuilder] = {
    "mock": build_mock_title_guesser,
    "llama_cpp_vision": build_llama_cpp_title_guesser,
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
    selection: AdapterSelection,
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
    selection: AdapterSelection,
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
    selection: AdapterSelection,
) -> ImageVerifier:
    builder = IMAGE_VERIFIERS.get(selection.adapter)
    if builder is None:
        raise _unsupported_adapter(
            stage="verification",
            adapter=selection.adapter,
            registry=IMAGE_VERIFIERS,
        )
    return builder(selection.settings)


def create_title_guesser(
    selection: AdapterSelection,
) -> TitleGuesser:
    builder = TITLE_GUESSERS.get(selection.adapter)
    if builder is None:
        raise _unsupported_adapter(
            stage="title-guessing",
            adapter=selection.adapter,
            registry=TITLE_GUESSERS,
        )
    return builder(selection.settings)


def create_adapters(config: StagesConfig) -> AdapterBundle:
    """Create all adapters."""
    return AdapterBundle(
        prompt_generator=create_prompt_generator(config.prompt_generation),
        image_generator=create_image_generator(config.image_generation),
        image_verifier=create_image_verifier(config.verification),
        title_guesser=create_title_guesser(config.title_guessing),
    )
