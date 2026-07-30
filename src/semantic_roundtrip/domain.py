"""Stable data objects exchanged between pipeline stages and adapters."""

from dataclasses import dataclass
from pathlib import Path
from typing import Literal


@dataclass(frozen=True, slots=True)
class BenchmarkItem:
    """One title and its domain from the benchmark dataset."""

    domain: str
    title: str


@dataclass(frozen=True, slots=True)
class PromptMessage:
    """One provider-independent message used to generate an image prompt."""

    role: Literal["system", "user", "assistant"]
    content: str


@dataclass(frozen=True, slots=True)
class PromptResponse:
    """One generated image prompt and its raw provider response."""

    text: str
    raw_response: str
    backend_request_id: str | None = None


@dataclass(frozen=True, slots=True)
class GeneratedPrompt:
    """One parsed visual prompt generated for a benchmark item."""

    index: int
    text: str


@dataclass(frozen=True, slots=True)
class ImageArtifact:
    """A generated image and the information needed to identify it."""

    path: Path
    seed: int
    raw_response: str
    backend_job_id: str | None = None


@dataclass(frozen=True, slots=True)
class VerificationResult:
    """The verifier's decision for one generated image."""

    passed: bool
    raw_response: str
    reason: str | None = None


@dataclass(frozen=True, slots=True)
class ImageDescription:
    """A textual description produced from one generated image."""

    text: str
    raw_response: str
    backend_request_id: str | None = None


@dataclass(frozen=True, slots=True)
class TitlePrediction:
    """A title guess and its optional model-reported confidence."""

    title: str
    raw_response: str
    confidence: float | None = None
    confidence_type: str | None = None
