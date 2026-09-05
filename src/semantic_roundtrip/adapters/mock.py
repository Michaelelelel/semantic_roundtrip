"""Deterministic adapters for local runs without models or network services."""

import json
import time
from hashlib import sha256
from pathlib import Path
from typing import Any

from PIL import Image
from pydantic import Field

from semantic_roundtrip.config import ConfigModel, ImageVerificationPolicy
from semantic_roundtrip.domain import (
    IllustratabilityRating,
    ImageArtifact,
    ImageDescription,
    PromptMessage,
    PromptResponse,
    TitlePrediction,
    VerificationDecision,
)
from semantic_roundtrip.evaluation import (
    STRICT_IMAGE_VERIFICATION_METHOD,
    TITLE_AWARE_IMAGE_VERIFICATION_METHOD,
)


class MockAdapterSettings(ConfigModel):
    """Settings shared by all deterministic mock adapters."""

    delay_seconds: float = Field(default=0.0, ge=0)
    prompt_profile: Path | None = None
    seed: int | None = Field(default=None, ge=0)
    temperature: float | None = Field(default=None, ge=0)
    top_p: float | None = Field(default=None, gt=0, le=1)
    top_k: int | None = Field(default=None, ge=0)
    min_p: float | None = Field(default=None, ge=0, le=1)
    repeat_penalty: float | None = Field(default=None, gt=0)
    presence_penalty: float | None = Field(default=None, ge=-2, le=2)
    frequency_penalty: float | None = Field(default=None, ge=-2, le=2)
    max_tokens: int | None = Field(default=None, gt=0)


class MockIllustratabilityRater:
    """Return one deterministic valid rating for pipeline smoke tests."""

    def __init__(self, delay_seconds: float = 0.0) -> None:
        self._delay_seconds = delay_seconds

    def rate(
        self,
        *,
        messages: tuple[PromptMessage, ...],
        seed: int,
    ) -> IllustratabilityRating:
        time.sleep(self._delay_seconds)
        score = 50
        return IllustratabilityRating(
            score=score,
            raw_response=json.dumps(
                {
                    "score": score,
                    "seed": seed,
                    "messages": [message.content for message in messages],
                }
            ),
            backend_request_id="mock-illustratability",
        )


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

    def __init__(
        self,
        delay_seconds: float = 0.0,
        policy: ImageVerificationPolicy = "strict",
    ) -> None:
        self._delay_seconds = delay_seconds
        self._policy = policy

    def verify_image(
        self,
        *,
        image_path: Path,
        reference_title: str | None = None,
    ) -> VerificationDecision:
        """Validate the image and return a successful decision."""
        if self._policy == "title_aware" and reference_title is None:
            raise ValueError("Title-aware image verification requires a title.")
        time.sleep(self._delay_seconds)
        with Image.open(image_path) as image:
            image.verify()

        raw_response = json.dumps(
            {
                "passed": True,
                "reason": None,
            }
        )

        method = (
            STRICT_IMAGE_VERIFICATION_METHOD
            if self._policy == "strict"
            else TITLE_AWARE_IMAGE_VERIFICATION_METHOD
        )
        return VerificationDecision(
            passed=True,
            reason=None,
            raw_response=raw_response,
            method=method,
        )


class MockImageDescriber:
    """Return a fixed description after validating the generated image."""

    def __init__(self, delay_seconds: float = 0.0) -> None:
        self._delay_seconds = delay_seconds

    def describe_image(
        self,
        *,
        image_path: Path,
        domain: str | None,
    ) -> ImageDescription:
        time.sleep(self._delay_seconds)
        with Image.open(image_path) as image:
            image.verify()

        text = "A plain blue square."
        raw_response = json.dumps({"description": text, "domain": domain})
        return ImageDescription(
            text=text,
            raw_response=raw_response,
            backend_request_id="mock-description",
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


class MockTextTitleGuesser:
    """Return a fixed prediction from a stored description."""

    def __init__(self, delay_seconds: float = 0.0) -> None:
        self._delay_seconds = delay_seconds

    def guess_title(
        self,
        *,
        description: str,
        domain: str | None,
    ) -> TitlePrediction:
        time.sleep(self._delay_seconds)
        raw_response = json.dumps(
            {
                "title": "Mock Title",
                "confidence": 0.5,
                "domain": domain,
                "description": description,
            }
        )
        return TitlePrediction(
            title="Mock Title",
            confidence=0.5,
            confidence_type="mock_probability",
            raw_response=raw_response,
        )


class MockPromptTitleGuesser:
    """Return a deterministic prompt-level prediction without an image."""

    def __init__(self, delay_seconds: float = 0.0) -> None:
        self._delay_seconds = delay_seconds

    def guess_title(self, *, prompt: str, domain: str | None) -> TitlePrediction:
        time.sleep(self._delay_seconds)
        return TitlePrediction(
            title="Mock Title",
            confidence=0.5,
            confidence_type="mock_probability",
            raw_response=json.dumps(
                {"title": "Mock Title", "prompt": prompt, "domain": domain}
            ),
        )


def build_mock_prompt_title_guesser(
    raw_settings: dict[str, Any],
) -> MockPromptTitleGuesser:
    settings = _load_mock_settings(raw_settings)
    return MockPromptTitleGuesser(settings.delay_seconds)


def _load_mock_settings(raw_settings: dict[str, Any]) -> MockAdapterSettings:
    return MockAdapterSettings.model_validate(raw_settings)


def build_mock_prompt_generator(
    raw_settings: dict[str, Any],
) -> MockPromptGenerator:
    settings = _load_mock_settings(raw_settings)
    return MockPromptGenerator(settings.delay_seconds)


def build_mock_illustratability_rater(
    raw_settings: dict[str, Any],
) -> MockIllustratabilityRater:
    settings = _load_mock_settings(raw_settings)
    return MockIllustratabilityRater(settings.delay_seconds)


def build_mock_image_generator(
    raw_settings: dict[str, Any],
) -> MockImageGenerator:
    settings = _load_mock_settings(raw_settings)
    return MockImageGenerator(settings.delay_seconds)


def build_mock_image_verifier(
    raw_settings: dict[str, Any],
    policy: ImageVerificationPolicy,
) -> MockImageVerifier:
    settings = _load_mock_settings(raw_settings)
    return MockImageVerifier(settings.delay_seconds, policy)


def build_mock_image_describer(
    raw_settings: dict[str, Any],
) -> MockImageDescriber:
    settings = _load_mock_settings(raw_settings)
    return MockImageDescriber(settings.delay_seconds)


def build_mock_image_title_guesser(
    raw_settings: dict[str, Any],
) -> MockImageTitleGuesser:
    settings = _load_mock_settings(raw_settings)
    return MockImageTitleGuesser(settings.delay_seconds)


def build_mock_text_title_guesser(
    raw_settings: dict[str, Any],
) -> MockTextTitleGuesser:
    settings = _load_mock_settings(raw_settings)
    return MockTextTitleGuesser(settings.delay_seconds)
