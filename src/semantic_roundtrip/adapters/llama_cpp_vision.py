"""llama.cpp multimodal adapters using the explicit media-marker payload."""

import base64
import json
import math
from pathlib import Path
from string import Template
from typing import Any, Literal

import requests
from pydantic import Field

from semantic_roundtrip.adapters.errors import AdapterError
from semantic_roundtrip.config import ConfigModel
from semantic_roundtrip.domain import TitlePrediction, VerificationResult


class LlamaCppVisionVerifierSettings(ConfigModel):
    """Settings for llama.cpp image verification."""

    endpoint: str = Field(min_length=1)
    model_id: str = Field(min_length=1)
    template_path: Path
    parser_version: Literal["json_object_v1"] = "json_object_v1"
    media_marker: str = "<__media__>"
    temperature: float = Field(default=0.0, ge=0)
    top_k: int = Field(default=1, gt=0)
    max_tokens: int = Field(default=128, gt=0)
    timeout_seconds: float = Field(default=300, gt=0)


class LlamaCppTitleGuesserSettings(ConfigModel):
    """Settings for llama.cpp title guessing."""

    endpoint: str = Field(min_length=1)
    model_id: str = Field(min_length=1)
    template_path: Path
    media_marker: str = "<__media__>"
    temperature: float = Field(default=0.0, ge=0)
    top_k: int = Field(default=1, gt=0)
    max_tokens: int = Field(default=64, gt=0)
    timeout_seconds: float = Field(default=300, gt=0)


VisionSettings = LlamaCppVisionVerifierSettings | LlamaCppTitleGuesserSettings


class LlamaCppVisionClient:
    """Send one image and question to llama.cpp's multimodal endpoint."""

    def __init__(self, settings: VisionSettings) -> None:
        self._config = settings
        self._session = requests.Session()

    def complete(
        self,
        *,
        image_path: Path,
        question: str,
    ) -> tuple[dict[str, Any], str]:
        image_base64 = base64.b64encode(image_path.read_bytes()).decode("ascii")
        prompt = (
            "A chat between a curious user and an artificial intelligence "
            "assistant. The assistant gives helpful, detailed, and polite "
            "answers to the user's questions. "
            f"USER: {self._config.media_marker}\n"
            f"{question}\nASSISTANT:"
        )
        payload = {
            "prompt": {
                "prompt_string": prompt,
                "multimodal_data": [image_base64],
            },
            "temperature": self._config.temperature,
            "top_k": self._config.top_k,
            "n_predict": self._config.max_tokens,
            "n_probs": 1,
            "stop": ["USER:"],
        }

        try:
            response = self._session.post(
                self._config.endpoint,
                json=payload,
                timeout=self._config.timeout_seconds,
            )
        except requests.RequestException as error:
            raise AdapterError(f"Vision request failed: {error}") from error

        raw_response = response.text
        try:
            response.raise_for_status()
            result = response.json()
            if not isinstance(result, dict) or not isinstance(
                result.get("content"),
                str,
            ):
                raise TypeError("missing text content")
        except (requests.HTTPError, TypeError, ValueError) as error:
            raise AdapterError(
                "llama.cpp returned an invalid multimodal response.",
                raw_response,
            ) from error
        return result, raw_response


class LlamaCppImageVerifier:
    """Verify image suitability with a llama.cpp vision model."""

    def __init__(self, settings: LlamaCppVisionVerifierSettings) -> None:
        self._config = settings
        self._template = Template(
            Path(settings.template_path).read_text(encoding="utf-8")
        )
        self._client = LlamaCppVisionClient(settings)

    def verify_image(self, *, image_path: Path) -> VerificationResult:
        question = self._template.substitute()
        result, raw_response = self._client.complete(
            image_path=image_path,
            question=question,
        )
        content = result["content"].strip()

        try:
            parsed = json.loads(content)
            passed = parsed["passed"]
            reason = parsed.get("reason")
            if not isinstance(passed, bool):
                raise TypeError("'passed' is not a boolean")
            if reason is not None and not isinstance(reason, str):
                raise TypeError("'reason' is not text or null")
        except (KeyError, TypeError, json.JSONDecodeError) as error:
            raise AdapterError(
                "Verifier response is not valid json_object_v1.",
                raw_response,
            ) from error

        return VerificationResult(
            passed=passed,
            reason=reason,
            raw_response=raw_response,
        )


class LlamaCppTitleGuesser:
    """Guess a title and retain llama.cpp token confidence metadata."""

    def __init__(self, settings: LlamaCppTitleGuesserSettings) -> None:
        self._template = Template(
            Path(settings.template_path).read_text(encoding="utf-8")
        )
        self._client = LlamaCppVisionClient(settings)

    def guess_title(
        self,
        *,
        image_path: Path,
        domain: str | None,
    ) -> TitlePrediction:
        question = self._template.substitute(domain=domain or "")
        result, raw_response = self._client.complete(
            image_path=image_path,
            question=question,
        )
        guessed_title = result["content"].strip()
        token_logprobs = [
            token["logprob"]
            for token in result.get("completion_probabilities", [])
            if isinstance(token, dict) and token.get("logprob") is not None
        ]
        confidence = None
        if token_logprobs:
            confidence = math.exp(sum(token_logprobs) / len(token_logprobs))

        return TitlePrediction(
            title=guessed_title,
            confidence=confidence,
            confidence_type=(
                "geometric_mean_token_probability" if confidence is not None else None
            ),
            raw_response=raw_response,
        )


def build_llama_cpp_image_verifier(
    raw_settings: dict[str, Any],
) -> LlamaCppImageVerifier:
    settings = LlamaCppVisionVerifierSettings.model_validate(raw_settings)
    return LlamaCppImageVerifier(settings)


def build_llama_cpp_title_guesser(
    raw_settings: dict[str, Any],
) -> LlamaCppTitleGuesser:
    settings = LlamaCppTitleGuesserSettings.model_validate(raw_settings)
    return LlamaCppTitleGuesser(settings)
