"""Create independently configured provider adapters."""

from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

from semantic_roundtrip.adapters.base import (
    ImageDescriber,
    ImageGenerator,
    ImageTitleGuesser,
    ImageVerifier,
    PromptGenerator,
    TextTitleGuesser,
)
from semantic_roundtrip.adapters.comfyui import build_comfyui_image_generator
from semantic_roundtrip.adapters.mock import (
    build_mock_image_describer,
    build_mock_image_generator,
    build_mock_image_title_guesser,
    build_mock_image_verifier,
    build_mock_prompt_generator,
    build_mock_text_title_guesser,
)
from semantic_roundtrip.adapters.openai_compatible import (
    build_openai_compatible_image_describer,
    build_openai_compatible_image_title_guesser,
    build_openai_compatible_image_verifier,
    build_openai_compatible_prompt_generator,
    build_openai_compatible_text_title_guesser,
)
from semantic_roundtrip.config import ResolvedAppConfig, StageAdapterConfig
from semantic_roundtrip.config_resolution import resolve_stage_adapter


@dataclass(frozen=True, slots=True)
class AdapterBundle:
    """Adapters required by one configured direct or description pipeline."""

    prompt_generator: PromptGenerator
    image_generator: ImageGenerator
    image_verifier: ImageVerifier
    image_describer: ImageDescriber | None
    image_title_guesser: ImageTitleGuesser | None
    text_title_guesser: TextTitleGuesser | None


PromptGeneratorBuilder = Callable[[dict[str, Any]], PromptGenerator]
ImageGeneratorBuilder = Callable[[dict[str, Any]], ImageGenerator]
ImageVerifierBuilder = Callable[[dict[str, Any]], ImageVerifier]
ImageDescriberBuilder = Callable[[dict[str, Any]], ImageDescriber]
ImageTitleGuesserBuilder = Callable[[dict[str, Any]], ImageTitleGuesser]
TextTitleGuesserBuilder = Callable[[dict[str, Any]], TextTitleGuesser]


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

IMAGE_DESCRIBERS: dict[str, ImageDescriberBuilder] = {
    "mock": build_mock_image_describer,
    "openai_compatible": build_openai_compatible_image_describer,
}

IMAGE_TITLE_GUESSERS: dict[str, ImageTitleGuesserBuilder] = {
    "mock": build_mock_image_title_guesser,
    "openai_compatible": build_openai_compatible_image_title_guesser,
}

TEXT_TITLE_GUESSERS: dict[str, TextTitleGuesserBuilder] = {
    "mock": build_mock_text_title_guesser,
    "openai_compatible": build_openai_compatible_text_title_guesser,
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


def create_image_describer(
    selection: StageAdapterConfig,
) -> ImageDescriber:
    builder = IMAGE_DESCRIBERS.get(selection.adapter)
    if builder is None:
        raise _unsupported_adapter(
            stage="image-description",
            adapter=selection.adapter,
            registry=IMAGE_DESCRIBERS,
        )
    return builder(selection.settings)


def create_text_title_guesser(
    selection: StageAdapterConfig,
) -> TextTitleGuesser:
    builder = TEXT_TITLE_GUESSERS.get(selection.adapter)
    if builder is None:
        raise _unsupported_adapter(
            stage="description title-guessing",
            adapter=selection.adapter,
            registry=TEXT_TITLE_GUESSERS,
        )
    return builder(selection.settings)


def create_adapters(config: ResolvedAppConfig) -> AdapterBundle:
    """Create only the adapters required by the configured pipeline route."""
    prompt_generator = create_prompt_generator(
        resolve_stage_adapter(config, "prompt_generation")
    )
    image_generator = create_image_generator(
        resolve_stage_adapter(config, "image_generation")
    )
    image_verifier = create_image_verifier(
        resolve_stage_adapter(config, "verification")
    )

    if config.stages.title_guessing.input == "image":
        return AdapterBundle(
            prompt_generator=prompt_generator,
            image_generator=image_generator,
            image_verifier=image_verifier,
            image_describer=None,
            image_title_guesser=create_image_title_guesser(
                resolve_stage_adapter(config, "title_guessing")
            ),
            text_title_guesser=None,
        )

    return AdapterBundle(
        prompt_generator=prompt_generator,
        image_generator=image_generator,
        image_verifier=image_verifier,
        image_describer=create_image_describer(
            resolve_stage_adapter(config, "image_description")
        ),
        image_title_guesser=None,
        text_title_guesser=create_text_title_guesser(
            resolve_stage_adapter(config, "title_guessing")
        ),
    )
