"""Pipeline dependency rules shared by validation and materialization."""

from collections.abc import Iterable

from semantic_roundtrip.config import StageName

STAGE_DEPENDENCIES: dict[StageName, tuple[StageName, ...]] = {
    "illustratability_rating": (),
    "prompt_generation": (),
    "image_generation": ("prompt_generation",),
    "verification": ("image_generation",),
    "title_guessing_direct": ("image_generation",),
    "image_description": ("image_generation",),
    "title_guessing_from_description": ("image_description",),
}

STAGE_ORDER: tuple[StageName, ...] = (
    "illustratability_rating",
    "prompt_generation",
    "image_generation",
    "verification",
    "title_guessing_direct",
    "image_description",
    "title_guessing_from_description",
)


def dependency_closure(stages: Iterable[StageName]) -> tuple[StageName, ...]:
    """Return requested stages and all required predecessors in pipeline order."""
    required: set[StageName] = set()

    def add(stage: StageName) -> None:
        if stage in required:
            return
        for dependency in STAGE_DEPENDENCIES[stage]:
            add(dependency)
        required.add(stage)

    for stage in stages:
        add(stage)
    return tuple(stage for stage in STAGE_ORDER if stage in required)
