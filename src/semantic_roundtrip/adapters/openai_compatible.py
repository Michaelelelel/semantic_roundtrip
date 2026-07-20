"""Prompt generation through an OpenAI-compatible chat endpoint."""

import json
from pathlib import Path
from string import Template
from typing import Any, Literal

import requests
from pydantic import Field

from semantic_roundtrip.adapters.errors import AdapterError
from semantic_roundtrip.config import ConfigModel
from semantic_roundtrip.domain import GeneratedPrompt, PromptBatchResult


class OpenAICompatiblePromptSettings(ConfigModel):
    """Settings for an OpenAI-compatible prompt-generation endpoint."""

    endpoint: str = Field(min_length=1)
    model_id: str = Field(min_length=1)
    request_model: str | None = None
    template_path: Path
    parser_version: Literal["json_list_v1"] = "json_list_v1"
    require_exact_count: bool = False
    system_prompt: str = (
        "Create visual prompts for a text-to-image model and follow the "
        "requested response format exactly."
    )
    temperature: float = Field(default=0.8, ge=0)
    top_p: float = Field(default=0.95, gt=0, le=1)
    max_tokens: int = Field(default=2048, gt=0)
    timeout_seconds: float = Field(default=300, gt=0)


class OpenAICompatiblePromptGenerator:
    """Request one JSON list of visual prompts from a chat model."""

    def __init__(self, settings: OpenAICompatiblePromptSettings) -> None:
        self._config = settings
        self._template = Template(
            Path(settings.template_path).read_text(encoding="utf-8")
        )
        self._session = requests.Session()

    def generate_prompts(
        self,
        *,
        title: str,
        domain: str | None,
        count: int,
    ) -> PromptBatchResult:
        user_prompt = self._template.substitute(
            title=title,
            domain=domain or "",
            count=count,
        )
        payload: dict[str, Any] = {
            "model": self._config.request_model or self._config.model_id,
            "messages": [
                {"role": "system", "content": self._config.system_prompt},
                {"role": "user", "content": user_prompt},
            ],
            "temperature": self._config.temperature,
            "top_p": self._config.top_p,
            "max_tokens": self._config.max_tokens,
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
            content = response_data["choices"][0]["message"]["content"]
            if not isinstance(content, str):
                raise TypeError("message content is not text")
        except (KeyError, IndexError, TypeError, ValueError) as error:
            raise AdapterError(
                "Prompt endpoint returned an unexpected response structure.",
                raw_response,
            ) from error

        prompts, returned_count, format_valid, parser_error = self._parse_json_list(
            content, count
        )
        if self._config.require_exact_count and (
            not format_valid or returned_count != count
        ):
            detail = parser_error or (
                f"requested {count} prompts but received {returned_count}"
            )
            raise AdapterError(
                f"Prompt response failed exact-count validation: {detail}",
                raw_response,
            )

        request_id = response_data.get("id")

        return PromptBatchResult(
            requested_count=count,
            returned_count=returned_count,
            prompts=prompts,
            raw_response=raw_response,
            format_valid=format_valid,
            parser_version=self._config.parser_version,
            parser_error=parser_error,
            backend_request_id=(str(request_id) if request_id is not None else None),
        )

    @staticmethod
    def _parse_json_list(
        content: str,
        requested_count: int,
    ) -> tuple[tuple[GeneratedPrompt, ...], int, bool, str | None]:
        try:
            parsed = json.loads(content)
        except json.JSONDecodeError as error:
            return (), 0, False, str(error)

        if not isinstance(parsed, list):
            return (), 0, False, "The model response is not a JSON array."

        returned_count = len(parsed)
        if not all(isinstance(value, str) and value.strip() for value in parsed):
            return (
                (),
                returned_count,
                False,
                "Every JSON array element must be a non-empty string.",
            )

        stored_values = parsed[:requested_count]
        prompts = tuple(
            GeneratedPrompt(index=index, text=value.strip())
            for index, value in enumerate(stored_values)
        )
        return prompts, returned_count, True, None


def build_openai_compatible_prompt_generator(
    raw_settings: dict[str, Any],
) -> OpenAICompatiblePromptGenerator:
    settings = OpenAICompatiblePromptSettings.model_validate(raw_settings)
    return OpenAICompatiblePromptGenerator(settings)
