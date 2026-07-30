"""Shared transport for OpenAI-compatible chat-completion endpoints."""

import base64
import mimetypes
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import requests
from pydantic import Field

from semantic_roundtrip.adapters.errors import AdapterError
from semantic_roundtrip.config import ConfigModel
from semantic_roundtrip.domain import PromptMessage, PromptResponse


@dataclass(frozen=True, slots=True)
class ChatTextPart:
    """One text item in a typed chat-message content array."""

    text: str


@dataclass(frozen=True, slots=True)
class ChatImageURLPart:
    """One image_url item in a typed chat-message content array."""

    url: str


ChatContentPart = ChatTextPart | ChatImageURLPart


@dataclass(frozen=True, slots=True)
class ChatMessage:
    """A text-only or typed multimodal chat message."""

    role: str
    content: str | tuple[ChatContentPart, ...]


@dataclass(frozen=True, slots=True)
class ChatCompletion:
    """Normalized first-choice result with the exact provider body."""

    content: str
    raw_response: str
    request_id: str | None
    finish_reason: str | None
    token_logprobs: tuple[float, ...] | None


def image_file_data_url(path: Path) -> str:
    """Read an image and return a MIME-qualified Base64 data URL."""
    media_type, _ = mimetypes.guess_type(path.name)
    if media_type is None or not media_type.startswith("image/"):
        raise ValueError(f"Cannot infer an image media type for '{path}'.")
    encoded = base64.b64encode(path.read_bytes()).decode("ascii")
    return f"data:{media_type.lower()};base64,{encoded}"


class OpenAICompatibleChatClient:
    """Send chat completions with common HTTP and envelope handling."""

    def __init__(
        self,
        *,
        endpoint: str,
        model_id: str,
        timeout_seconds: float,
        error_subject: str = "OpenAI-compatible chat",
        session: requests.Session | None = None,
    ) -> None:
        self._endpoint = endpoint
        self._model_id = model_id
        self._timeout_seconds = timeout_seconds
        self._error_subject = error_subject
        self._session = session if session is not None else requests.Session()

    def complete(
        self,
        *,
        messages: tuple[ChatMessage, ...],
        temperature: float | None = None,
        top_p: float | None = None,
        max_tokens: int | None = None,
        seed: int | None = None,
        response_format: Mapping[str, Any] | None = None,
        include_token_logprobs: bool = False,
        top_logprobs: int | None = None,
    ) -> ChatCompletion:
        """Return the first choice from one non-streaming completion."""
        if not messages:
            raise ValueError("At least one chat message is required.")
        if top_logprobs is not None and not include_token_logprobs:
            raise ValueError("top_logprobs requires include_token_logprobs=True.")
        if top_logprobs is not None and top_logprobs < 0:
            raise ValueError("top_logprobs must be non-negative.")

        payload: dict[str, Any] = {
            "model": self._model_id,
            "messages": [_serialize_message(message) for message in messages],
        }
        optional_values = {
            "temperature": temperature,
            "top_p": top_p,
            "max_tokens": max_tokens,
            "seed": seed,
        }
        payload.update(
            {key: value for key, value in optional_values.items() if value is not None}
        )
        if response_format is not None:
            payload["response_format"] = dict(response_format)
        if include_token_logprobs:
            payload["logprobs"] = True
            if top_logprobs is not None:
                payload["top_logprobs"] = top_logprobs

        try:
            response = self._session.post(
                self._endpoint,
                json=payload,
                timeout=self._timeout_seconds,
            )
        except requests.RequestException as error:
            raise AdapterError(
                f"{self._error_subject} request failed: {error}"
            ) from error

        raw_response = response.text
        try:
            response.raise_for_status()
        except requests.HTTPError as error:
            raise AdapterError(
                f"{self._error_subject} endpoint returned HTTP {response.status_code}.",
                raw_response,
            ) from error

        try:
            response_data = response.json()
            if not isinstance(response_data, dict):
                raise TypeError("response is not an object")
            choices = response_data["choices"]
            if not isinstance(choices, list) or not choices:
                raise TypeError("choices is not a non-empty list")
            choice = choices[0]
            if not isinstance(choice, dict):
                raise TypeError("choice is not an object")
            message = choice["message"]
            if not isinstance(message, dict):
                raise TypeError("message is not an object")
            content = message["content"]
            finish_reason = choice.get("finish_reason")
            if not isinstance(content, str):
                raise TypeError("message content is not text")
            if finish_reason is not None and not isinstance(finish_reason, str):
                raise TypeError("finish reason is not text")
            token_logprobs = (
                _parse_token_logprobs(choice) if include_token_logprobs else None
            )
        except (KeyError, IndexError, TypeError, ValueError) as error:
            raise AdapterError(
                f"{self._error_subject} endpoint returned an unexpected "
                "response structure.",
                raw_response,
            ) from error

        request_id = response_data.get("id")
        return ChatCompletion(
            content=content,
            raw_response=raw_response,
            request_id=(str(request_id) if request_id is not None else None),
            finish_reason=finish_reason,
            token_logprobs=token_logprobs,
        )


def _serialize_message(message: ChatMessage) -> dict[str, Any]:
    if isinstance(message.content, str):
        content: str | list[dict[str, Any]] = message.content
    else:
        if not message.content:
            raise ValueError("Multimodal chat content cannot be empty.")
        content = [_serialize_content_part(part) for part in message.content]
    return {"role": message.role, "content": content}


def _serialize_content_part(part: ChatContentPart) -> dict[str, Any]:
    if isinstance(part, ChatTextPart):
        return {"type": "text", "text": part.text}
    if isinstance(part, ChatImageURLPart):
        return {"type": "image_url", "image_url": {"url": part.url}}
    raise TypeError(f"Unsupported chat content part: {type(part).__name__}.")


def _parse_token_logprobs(choice: dict[str, Any]) -> tuple[float, ...]:
    raw_logprobs = choice.get("logprobs")
    if not isinstance(raw_logprobs, dict):
        raise TypeError("requested token logprobs are missing")
    raw_content = raw_logprobs.get("content")
    if not isinstance(raw_content, list) or not raw_content:
        raise TypeError("logprobs content is not a non-empty list")

    token_logprobs: list[float] = []
    for item in raw_content:
        if not isinstance(item, dict):
            raise TypeError("token logprob is not an object")
        value = item.get("logprob")
        if isinstance(value, bool) or not isinstance(value, int | float):
            raise TypeError("token logprob is not numeric")
        token_logprobs.append(float(value))
    return tuple(token_logprobs)


class OpenAICompatiblePromptSettings(ConfigModel):
    """Settings for OpenAI-compatible prompt generation."""

    endpoint: str = Field(min_length=1)
    model_id: str = Field(min_length=1)
    temperature: float = Field(default=0.8, ge=0)
    top_p: float = Field(default=0.95, gt=0, le=1)
    max_tokens: int = Field(default=2048, gt=0)
    timeout_seconds: float = Field(default=300, gt=0)


class OpenAICompatiblePromptGenerator:
    """Generate one image prompt through the shared chat transport."""

    def __init__(self, settings: OpenAICompatiblePromptSettings) -> None:
        self._config = settings
        self._client = OpenAICompatibleChatClient(
            endpoint=settings.endpoint,
            model_id=settings.model_id,
            timeout_seconds=settings.timeout_seconds,
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
            temperature=self._config.temperature,
            top_p=self._config.top_p,
            max_tokens=self._config.max_tokens,
            seed=seed,
        )

        text = completion.content.strip()
        if not text:
            raise AdapterError(
                "Prompt endpoint returned an empty response.",
                completion.raw_response,
            )
        if completion.finish_reason == "length":
            raise AdapterError(
                "Prompt response was truncated because the token limit was reached.",
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
