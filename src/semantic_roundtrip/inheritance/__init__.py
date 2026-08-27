"""Resolve and materialize immutable inputs from earlier experiment runs."""

from semantic_roundtrip.inheritance.dependencies import (
    STAGE_DEPENDENCIES,
    dependency_closure,
)
from semantic_roundtrip.inheritance.source import (
    SourceRun,
    load_source_run,
    resolve_job_entry_run,
)

__all__ = [
    "STAGE_DEPENDENCIES",
    "SourceRun",
    "dependency_closure",
    "load_source_run",
    "resolve_job_entry_run",
]
