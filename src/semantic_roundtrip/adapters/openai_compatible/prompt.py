"""Prompt generation through an OpenAI-compatible chat endpoint."""

from typing import Any

from pydantic import Field

from semantic_roundtrip.adapters.errors import AdapterError
from semantic_roundtrip.adapters.openai_compatible.client import (
    ChatMessage,
    OpenAICompatibleChatClient,
    ReasoningFormat,
)
from semantic_roundtrip.adapters.openai_compatible.settings import (
    OpenAICompatibleGenerationSettings,
)
from semantic_roundtrip.domain import PromptMessage, PromptResponse


class OpenAICompatiblePromptSettings(OpenAICompatibleGenerationSettings):
    """Settings for an OpenAI-compatible prompt-generation endpoint."""

    endpoint: str = Field(min_length=1)
    model_id: str = Field(min_length=1)
    api_key_env: str | None = Field(default=None, min_length=1)
    request_token_logprobs: bool = True
    temperature: float | None = Field(default=0.8, ge=0)
    top_p: float | None = Field(default=0.95, gt=0, le=1)
    max_tokens: int = Field(default=2048, gt=0)
    timeout_seconds: float = Field(default=300, gt=0)
    stream: bool = False
    reasoning_effort: str | None = Field(default=None, min_length=1)
    reasoning_format: ReasoningFormat | None = None
    thinking_budget_tokens: int | None = Field(default=None, ge=0)
    chat_template_kwargs: dict[str, Any] = Field(default_factory=dict)


class OpenAICompatiblePromptGenerator:
    """Return one image prompt from an OpenAI-compatible server."""

    def __init__(self, settings: OpenAICompatiblePromptSettings) -> None:
        self._config = settings
        self._client = OpenAICompatibleChatClient(
            endpoint=settings.endpoint,
            model_id=settings.model_id,
            timeout_seconds=settings.timeout_seconds,
            api_key_env=settings.api_key_env,
            error_subject="Prompt",
        )

    def generate_prompt(
        self,
        *,
        messages: tuple[PromptMessage, ...],
        seed: int,
    ) -> PromptResponse:
        completion = self._client.complete(
            messages=tuple(
                ChatMessage(role=message.role, content=message.content)
                for message in messages
            ),
            generation_parameters=self._config.generation_parameters(seed=seed),
            stream=self._config.stream,
            reasoning_effort=self._config.reasoning_effort,
            reasoning_format=self._config.reasoning_format,
            thinking_budget_tokens=self._config.thinking_budget_tokens,
            chat_template_kwargs=self._config.chat_template_kwargs,
        )

        if completion.finish_reason == "length":
            raise AdapterError(
                "Prompt response was truncated because the token limit was reached.",
                completion.raw_response,
            )

        text = completion.content.strip()
        if not text:
            raise AdapterError(
                "Prompt endpoint returned an empty response.",
                completion.raw_response,
            )

        return PromptResponse(
            text=text,
            raw_response=completion.raw_response,
            backend_request_id=completion.request_id,
        )


def build_openai_compatible_prompt_generator(
    raw_settings: dict[str, Any],
) -> OpenAICompatiblePromptGenerator:
    settings = OpenAICompatiblePromptSettings.model_validate(raw_settings)
    return OpenAICompatiblePromptGenerator(settings)
