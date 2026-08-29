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
    if completion.finish_reason == "length":
        raise AdapterError(
            "Title response was truncated because the token limit was reached.",
            completion.raw_response,
        )

    guessed_title = completion.content.strip()
    if not guessed_title:
        raise AdapterError(
            "Title guesser returned an empty response.",
            completion.raw_response,
        )

    answer_likelihood = None
    if completion.visible_content_token_logprobs:
        answer_likelihood = math.exp(
            sum(completion.visible_content_token_logprobs)
            / len(completion.visible_content_token_logprobs)
        )

    return TitlePrediction(
        title=guessed_title,
        confidence=answer_likelihood,
        confidence_type=(
            "visible_answer_geometric_mean_token_probability"
            if answer_likelihood is not None
            else None
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
            api_key_env=settings.api_key_env,
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


def build_openai_compatible_text_title_guesser(
    raw_settings: dict[str, Any],
) -> OpenAICompatibleTextTitleGuesser:
    settings = OpenAICompatibleStageSettings.model_validate(raw_settings)
    return OpenAICompatibleTextTitleGuesser(settings)
