"""Provider-independent contracts for the semantic round-trip stages."""

from pathlib import Path
from typing import Protocol

from semantic_roundtrip.domain import (
    GeneratedPrompt,
    ImageArtifact,
    TitlePrediction,
    VerificationResult,
)


class PromptGenerator(Protocol):
    """Generate visual prompts from a title and optional domain context."""

    def generate_prompts(
        self,
        *,
        title: str,
        domain: str | None,
        count: int,
    ) -> list[GeneratedPrompt]:
        """Return exactly ``count`` visual prompts."""
        ...


class ImageGenerator(Protocol):
    """Generate an image from a visual prompt and deterministic seed."""

    def generate_image(
        self,
        *,
        prompt: str,
        seed: int,
        output_directory: Path,
    ) -> ImageArtifact:
        """Generate and persist one image artifact."""
        ...


class ImageVerifier(Protocol):
    """Check an image for text leakage or replica suspicion."""

    def verify_image(
        self,
        *,
        image_path: Path,
    ) -> VerificationResult:
        """Return the verification decision and reason."""
        ...


class TitleGuesser(Protocol):
    """Guess a title using only the image and optional domain context."""

    def guess_title(
        self,
        *,
        image_path: Path,
        domain: str | None,
    ) -> TitlePrediction:
        """Return one best title guess without access to the source title."""
        ...
