"""Read-only loading and statistics for the study notebooks."""

from semantic_roundtrip.analysis.loader import AnalysisTables, load_job, load_run
from semantic_roundtrip.analysis.statistics import (
    aggregate_titles,
    illustratability_spearman,
    paired_stratified_bootstrap,
    score_observations,
)

__all__ = [
    "AnalysisTables",
    "aggregate_titles",
    "illustratability_spearman",
    "load_job",
    "load_run",
    "paired_stratified_bootstrap",
    "score_observations",
]
