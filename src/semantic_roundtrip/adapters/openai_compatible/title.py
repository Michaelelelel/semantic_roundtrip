"""Text-input title guessing through an OpenAI-compatible chat endpoint."""

import math
from pathlib import Path
from string import Template
from typing import Any

from semantic_roundtrip.adapters.errors import AdapterError
from semantic_roundtrip.adapters.openai_compatible.client import (
    ChatCompletion,
    ChatMessage,
    OpenAICompatibleChatClient,
)
from semantic_roundtrip.adapters.openai_compatible.settings import (
    OpenAICompatibleStageSettings,
)
from semantic_roundtrip.domain import TitlePrediction


def title_prediction_from_completion(
    completion: ChatCompletion,
) -> TitlePrediction:
    """Convert one chat completion into a title prediction."""
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


class OpenAICompatibleTextTitleGuesser:
    """Guess a title from a stored description without receiving the image."""

    def __init__(self, settings: OpenAICompatibleStageSettings) -> None:
        self._config = settings
        self._template = Template(
            Path(settings.template_path).read_text(encoding="utf-8")
        )
        self._client = OpenAICompatibleChatClient(
            endpoint=settings.endpoint,
            model_id=settings.model_id,
            timeout_seconds=settings.timeout_seconds,
            error_subject="Description title guessing",
        )

    def guess_title(
        self,
        *,
        description: str,
        domain: str | None,
    ) -> TitlePrediction:
        completion = self._client.complete(
            messages=(
                ChatMessage(
                    role="user",
                    content=self._template.substitute(
                        description=description,
                        domain=domain or "",
                    ),
                ),
            ),
            temperature=self._config.temperature,
            top_p=self._config.top_p,
            max_tokens=self._config.max_tokens,
            include_token_logprobs=True,
        )
        return title_prediction_from_completion(completion)


def build_openai_compatible_text_title_guesser(
    raw_settings: dict[str, Any],
) -> OpenAICompatibleTextTitleGuesser:
    settings = OpenAICompatibleStageSettings.model_validate(raw_settings)
    return OpenAICompatibleTextTitleGuesser(settings)
