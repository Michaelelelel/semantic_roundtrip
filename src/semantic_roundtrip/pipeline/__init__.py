"""Public interface for semantic round-trip pipeline execution."""

from semantic_roundtrip.pipeline.models import PipelineSummary
from semantic_roundtrip.pipeline.runner import run_pipeline

__all__ = ["PipelineSummary", "run_pipeline"]
