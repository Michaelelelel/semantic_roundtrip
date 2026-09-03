"""Pipeline result models."""

from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class PipelineSummary:
    """Current database counts and final status of one pipeline invocation."""

    status: str
    dataset_items: int
    illustratability_ratings: int
    prompts: int
    images: int
    prompt_verifications: int
    strict_image_verifications: int
    title_aware_image_verifications: int
    image_descriptions: int
    predictions: int
    failed_tasks: int
