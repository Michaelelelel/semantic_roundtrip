"""Strict illustratability ratings through an OpenAI-compatible endpoint."""

import json
from typing import Any

from semantic_roundtrip.adapters.errors import AdapterError
from semantic_roundtrip.adapters.openai_compatible.client import (
    ChatMessage,
    OpenAICompatibleChatClient,
)
from semantic_roundtrip.adapters.openai_compatible.prompt import (
    OpenAICompatiblePromptSettings,
)
from semantic_roundtrip.domain import (
    IllustratabilityRating,
    PromptMessage,
)

RATING_SCHEMA: dict[str, Any] = {
    "type": "object",
    "properties": {"score": {"type": "integer", "minimum": 0, "maximum": 100}},
    "required": ["score"],
    "additionalProperties": False,
}

RATING_RESPONSE_FORMAT: dict[str, Any] = {
    "type": "json_schema",
    "json_schema": {
        "name": "illustratability_rating",
        "strict": True,
        "schema": RATING_SCHEMA,
    },
}


class OpenAICompatibleIllustratabilityRater:
    """Estimate title illustratability while retaining the provider response."""

    def __init__(self, settings: OpenAICompatiblePromptSettings) -> None:
        self._config = settings
        self._client = OpenAICompatibleChatClient(
            endpoint=settings.endpoint,
            model_id=settings.model_id,
            timeout_seconds=settings.timeout_seconds,
            api_key_env=settings.api_key_env,
            error_subject="Illustratability rating",
        )

    def rate(
        self,
        *,
        messages: tuple[PromptMessage, ...],
        seed: int,
    ) -> IllustratabilityRating:
        completion = self._client.complete(
            messages=tuple(
                ChatMessage(role=message.role, content=message.content)
                for message in messages
            ),
            generation_parameters=self._config.generation_parameters(seed=seed),
            response_format=RATING_RESPONSE_FORMAT,
            stream=self._config.stream,
            reasoning_effort=self._config.reasoning_effort,
            reasoning_format=self._config.reasoning_format,
            thinking_budget_tokens=self._config.thinking_budget_tokens,
            chat_template_kwargs=self._config.chat_template_kwargs,
        )
        if completion.finish_reason == "length":
            raise AdapterError(
                "Illustratability rating was truncated because the token limit "
                "was reached.",
                completion.raw_response,
            )

        try:
            parsed = json.loads(completion.content)
            if not isinstance(parsed, dict):
                raise TypeError("response is not an object")
            if set(parsed) != {"score"}:
                raise ValueError("response contains fields other than 'score'")
            score = parsed["score"]
            if isinstance(score, bool) or not isinstance(score, int):
                raise TypeError("'score' is not an integer")
            if not 0 <= score <= 100:
                raise ValueError("'score' is outside 0 through 100")
        except (KeyError, TypeError, ValueError, json.JSONDecodeError) as error:
            raise AdapterError(
                "Illustratability response is not valid rating JSON.",
                completion.raw_response,
            ) from error

        return IllustratabilityRating(
            score=score,
            raw_response=completion.raw_response,
            backend_request_id=completion.request_id,
        )


def build_openai_compatible_illustratability_rater(
    raw_settings: dict[str, Any],
) -> OpenAICompatibleIllustratabilityRater:
    settings = OpenAICompatiblePromptSettings.model_validate(raw_settings)
    return OpenAICompatibleIllustratabilityRater(settings)
