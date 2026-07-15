"""Stable data objects exchanged between pipeline stages and adapters."""

from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True, slots=True)
class BenchmarkItem:
    """One title and its domain from the benchmark dataset."""

    domain: str
    title: str


@dataclass(frozen=True, slots=True)
class GeneratedPrompt:
    """One visual prompt generated for a benchmark item."""

    index: int
    text: str
    raw_response: str | None = None


@dataclass(frozen=True, slots=True)
class ImageArtifact:
    """A generated image and the information needed to identify it."""

    path: Path
    seed: int
    backend_job_id: str | None = None


@dataclass(frozen=True, slots=True)
class VerificationResult:
    """The verifier's decision for one generated image."""

    passed: bool
    reason: str | None = None
    raw_response: str | None = None


@dataclass(frozen=True, slots=True)
class TitlePrediction:
    """A title guess and its optional model-reported confidence."""

    title: str
    confidence: float | None = None
    confidence_type: str | None = None
    raw_response: str | None = None
