"""Provider-independent contracts for the semantic round-trip stages."""

from pathlib import Path
from typing import Protocol

from semantic_roundtrip.domain import (
    ImageDescription,
    ImageArtifact,
    PromptMessage,
    PromptResponse,
    TitlePrediction,
    VerificationResult,
)


class PromptGenerator(Protocol):
    """Generate one image prompt from provider-independent messages."""

    def generate_prompt(
        self,
        *,
        messages: tuple[PromptMessage, ...],
        seed: int,
    ) -> PromptResponse:
        """Return one image prompt and its raw provider response."""
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


class ImageDescriber(Protocol):
    """Describe an image without access to its source title."""

    def describe_image(
        self,
        *,
        image_path: Path,
        domain: str | None,
    ) -> ImageDescription:
        """Return a stored textual representation of one image."""
        ...


class ImageTitleGuesser(Protocol):
    """Guess a title directly from an image and optional domain context."""

    def guess_title(
        self,
        *,
        image_path: Path,
        domain: str | None,
    ) -> TitlePrediction:
        """Return one best title guess without access to the source title."""
        ...


class TextTitleGuesser(Protocol):
    """Guess a title from a stored image description."""

    def guess_title(
        self,
        *,
        description: str,
        domain: str | None,
    ) -> TitlePrediction:
        """Return one best title guess without access to the image or source title."""
        ...
