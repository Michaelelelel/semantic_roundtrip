"""Deterministic adapters for local tests without models or network services."""

import json
from hashlib import sha256
from pathlib import Path

from PIL import Image

from semantic_roundtrip.domain import (
    GeneratedPrompt,
    ImageArtifact,
    TitlePrediction,
    VerificationResult,
)


class MockPromptGenerator:
    """Generate deterministic visual prompts without calling a text model."""

    def generate_prompts(
        self,
        *,
        title: str,
        domain: str | None,
        count: int,
    ) -> list[GeneratedPrompt]:
        """Return exactly ``count`` mock visual prompts."""
        domain_context = f" in the {domain} domain" if domain else ""

        prompts = []
        for index in range(count):
            text = f"Mock visual prompt {index + 1} for {title}{domain_context}"
            raw_response = json.dumps(
                {
                    "index": index,
                    "text": text,
                }
            )
            prompts.append(
                GeneratedPrompt(
                    index=index,
                    text=text,
                    raw_response=raw_response,
                )
            )

        return prompts


class MockImageGenerator:
    """Create small deterministic PNG images without an image model."""

    def generate_image(
        self,
        *,
        prompt: str,
        seed: int,
        output_directory: Path,
    ) -> ImageArtifact:
        """Create one PNG whose filename and colour depend on prompt and seed."""
        output_directory.mkdir(parents=True, exist_ok=True)

        identifier = sha256(f"{prompt}\0{seed}".encode()).hexdigest()[:16]
        image_path = output_directory / f"mock_{identifier}_seed_{seed}.png"

        if image_path.exists():
            raise FileExistsError(f"Mock image already exists: {image_path}")

        colour = (0, 0, 255)
        image = Image.new("RGB", (64, 64), color=colour)
        image.save(image_path, format="PNG")

        backend_job_id = f"mock-{identifier}"
        raw_response = json.dumps(
            {
                "backend_job_id": backend_job_id,
                "path": image_path.name,
                "seed": seed,
            }
        )

        return ImageArtifact(
            path=image_path,
            seed=seed,
            raw_response=raw_response,
            backend_job_id=backend_job_id,
        )


class MockImageVerifier:
    """Return a configured verification decision for any valid image file."""

    def verify_image(
        self,
        *,
        image_path: Path,
    ) -> VerificationResult:
        """Validate that the image exists, then return the configured result."""
        with Image.open(image_path) as image:
            image.verify()

        raw_response = json.dumps(
            {
                "passed": True,
                "reason": None,
            }
        )

        return VerificationResult(
            passed=True,
            reason=None,
            raw_response=raw_response,
        )


class MockTitleGuesser:
    """Return a configured title prediction without calling a vision model."""

    def guess_title(
        self,
        *,
        image_path: Path,
        domain: str | None,
    ) -> TitlePrediction:
        """Validate the image, then return the configured prediction."""
        with Image.open(image_path) as image:
            image.verify()

        raw_response = json.dumps(
            {
                "title": "Mock Title",
                "confidence": 0.5,
                "domain": domain,
            }
        )

        return TitlePrediction(
            title="Mock Title",
            confidence=0.5,
            confidence_type="mock_probability",
            raw_response=raw_response,
        )
