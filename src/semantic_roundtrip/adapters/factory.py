"""Create configured adapters without exposing provider logic to the pipeline."""

from dataclasses import dataclass

from semantic_roundtrip.adapters.base import (
    ImageGenerator,
    ImageVerifier,
    PromptGenerator,
    TitleGuesser,
)
from semantic_roundtrip.adapters.mock import (
    MockImageGenerator,
    MockImageVerifier,
    MockPromptGenerator,
    MockTitleGuesser,
)
from semantic_roundtrip.config import StageConfig, StagesConfig


@dataclass(frozen=True, slots=True)
class AdapterBundle:
    """The four adapters required by one pipeline run."""

    prompt_generator: PromptGenerator
    image_generator: ImageGenerator
    image_verifier: ImageVerifier
    title_guesser: TitleGuesser


def create_prompt_generator(prompt_generation: StageConfig) -> PromptGenerator:
    """Create the configured title-to-prompt adapter."""
    if prompt_generation.adapter == "mock":
        return MockPromptGenerator()

    raise ValueError(f"Unsupported prompt-generation adapter: {prompt_generation.adapter}")


def create_image_generator(image_generation: StageConfig) -> ImageGenerator:
    """Create the configured prompt-to-image adapter."""
    if image_generation.adapter == "mock":
        return MockImageGenerator()

    raise ValueError(f"Unsupported verification adapter: {image_generation.adapter}")


def create_image_verifier(verification: StageConfig) -> ImageVerifier:
    """Create the configured image-verification adapter."""
    if verification.adapter == "mock":
        return MockImageVerifier()

    raise ValueError(f"Unsupported verification adapter: {verification.adapter}")


def create_title_guesser(title_guessing: StageConfig) -> TitleGuesser:
    """Create the configured image-to-title adapter."""
    if title_guessing.adapter == "mock":
        return MockTitleGuesser()

    raise ValueError(f"Unsupported title-guessing adapter: {title_guessing.adapter}")


def create_adapters(config: StagesConfig) -> AdapterBundle:
    """Create all adapters."""
    return AdapterBundle(
        prompt_generator=create_prompt_generator(config.prompt_generation),
        image_generator=create_image_generator(config.image_generation),
        image_verifier=create_image_verifier(config.verification),
        title_guesser=create_title_guesser(config.title_guessing),
    )
