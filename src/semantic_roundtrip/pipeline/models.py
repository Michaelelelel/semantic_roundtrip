"""Pipeline result models."""

from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class PipelineSummary:
    """Current database counts and final status of one pipeline invocation."""

    status: str
    dataset_items: int
    prompts: int
    images: int
    verifications: int
    image_descriptions: int
    predictions: int
    failed_tasks: int
