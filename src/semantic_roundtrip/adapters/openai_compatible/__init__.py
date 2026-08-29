"""OpenAI-compatible transport and stage adapters."""

from semantic_roundtrip.adapters.openai_compatible.prompt import (
    build_openai_compatible_prompt_generator,
)
from semantic_roundtrip.adapters.openai_compatible.rating import (
    build_openai_compatible_illustratability_rater,
)
from semantic_roundtrip.adapters.openai_compatible.title import (
    build_openai_compatible_text_title_guesser,
)
from semantic_roundtrip.adapters.openai_compatible.vision import (
    build_openai_compatible_image_describer,
    build_openai_compatible_image_title_guesser,
    build_openai_compatible_image_verifier,
)

__all__ = [
    "build_openai_compatible_illustratability_rater",
    "build_openai_compatible_image_describer",
    "build_openai_compatible_image_title_guesser",
    "build_openai_compatible_image_verifier",
    "build_openai_compatible_prompt_generator",
    "build_openai_compatible_text_title_guesser",
]
