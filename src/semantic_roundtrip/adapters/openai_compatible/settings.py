"""Shared settings for templated OpenAI-compatible stage adapters."""

from pathlib import Path
from typing import Any

from pydantic import Field

from semantic_roundtrip.adapters.openai_compatible.client import ReasoningFormat
from semantic_roundtrip.config import ConfigModel


class OpenAICompatibleStageSettings(ConfigModel):
    """Settings shared by templated text and multimodal chat stages."""

    endpoint: str = Field(min_length=1)
    model_id: str = Field(min_length=1)
    api_key_env: str | None = Field(default=None, min_length=1)
    request_token_logprobs: bool = True
    template_path: Path
    temperature: float = Field(default=0.0, ge=0)
    top_p: float = Field(default=1.0, gt=0, le=1)
    max_tokens: int = Field(gt=0)
    seed: int | None = Field(default=None, ge=0)
    timeout_seconds: float = Field(default=300, gt=0)
    reasoning_effort: str | None = Field(default=None, min_length=1)
    reasoning_format: ReasoningFormat | None = None
    thinking_budget_tokens: int | None = Field(default=None, ge=0)
    chat_template_kwargs: dict[str, Any] = Field(default_factory=dict)
