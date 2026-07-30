"""Vision stages using an OpenAI-compatible multimodal chat endpoint."""

import json
import math
from pathlib import Path
from string import Template
from typing import Any

from pydantic import Field

from semantic_roundtrip.adapters.errors import AdapterError
from semantic_roundtrip.adapters.openai_compatible.client import (
    ChatMessage,
    ImageContent,
    OpenAICompatibleChatClient,
    TextContent,
    image_file_data_url,
)
from semantic_roundtrip.config import ConfigModel
from semantic_roundtrip.domain import TitlePrediction, VerificationResult


class OpenAICompatibleVisionSettings(ConfigModel):
    """Settings shared by OpenAI-compatible vision stages."""

    endpoint: str = Field(min_length=1)
    model_id: str = Field(min_length=1)
    template_path: Path
    temperature: float = Field(default=0.0, ge=0)
    top_p: float = Field(default=1.0, gt=0, le=1)
    max_tokens: int = Field(gt=0)
    timeout_seconds: float = Field(default=300, gt=0)


VERIFICATION_SCHEMA: dict[str, Any] = {
    "type": "object",
    "properties": {
        "passed": {"type": "boolean"},
        "reason": {"type": ["string", "null"]},
    },
    "required": ["passed", "reason"],
    "additionalProperties": False,
}

VERIFICATION_RESPONSE_FORMAT: dict[str, Any] = {
    "type": "json_schema",
    "schema": VERIFICATION_SCHEMA,
}


def _image_message(*, image_path: Path, instruction: str) -> ChatMessage:
    return ChatMessage(
        role="user",
        content=(
            ImageContent(image_file_data_url(image_path)),
            TextContent(instruction),
        ),
    )


class OpenAICompatibleImageVerifier:
    """Verify an image through OpenAI-compatible multimodal chat."""

    def __init__(self, settings: OpenAICompatibleVisionSettings) -> None:
        self._config = settings
        self._template = Template(
            Path(settings.template_path).read_text(encoding="utf-8")
        )
        self._client = OpenAICompatibleChatClient(
            endpoint=settings.endpoint,
            model_id=settings.model_id,
            timeout_seconds=settings.timeout_seconds,
            error_subject="Verification",
        )

    def verify_image(self, *, image_path: Path) -> VerificationResult:
        completion = self._client.complete(
            messages=(
                _image_message(
                    image_path=image_path,
                    instruction=self._template.substitute(),
                ),
            ),
            temperature=self._config.temperature,
            top_p=self._config.top_p,
            max_tokens=self._config.max_tokens,
            response_format=VERIFICATION_RESPONSE_FORMAT,
        )

        try:
            parsed = json.loads(completion.content)
            if not isinstance(parsed, dict):
                raise TypeError("response is not an object")

            passed = parsed["passed"]
            reason = parsed.get("reason")
            if not isinstance(passed, bool):
                raise TypeError("'passed' is not a boolean")
            if reason is not None and not isinstance(reason, str):
                raise TypeError("'reason' is not text or null")
        except (KeyError, TypeError, json.JSONDecodeError) as error:
            raise AdapterError(
                "Verifier response is not valid verification JSON.",
                completion.raw_response,
            ) from error

        return VerificationResult(
            passed=passed,
            reason=reason,
            raw_response=completion.raw_response,
        )


class OpenAICompatibleImageTitleGuesser:
    """Guess a title directly from an image and retain confidence metadata."""

    def __init__(self, settings: OpenAICompatibleVisionSettings) -> None:
        self._config = settings
        self._template = Template(
            Path(settings.template_path).read_text(encoding="utf-8")
        )
        self._client = OpenAICompatibleChatClient(
            endpoint=settings.endpoint,
            model_id=settings.model_id,
            timeout_seconds=settings.timeout_seconds,
            error_subject="Title guessing",
        )

    def guess_title(
        self,
        *,
        image_path: Path,
        domain: str | None,
    ) -> TitlePrediction:
        completion = self._client.complete(
            messages=(
                _image_message(
                    image_path=image_path,
                    instruction=self._template.substitute(domain=domain or ""),
                ),
            ),
            temperature=self._config.temperature,
            top_p=self._config.top_p,
            max_tokens=self._config.max_tokens,
            include_token_logprobs=True,
        )

        guessed_title = completion.content.strip()
        if not guessed_title:
            raise AdapterError(
                "Title guesser returned an empty response.",
                completion.raw_response,
            )

        confidence = None
        if completion.token_logprobs:
            confidence = math.exp(
                sum(completion.token_logprobs) / len(completion.token_logprobs)
            )

        return TitlePrediction(
            title=guessed_title,
            confidence=confidence,
            confidence_type=(
                "geometric_mean_token_probability" if confidence is not None else None
            ),
            raw_response=completion.raw_response,
        )


def build_openai_compatible_image_verifier(
    raw_settings: dict[str, Any],
) -> OpenAICompatibleImageVerifier:
    settings = OpenAICompatibleVisionSettings.model_validate(raw_settings)
    return OpenAICompatibleImageVerifier(settings)


def build_openai_compatible_image_title_guesser(
    raw_settings: dict[str, Any],
) -> OpenAICompatibleImageTitleGuesser:
    settings = OpenAICompatibleVisionSettings.model_validate(raw_settings)
    return OpenAICompatibleImageTitleGuesser(settings)
