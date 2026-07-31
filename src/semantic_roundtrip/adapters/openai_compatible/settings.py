"""Shared settings for templated OpenAI-compatible stage adapters."""

from pathlib import Path

from pydantic import Field

from semantic_roundtrip.config import ConfigModel


class OpenAICompatibleStageSettings(ConfigModel):
    """Settings shared by templated text and multimodal chat stages."""

    endpoint: str = Field(min_length=1)
    model_id: str = Field(min_length=1)
    template_path: Path
    temperature: float = Field(default=0.0, ge=0)
    top_p: float = Field(default=1.0, gt=0, le=1)
    max_tokens: int = Field(gt=0)
    timeout_seconds: float = Field(default=300, gt=0)
