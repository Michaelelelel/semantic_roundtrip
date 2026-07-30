"""Deterministic adapters for local runs without models or network services."""

import json
import time
from hashlib import sha256
from pathlib import Path
from typing import Any

from PIL import Image
from pydantic import Field

from semantic_roundtrip.config import ConfigModel
from semantic_roundtrip.domain import (
    ImageArtifact,
    PromptMessage,
    PromptResponse,
    TitlePrediction,
    VerificationResult,
)


class MockAdapterSettings(ConfigModel):
    """Settings shared by all deterministic mock adapters."""

    delay_seconds: float = Field(default=0.0, ge=0)


class MockPromptGenerator:
    """Generate one simple image prompt without calling a model."""

    def __init__(self, delay_seconds: float = 0.0) -> None:
        self._delay_seconds = delay_seconds

    def generate_prompt(
        self,
        *,
        messages: tuple[PromptMessage, ...],
        seed: int,
    ) -> PromptResponse:
        """Return one fixed mock prompt."""
        time.sleep(self._delay_seconds)
        text = "Mock visual prompt"
        request_id = "mock-prompt"
        raw_response = json.dumps({"prompt": text, "seed": seed})

        return PromptResponse(
            text=text,
            raw_response=raw_response,
            backend_request_id=request_id,
        )


class MockImageGenerator:
    """Create small deterministic PNG images without an image model."""

    def __init__(self, delay_seconds: float = 0.0) -> None:
        self._delay_seconds = delay_seconds

    def generate_image(
        self,
        *,
        prompt: str,
        seed: int,
        output_directory: Path,
    ) -> ImageArtifact:
        """Create one deterministic blue PNG."""
        time.sleep(self._delay_seconds)
        output_directory.mkdir(parents=True, exist_ok=True)

        identifier = sha256(f"{prompt}\0{seed}".encode()).hexdigest()[:16]
        image_path = output_directory / f"mock_{identifier}_seed_{seed}.png"
        backend_job_id = f"mock-{identifier}"
        raw_response = json.dumps(
            {
                "backend_job_id": backend_job_id,
                "path": image_path.name,
                "seed": seed,
            }
        )

        if not image_path.exists():
            image = Image.new("RGB", (64, 64), color=(0, 0, 255))
            image.save(image_path, format="PNG")

        return ImageArtifact(
            path=image_path,
            seed=seed,
            raw_response=raw_response,
            backend_job_id=backend_job_id,
        )


class MockImageVerifier:
    """Accept any valid image without calling a vision model."""

    def __init__(self, delay_seconds: float = 0.0) -> None:
        self._delay_seconds = delay_seconds

    def verify_image(self, *, image_path: Path) -> VerificationResult:
        """Validate the image and return a successful decision."""
        time.sleep(self._delay_seconds)
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


class MockImageTitleGuesser:
    """Return a fixed prediction directly from an image."""

    def __init__(self, delay_seconds: float = 0.0) -> None:
        self._delay_seconds = delay_seconds

    def guess_title(
        self,
        *,
        image_path: Path,
        domain: str | None,
    ) -> TitlePrediction:
        """Validate the image and return the fixed mock prediction."""
        time.sleep(self._delay_seconds)
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


def _load_mock_settings(raw_settings: dict[str, Any]) -> MockAdapterSettings:
    return MockAdapterSettings.model_validate(raw_settings)


def build_mock_prompt_generator(
    raw_settings: dict[str, Any],
) -> MockPromptGenerator:
    settings = _load_mock_settings(raw_settings)
    return MockPromptGenerator(settings.delay_seconds)


def build_mock_image_generator(
    raw_settings: dict[str, Any],
) -> MockImageGenerator:
    settings = _load_mock_settings(raw_settings)
    return MockImageGenerator(settings.delay_seconds)


def build_mock_image_verifier(
    raw_settings: dict[str, Any],
) -> MockImageVerifier:
    settings = _load_mock_settings(raw_settings)
    return MockImageVerifier(settings.delay_seconds)


def build_mock_image_title_guesser(
    raw_settings: dict[str, Any],
) -> MockImageTitleGuesser:
    settings = _load_mock_settings(raw_settings)
    return MockImageTitleGuesser(settings.delay_seconds)
