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
    GeneratedPrompt,
    ImageArtifact,
    PromptBatchResult,
    TitlePrediction,
    VerificationResult,
)


class MockAdapterSettings(ConfigModel):
    """Settings shared by all deterministic mock adapters."""

    delay_seconds: float = Field(default=0.0, ge=0)


class MockPromptGenerator:
    """Generate deterministic visual prompts without calling a text model."""

    def __init__(self, delay_seconds: float = 0.0) -> None:
        self._delay_seconds = delay_seconds

    def generate_prompts(
        self,
        *,
        title: str,
        domain: str | None,
        count: int,
    ) -> PromptBatchResult:
        """Return one mock batch containing exactly ``count`` prompts."""
        time.sleep(self._delay_seconds)
        domain_context = f" in the {domain} domain" if domain else ""
        texts = [
            f"Mock visual prompt {index + 1} for {title}{domain_context}"
            for index in range(count)
        ]
        backend_request_id = sha256(f"{title}\0{domain}\0{count}".encode()).hexdigest()[
            :16
        ]

        return PromptBatchResult(
            requested_count=count,
            returned_count=count,
            prompts=tuple(
                GeneratedPrompt(index=index, text=text)
                for index, text in enumerate(texts)
            ),
            raw_response=json.dumps({"prompts": texts}),
            format_valid=True,
            parser_version="mock_json_list_v1",
            backend_request_id=f"mock-{backend_request_id}",
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


class MockTitleGuesser:
    """Return a fixed prediction without calling a vision model."""

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


def build_mock_title_guesser(
    raw_settings: dict[str, Any],
) -> MockTitleGuesser:
    settings = _load_mock_settings(raw_settings)
    return MockTitleGuesser(settings.delay_seconds)
