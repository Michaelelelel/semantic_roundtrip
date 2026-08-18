"""Vision stages using an OpenAI-compatible multimodal chat endpoint."""

import json
from pathlib import Path
from string import Template
from typing import Any

from semantic_roundtrip.adapters.errors import AdapterError
from semantic_roundtrip.adapters.openai_compatible.client import (
    ChatMessage,
    ImageContent,
    OpenAICompatibleChatClient,
    TextContent,
    image_file_data_url,
)
from semantic_roundtrip.adapters.openai_compatible.settings import (
    OpenAICompatibleStageSettings,
)
from semantic_roundtrip.adapters.openai_compatible.title import (
    title_prediction_from_completion,
)
from semantic_roundtrip.domain import (
    ImageDescription,
    TitlePrediction,
    VerificationResult,
)


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

    def __init__(self, settings: OpenAICompatibleStageSettings) -> None:
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
            seed=self._config.seed,
            response_format=VERIFICATION_RESPONSE_FORMAT,
            reasoning_effort=self._config.reasoning_effort,
            chat_template_kwargs=self._config.chat_template_kwargs,
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


class OpenAICompatibleImageDescriber:
    """Describe an image without receiving its source title."""

    def __init__(self, settings: OpenAICompatibleStageSettings) -> None:
        self._config = settings
        self._template = Template(
            Path(settings.template_path).read_text(encoding="utf-8")
        )
        self._client = OpenAICompatibleChatClient(
            endpoint=settings.endpoint,
            model_id=settings.model_id,
            timeout_seconds=settings.timeout_seconds,
            error_subject="Image description",
        )

    def describe_image(
        self,
        *,
        image_path: Path,
        domain: str | None,
    ) -> ImageDescription:
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
            seed=self._config.seed,
            reasoning_effort=self._config.reasoning_effort,
            chat_template_kwargs=self._config.chat_template_kwargs,
        )

        description = completion.content.strip()
        if not description:
            raise AdapterError(
                "Image describer returned an empty response.",
                completion.raw_response,
            )
        if completion.finish_reason == "length":
            raise AdapterError(
                "Image description was truncated because the token limit was reached.",
                completion.raw_response,
            )

        return ImageDescription(
            text=description,
            raw_response=completion.raw_response,
            backend_request_id=completion.request_id,
        )


class OpenAICompatibleImageTitleGuesser:
    """Guess a title directly from an image and retain confidence metadata."""

    def __init__(self, settings: OpenAICompatibleStageSettings) -> None:
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
            seed=self._config.seed,
            include_token_logprobs=True,
            reasoning_effort=self._config.reasoning_effort,
            chat_template_kwargs=self._config.chat_template_kwargs,
        )

        return title_prediction_from_completion(completion)


def build_openai_compatible_image_verifier(
    raw_settings: dict[str, Any],
) -> OpenAICompatibleImageVerifier:
    settings = OpenAICompatibleStageSettings.model_validate(raw_settings)
    return OpenAICompatibleImageVerifier(settings)


def build_openai_compatible_image_describer(
    raw_settings: dict[str, Any],
) -> OpenAICompatibleImageDescriber:
    settings = OpenAICompatibleStageSettings.model_validate(raw_settings)
    return OpenAICompatibleImageDescriber(settings)


def build_openai_compatible_image_title_guesser(
    raw_settings: dict[str, Any],
) -> OpenAICompatibleImageTitleGuesser:
    settings = OpenAICompatibleStageSettings.model_validate(raw_settings)
    return OpenAICompatibleImageTitleGuesser(settings)
