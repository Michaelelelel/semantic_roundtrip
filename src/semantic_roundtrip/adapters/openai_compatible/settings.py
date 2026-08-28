"""Shared generation settings for OpenAI-compatible adapters."""

from pathlib import Path
from typing import Any, ClassVar, Self

from pydantic import Field, model_validator

from semantic_roundtrip.adapters.openai_compatible.client import ReasoningFormat
from semantic_roundtrip.config import ConfigModel


class OpenAICompatibleGenerationSettings(ConfigModel):
    """Validated generation controls shared by every chat-based stage."""

    _sampler_field_names: ClassVar[tuple[str, ...]] = (
        "temperature",
        "dynatemp_range",
        "top_k",
        "top_p",
        "min_p",
        "typical_p",
        "xtc_probability",
        "repeat_penalty",
        "presence_penalty",
        "frequency_penalty",
        "dry_multiplier",
        "mirostat",
    )

    include_sampler_parameters: bool = True
    temperature: float | None = Field(default=0.0, ge=0)
    dynatemp_range: float | None = Field(default=None, ge=0)
    top_k: int | None = Field(default=None, ge=0)
    top_p: float | None = Field(default=1.0, gt=0, le=1)
    min_p: float | None = Field(default=None, ge=0, le=1)
    typical_p: float | None = Field(default=None, ge=0, le=1)
    xtc_probability: float | None = Field(default=None, ge=0, le=1)
    repeat_penalty: float | None = Field(default=None, gt=0)
    presence_penalty: float | None = Field(default=None, ge=-2, le=2)
    frequency_penalty: float | None = Field(default=None, ge=-2, le=2)
    dry_multiplier: float | None = Field(default=None, ge=0)
    mirostat: int | None = Field(default=None, ge=0, le=2)
    max_tokens: int = Field(gt=0)
    seed: int | None = Field(default=None, ge=0)

    @model_validator(mode="after")
    def reject_explicit_samplers_when_omitted(self) -> Self:
        """Prevent silently ignored sampler controls for remote providers."""
        if not self.include_sampler_parameters:
            explicit = set(self._sampler_field_names) & self.model_fields_set
            if explicit:
                names = ", ".join(sorted(explicit))
                raise ValueError(
                    "Sampler parameters cannot be set when "
                    f"include_sampler_parameters is false: {names}."
                )
        return self

    def generation_parameters(
        self,
        *,
        seed: int | None = None,
    ) -> dict[str, Any]:
        """Return only the generation controls that belong in the request."""
        parameters: dict[str, Any] = {"max_tokens": self.max_tokens}
        effective_seed = self.seed if seed is None else seed
        if effective_seed is not None:
            parameters["seed"] = effective_seed

        if not self.include_sampler_parameters:
            return parameters

        for name in self._sampler_field_names:
            value = getattr(self, name)
            if value is not None:
                parameters[name] = value
        return parameters


class OpenAICompatibleStageSettings(OpenAICompatibleGenerationSettings):
    """Settings shared by templated text and multimodal chat stages."""

    endpoint: str = Field(min_length=1)
    model_id: str = Field(min_length=1)
    api_key_env: str | None = Field(default=None, min_length=1)
    request_token_logprobs: bool = True
    template_path: Path
    timeout_seconds: float = Field(default=300, gt=0)
    reasoning_effort: str | None = Field(default=None, min_length=1)
    reasoning_format: ReasoningFormat | None = None
    thinking_budget_tokens: int | None = Field(default=None, ge=0)
    chat_template_kwargs: dict[str, Any] = Field(default_factory=dict)
