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
from semantic_roundtrip.config import ImageVerificationPolicy
from semantic_roundtrip.domain import (
    ImageDescription,
    TitlePrediction,
    VerificationDecision,
)
from semantic_roundtrip.evaluation import (
    STRICT_IMAGE_VERIFICATION_METHOD,
    TITLE_AWARE_IMAGE_VERIFICATION_METHOD,
    normalize_title_text,
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
    "json_schema": {
        "name": "image_verification",
        "strict": True,
        "schema": VERIFICATION_SCHEMA,
    },
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

    def __init__(
        self,
        settings: OpenAICompatibleStageSettings,
        policy: ImageVerificationPolicy,
    ) -> None:
        self._config = settings
        self._policy = policy
        self._template = Template(
            Path(settings.template_path).read_text(encoding="utf-8")
        )
        identifiers = set(self._template.get_identifiers())
        title_fields = {"title", "normalized_title"}
        if policy == "strict" and identifiers & title_fields:
            raise ValueError(
                "The strict image verifier must remain blind to the title."
            )
        if policy == "title_aware" and not title_fields.issubset(identifiers):
            raise ValueError(
                "The title-aware verifier prompt must include $title and "
                "$normalized_title."
            )
        self._client = OpenAICompatibleChatClient(
            endpoint=settings.endpoint,
            model_id=settings.model_id,
            timeout_seconds=settings.timeout_seconds,
            api_key_env=settings.api_key_env,
            error_subject="Verification",
        )

    def verify_image(
        self,
        *,
        image_path: Path,
        reference_title: str | None = None,
    ) -> VerificationDecision:
        if self._policy == "title_aware" and reference_title is None:
            raise ValueError("Title-aware image verification requires a title.")
        template_values = (
            {}
            if self._policy == "strict"
            else {
                "title": reference_title,
                "normalized_title": normalize_title_text(reference_title),
            }
        )
        completion = self._client.complete(
            messages=(
                _image_message(
                    image_path=image_path,
                    instruction=self._template.substitute(template_values),
                ),
            ),
            generation_parameters=self._config.generation_parameters(),
            response_format=VERIFICATION_RESPONSE_FORMAT,
            reasoning_effort=self._config.reasoning_effort,
            reasoning_format=self._config.reasoning_format,
            thinking_budget_tokens=self._config.thinking_budget_tokens,
            chat_template_kwargs=self._config.chat_template_kwargs,
        )

        if completion.finish_reason == "length":
            raise AdapterError(
                "Verification response was truncated because the token limit was "
                "reached.",
                completion.raw_response,
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

        method = (
            STRICT_IMAGE_VERIFICATION_METHOD
            if self._policy == "strict"
            else TITLE_AWARE_IMAGE_VERIFICATION_METHOD
        )
        return VerificationDecision(
            passed=passed,
            reason=reason,
            raw_response=completion.raw_response,
            method=method,
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
            api_key_env=settings.api_key_env,
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
            generation_parameters=self._config.generation_parameters(),
            reasoning_effort=self._config.reasoning_effort,
            reasoning_format=self._config.reasoning_format,
            thinking_budget_tokens=self._config.thinking_budget_tokens,
            chat_template_kwargs=self._config.chat_template_kwargs,
        )

        if completion.finish_reason == "length":
            raise AdapterError(
                "Image description was truncated because the token limit was reached.",
                completion.raw_response,
            )

        description = completion.content.strip()
        if not description:
            raise AdapterError(
                "Image describer returned an empty response.",
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
            api_key_env=settings.api_key_env,
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
            generation_parameters=self._config.generation_parameters(),
            include_token_logprobs=self._config.request_token_logprobs,
            top_logprobs=(
                self._config.top_logprobs
                if self._config.request_token_logprobs
                else None
            ),
            reasoning_effort=self._config.reasoning_effort,
            reasoning_format=self._config.reasoning_format,
            thinking_budget_tokens=self._config.thinking_budget_tokens,
            chat_template_kwargs=self._config.chat_template_kwargs,
        )

        return title_prediction_from_completion(completion)


def build_openai_compatible_image_verifier(
    raw_settings: dict[str, Any],
    policy: ImageVerificationPolicy,
) -> OpenAICompatibleImageVerifier:
    settings = OpenAICompatibleStageSettings.model_validate(raw_settings)
    return OpenAICompatibleImageVerifier(settings, policy)


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
