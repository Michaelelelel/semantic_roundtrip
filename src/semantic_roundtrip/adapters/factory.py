"""Create independently configured provider adapters."""

from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

from semantic_roundtrip.adapters.base import (
    IllustratabilityRater,
    ImageDescriber,
    ImageGenerator,
    ImageTitleGuesser,
    ImageVerifier,
    PromptGenerator,
    TextTitleGuesser,
)
from semantic_roundtrip.adapters.comfyui import build_comfyui_image_generator
from semantic_roundtrip.adapters.mock import (
    build_mock_illustratability_rater,
    build_mock_image_describer,
    build_mock_image_generator,
    build_mock_image_title_guesser,
    build_mock_image_verifier,
    build_mock_prompt_generator,
    build_mock_text_title_guesser,
)
from semantic_roundtrip.adapters.openai_compatible import (
    build_openai_compatible_illustratability_rater,
    build_openai_compatible_image_describer,
    build_openai_compatible_image_title_guesser,
    build_openai_compatible_image_verifier,
    build_openai_compatible_prompt_generator,
    build_openai_compatible_text_title_guesser,
)
from semantic_roundtrip.config import (
    ImageVerificationPolicy,
    ResolvedAppConfig,
    StageAdapterConfig,
)
from semantic_roundtrip.config_resolution import (
    configured_image_verification_policies,
    resolve_stage_adapter,
)


@dataclass(frozen=True, slots=True)
class AdapterBundle:
    """Adapters required by the configured title-reconstruction routes."""

    illustratability_rater: IllustratabilityRater | None
    prompt_generator: PromptGenerator | None
    image_generator: ImageGenerator | None
    image_verifiers: dict[ImageVerificationPolicy, ImageVerifier]
    image_describer: ImageDescriber | None
    image_title_guesser: ImageTitleGuesser | None
    text_title_guesser: TextTitleGuesser | None


IllustratabilityRaterBuilder = Callable[[dict[str, Any]], IllustratabilityRater]
PromptGeneratorBuilder = Callable[[dict[str, Any]], PromptGenerator]
ImageGeneratorBuilder = Callable[[dict[str, Any]], ImageGenerator]
ImageVerifierBuilder = Callable[
    [dict[str, Any], ImageVerificationPolicy], ImageVerifier
]
ImageDescriberBuilder = Callable[[dict[str, Any]], ImageDescriber]
ImageTitleGuesserBuilder = Callable[[dict[str, Any]], ImageTitleGuesser]
TextTitleGuesserBuilder = Callable[[dict[str, Any]], TextTitleGuesser]


ILLUSTRATABILITY_RATERS: dict[str, IllustratabilityRaterBuilder] = {
    "mock": build_mock_illustratability_rater,
    "openai_compatible": build_openai_compatible_illustratability_rater,
}


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


def create_illustratability_rater(
    selection: StageAdapterConfig,
) -> IllustratabilityRater:
    builder = ILLUSTRATABILITY_RATERS.get(selection.adapter)
    if builder is None:
        raise _unsupported_adapter(
            stage="illustratability-rating",
            adapter=selection.adapter,
            registry=ILLUSTRATABILITY_RATERS,
        )
    return builder(selection.settings)


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
    policy: ImageVerificationPolicy,
) -> ImageVerifier:
    builder = IMAGE_VERIFIERS.get(selection.adapter)
    if builder is None:
        raise _unsupported_adapter(
            stage="verification",
            adapter=selection.adapter,
            registry=IMAGE_VERIFIERS,
        )
    return builder(selection.settings, policy)


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
    """Create only the adapters required by the configured pipeline routes."""
    return AdapterBundle(
        illustratability_rater=(
            None
            if config.stages.illustratability_rating is None
            else create_illustratability_rater(
                resolve_stage_adapter(config, "illustratability_rating")
            )
        ),
        prompt_generator=(
            None
            if config.stages.prompt_generation is None
            else create_prompt_generator(
                resolve_stage_adapter(config, "prompt_generation")
            )
        ),
        image_generator=(
            None
            if config.stages.image_generation is None
            else create_image_generator(
                resolve_stage_adapter(config, "image_generation")
            )
        ),
        image_verifiers={
            policy: create_image_verifier(
                resolve_stage_adapter(
                    config,
                    "verification",
                    image_verification_policy=policy,
                ),
                policy,
            )
            for policy in configured_image_verification_policies(config)
        },
        image_describer=(
            None
            if config.stages.image_description is None
            else create_image_describer(
                resolve_stage_adapter(config, "image_description")
            )
        ),
        image_title_guesser=(
            None
            if (
                config.stages.title_guessing is None
                or config.stages.title_guessing.direct is None
            )
            else create_image_title_guesser(
                resolve_stage_adapter(config, "title_guessing_direct")
            )
        ),
        text_title_guesser=(
            None
            if (
                config.stages.title_guessing is None
                or config.stages.title_guessing.from_description is None
            )
            else create_text_title_guesser(
                resolve_stage_adapter(config, "title_guessing_from_description")
            )
        ),
    )
