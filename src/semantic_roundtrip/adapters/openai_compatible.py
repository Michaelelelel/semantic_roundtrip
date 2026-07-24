"""Prompt generation through an OpenAI-compatible chat endpoint."""

from typing import Any

import requests
from pydantic import Field

from semantic_roundtrip.adapters.errors import AdapterError
from semantic_roundtrip.config import ConfigModel
from semantic_roundtrip.domain import PromptMessage, PromptResponse


class OpenAICompatiblePromptSettings(ConfigModel):
    """Settings for an OpenAI-compatible prompt-generation endpoint."""

    endpoint: str = Field(min_length=1)
    model_id: str = Field(min_length=1)
    temperature: float = Field(default=0.8, ge=0)
    top_p: float = Field(default=0.95, gt=0, le=1)
    max_tokens: int = Field(default=2048, gt=0)
    timeout_seconds: float = Field(default=300, gt=0)


class OpenAICompatiblePromptGenerator:
    """Return one image prompt from an OpenAI-compatible server."""

    def __init__(self, settings: OpenAICompatiblePromptSettings) -> None:
        self._config = settings
        self._session = requests.Session()

    def generate_prompt(
        self,
        *,
        messages: tuple[PromptMessage, ...],
        seed: int,
    ) -> PromptResponse:
        payload: dict[str, Any] = {
            "model": self._config.model_id,
            "messages": [
                {"role": message.role, "content": message.content}
                for message in messages
            ],
            "temperature": self._config.temperature,
            "top_p": self._config.top_p,
            "max_tokens": self._config.max_tokens,
            "seed": seed,
        }
        try:
            response = self._session.post(
                self._config.endpoint,
                json=payload,
                timeout=self._config.timeout_seconds,
            )
        except requests.RequestException as error:
            raise AdapterError(f"Prompt request failed: {error}") from error

        raw_response = response.text
        try:
            response.raise_for_status()
        except requests.HTTPError as error:
            raise AdapterError(
                f"Prompt endpoint returned HTTP {response.status_code}.",
                raw_response,
            ) from error

        try:
            response_data = response.json()
            choice = response_data["choices"][0]
            content = choice["message"]["content"]
            finish_reason = choice.get("finish_reason")
            if not isinstance(content, str):
                raise TypeError("message content is not text")
            if finish_reason is not None and not isinstance(finish_reason, str):
                raise TypeError("finish reason is not text")
        except (KeyError, IndexError, TypeError, ValueError) as error:
            raise AdapterError(
                "Prompt endpoint returned an unexpected response structure.",
                raw_response,
            ) from error

        text = content.strip()
        if not text:
            raise AdapterError(
                "Prompt endpoint returned an empty response.",
                raw_response,
            )
        if finish_reason == "length":
            raise AdapterError(
                "Prompt response was truncated because the token limit was reached.",
                raw_response,
            )

        request_id = response_data.get("id")
        return PromptResponse(
            text=text,
            raw_response=raw_response,
            backend_request_id=(str(request_id) if request_id is not None else None),
        )


def build_openai_compatible_prompt_generator(
    raw_settings: dict[str, Any],
) -> OpenAICompatiblePromptGenerator:
    settings = OpenAICompatiblePromptSettings.model_validate(raw_settings)
    return OpenAICompatiblePromptGenerator(settings)
