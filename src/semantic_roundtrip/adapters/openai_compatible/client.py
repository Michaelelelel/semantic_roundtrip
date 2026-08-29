"""Shared transport for OpenAI-compatible chat-completion endpoints."""

import base64
import json
import mimetypes
import os
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Literal

import requests

from semantic_roundtrip.adapters.errors import AdapterError


@dataclass(frozen=True, slots=True)
class TextContent:
    """One text part in a typed chat-message content array."""

    text: str


@dataclass(frozen=True, slots=True)
class ImageContent:
    """One image URL part in a typed chat-message content array."""

    url: str


ChatContentPart = TextContent | ImageContent
ReasoningFormat = Literal["auto", "none", "deepseek", "deepseek-legacy"]


@dataclass(frozen=True, slots=True)
class ChatMessage:
    """One text-only or multimodal chat message."""

    role: Literal["system", "user", "assistant"]
    content: str | tuple[ChatContentPart, ...]


@dataclass(frozen=True, slots=True)
class ChatCompletion:
    """Normalized first-choice result and the exact provider response."""

    content: str
    raw_response: str
    request_id: str | None
    finish_reason: str | None
    visible_content_token_logprobs: tuple[float, ...] | None


def image_file_data_url(path: Path) -> str:
    """Read an image and return a MIME-qualified Base64 data URL."""
    media_type, _ = mimetypes.guess_type(path.name)
    if media_type is None or not media_type.startswith("image/"):
        raise ValueError(f"Cannot infer an image media type for '{path}'.")

    encoded = base64.b64encode(path.read_bytes()).decode("ascii")
    return f"data:{media_type.lower()};base64,{encoded}"


class OpenAICompatibleChatClient:
    """Send requests through one OpenAI-compatible chat endpoint."""

    def __init__(
        self,
        *,
        endpoint: str,
        model_id: str,
        timeout_seconds: float,
        api_key_env: str | None = None,
        error_subject: str = "OpenAI-compatible chat",
        session: requests.Session | None = None,
    ) -> None:
        self._endpoint = endpoint
        self._model_id = model_id
        self._timeout_seconds = timeout_seconds
        self._api_key_env = api_key_env
        self._error_subject = error_subject
        self._session = session if session is not None else requests.Session()

    def complete(
        self,
        *,
        messages: tuple[ChatMessage, ...],
        generation_parameters: Mapping[str, Any] | None = None,
        response_format: Mapping[str, Any] | None = None,
        include_token_logprobs: bool = False,
        top_logprobs: int | None = None,
        stream: bool = False,
        reasoning_effort: str | None = None,
        reasoning_format: ReasoningFormat | None = None,
        thinking_budget_tokens: int | None = None,
        chat_template_kwargs: Mapping[str, Any] | None = None,
    ) -> ChatCompletion:
        """Return the normalized first choice from one chat completion."""
        if not messages:
            raise ValueError("At least one chat message is required.")
        if top_logprobs is not None and not include_token_logprobs:
            raise ValueError("top_logprobs requires include_token_logprobs=True.")
        if top_logprobs is not None and top_logprobs < 0:
            raise ValueError("top_logprobs must be non-negative.")
        if stream and include_token_logprobs:
            raise ValueError("Streaming token logprobs are not supported.")

        payload: dict[str, Any] = {
            "model": self._model_id,
            "messages": [_serialize_message(message) for message in messages],
        }
        if generation_parameters:
            payload.update(generation_parameters)
        optional_values = {
            "reasoning_format": reasoning_format,
            "thinking_budget_tokens": thinking_budget_tokens,
        }
        payload.update(
            {key: value for key, value in optional_values.items() if value is not None}
        )

        if response_format is not None:
            payload["response_format"] = dict(response_format)
        if reasoning_effort is not None:
            payload["reasoning_effort"] = reasoning_effort
        if chat_template_kwargs:
            payload["chat_template_kwargs"] = dict(chat_template_kwargs)
        if stream:
            payload["stream"] = True
        if include_token_logprobs:
            payload["logprobs"] = True
            if top_logprobs is not None:
                payload["top_logprobs"] = top_logprobs

        headers: dict[str, str] | None = None
        if self._api_key_env is not None:
            api_key = os.environ.get(self._api_key_env)
            if not api_key:
                raise AdapterError(
                    f"{self._error_subject} requires environment variable "
                    f"'{self._api_key_env}'."
                )
            headers = {"Authorization": f"Bearer {api_key}"}

        try:
            response = self._session.post(
                self._endpoint,
                json=payload,
                headers=headers,
                timeout=self._timeout_seconds,
            )
        except requests.RequestException as error:
            raise AdapterError(
                f"{self._error_subject} request failed: {error}"
            ) from error

        try:
            raw_response = response.content.decode("utf-8")
        except UnicodeDecodeError as error:
            raise AdapterError(
                f"{self._error_subject} endpoint returned invalid UTF-8."
            ) from error
        try:
            response.raise_for_status()
        except requests.HTTPError as error:
            raise AdapterError(
                f"{self._error_subject} endpoint returned HTTP {response.status_code}.",
                raw_response,
            ) from error

        if stream:
            try:
                completion = _parse_streaming_response(
                    raw_response,
                    error_subject=self._error_subject,
                )
            except (KeyError, IndexError, TypeError, ValueError) as error:
                raise AdapterError(
                    f"{self._error_subject} endpoint returned an unexpected "
                    "streaming response structure.",
                    raw_response,
                ) from error
            _reject_reasoning_markup(
                completion.content,
                finish_reason=completion.finish_reason,
                raw_response=raw_response,
                error_subject=self._error_subject,
            )
            return completion

        try:
            response_data = response.json()
            choice = _first_choice(response_data)
            content = _choice_content(choice)
            finish_reason = choice.get("finish_reason")
            if finish_reason is not None and not isinstance(finish_reason, str):
                raise TypeError("finish reason is not text")
            visible_content_token_logprobs = (
                _visible_content_token_logprobs(choice, content)
                if include_token_logprobs
                else None
            )
        except (KeyError, IndexError, TypeError, ValueError) as error:
            raise AdapterError(
                f"{self._error_subject} endpoint returned an unexpected "
                "response structure.",
                raw_response,
            ) from error

        _reject_reasoning_markup(
            content,
            finish_reason=finish_reason,
            raw_response=raw_response,
            error_subject=self._error_subject,
        )

        request_id = response_data.get("id")
        return ChatCompletion(
            content=content,
            raw_response=raw_response,
            request_id=(str(request_id) if request_id is not None else None),
            finish_reason=finish_reason,
            visible_content_token_logprobs=visible_content_token_logprobs,
        )


def _reject_reasoning_markup(
    content: str,
    *,
    finish_reason: str | None,
    raw_response: str,
    error_subject: str,
) -> None:
    """Reject reasoning that leaked into the provider's final-answer field."""
    if finish_reason == "length":
        return
    normalized = content.casefold()
    reasoning_markers = (
        "<think>",
        "</think>",
        "<|channel>",
        "<channel|>",
        "<|analysis|>",
        "<|thought|>",
    )
    if any(marker in normalized for marker in reasoning_markers):
        raise AdapterError(
            f"{error_subject} endpoint returned reasoning markup in final content.",
            raw_response,
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
    if isinstance(part, TextContent):
        return {"type": "text", "text": part.text}
    if isinstance(part, ImageContent):
        return {"type": "image_url", "image_url": {"url": part.url}}
    raise TypeError(f"Unsupported chat content part: {type(part).__name__}.")


def _first_choice(response_data: Any) -> dict[str, Any]:
    if not isinstance(response_data, dict):
        raise TypeError("response is not an object")

    choices = response_data["choices"]
    if not isinstance(choices, list) or not choices:
        raise TypeError("choices is not a non-empty list")

    choice = choices[0]
    if not isinstance(choice, dict):
        raise TypeError("choice is not an object")
    return choice


def _choice_content(choice: dict[str, Any]) -> str:
    message = choice["message"]
    if not isinstance(message, dict):
        raise TypeError("message is not an object")

    content = message["content"]
    if not isinstance(content, str):
        raise TypeError("message content is not text")
    return content


def _parse_streaming_response(
    raw_response: str,
    *,
    error_subject: str = "OpenAI-compatible chat",
) -> ChatCompletion:
    content_parts: list[str] = []
    request_id: str | None = None
    finish_reason: str | None = None

    for line in raw_response.splitlines():
        if not line.startswith("data: "):
            continue

        event_text = line.removeprefix("data: ")
        if event_text == "[DONE]":
            break

        event = json.loads(event_text)
        if not isinstance(event, dict):
            raise TypeError("streaming event is not an object")

        stream_error = event.get("error")
        if stream_error is not None:
            if not isinstance(stream_error, dict):
                raise TypeError("streaming error is not an object")
            message = stream_error.get("message")
            if not isinstance(message, str) or not message:
                raise TypeError("streaming error message is not text")
            raise AdapterError(
                f"{error_subject} endpoint returned a streaming error: {message}",
                raw_response,
            )

        raw_request_id = event.get("id")
        if raw_request_id is not None:
            request_id = str(raw_request_id)

        choices = event.get("choices")
        if not isinstance(choices, list):
            raise TypeError("streaming choices is not a list")
        if not choices:
            # OpenAI-compatible servers may finish with a usage/timing event
            # that deliberately contains no choice.
            continue

        choice = choices[0]
        if not isinstance(choice, dict):
            raise TypeError("streaming choice is not an object")
        delta = choice.get("delta")
        if not isinstance(delta, dict):
            raise TypeError("streaming delta is not an object")

        content = delta.get("content")
        if content is not None:
            if not isinstance(content, str):
                raise TypeError("streaming content is not text")
            content_parts.append(content)

        raw_finish_reason = choice.get("finish_reason")
        if raw_finish_reason is not None:
            if not isinstance(raw_finish_reason, str):
                raise TypeError("streaming finish reason is not text")
            finish_reason = raw_finish_reason

    return ChatCompletion(
        content="".join(content_parts),
        raw_response=raw_response,
        request_id=request_id,
        finish_reason=finish_reason,
        visible_content_token_logprobs=None,
    )


def _visible_content_token_logprobs(
    choice: dict[str, Any],
    visible_content: str,
) -> tuple[float, ...] | None:
    """Return probabilities only when token bytes exactly end in visible content.

    Some reasoning endpoints expose hidden reasoning and the final answer in one
    ``logprobs.content`` sequence even though only the final answer appears in
    ``message.content``. Treat log-probabilities as optional metadata: retain an
    exact visible suffix and otherwise return ``None`` without invalidating the
    completion.
    """
    raw_logprobs = choice.get("logprobs")
    if not isinstance(raw_logprobs, dict):
        return None

    raw_content = raw_logprobs.get("content")
    if not isinstance(raw_content, list) or not raw_content:
        return None

    target = visible_content.encode("utf-8")
    if not target:
        return None

    parsed: list[tuple[bytes, float]] = []
    for item in raw_content:
        if not isinstance(item, dict):
            return None

        value = item.get("logprob")
        if isinstance(value, bool) or not isinstance(value, int | float):
            return None

        token_bytes = _logprob_token_bytes(item)
        if token_bytes is None:
            return None
        if token_bytes:
            parsed.append((token_bytes, float(value)))

    suffix = b""
    suffix_logprobs: list[float] = []
    for token_bytes, logprob in reversed(parsed):
        suffix = token_bytes + suffix
        suffix_logprobs.append(logprob)
        if len(suffix) >= len(target):
            break

    if suffix != target:
        return None

    suffix_logprobs.reverse()
    return tuple(suffix_logprobs)


def _logprob_token_bytes(item: dict[str, Any]) -> bytes | None:
    """Return the provider token bytes, with a conservative text fallback."""
    raw_bytes = item.get("bytes")
    if isinstance(raw_bytes, list):
        if any(
            isinstance(value, bool)
            or not isinstance(value, int)
            or value < 0
            or value > 255
            for value in raw_bytes
        ):
            return None
        return bytes(raw_bytes)

    token = item.get("token")
    if isinstance(token, str):
        return token.encode("utf-8")

    return None
