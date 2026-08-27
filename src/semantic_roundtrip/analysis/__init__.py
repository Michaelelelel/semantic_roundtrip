"""Read-only DataFrame analysis for explicitly selected SQLite runs."""

from semantic_roundtrip.analysis.config import LoadedStudy, StudyConfig, load_study
from semantic_roundtrip.analysis.design import (
    DIRECT_COMPARISONS,
    validate_final_design,
)
from semantic_roundtrip.analysis.loader import load_study_frames
from semantic_roundtrip.analysis.metrics import (
    aggregate_titles,
    condition_summary,
    paired_effect,
    paired_title_differences,
    weighted_title_effect,
)
from semantic_roundtrip.analysis.models import StudyFrames

__all__ = [
    "DIRECT_COMPARISONS",
    "LoadedStudy",
    "StudyConfig",
    "StudyFrames",
    "aggregate_titles",
    "condition_summary",
    "load_study",
    "load_study_frames",
    "paired_effect",
    "paired_title_differences",
    "validate_final_design",
    "weighted_title_effect",
]
