"""Loading, validation and rendering of versioned chat prompt profiles."""

from collections.abc import Mapping
from collections.abc import Set as AbstractSet
from dataclasses import dataclass
from pathlib import Path
from string import Template
from typing import Literal

import yaml
from pydantic import Field

from semantic_roundtrip.config import ConfigModel
from semantic_roundtrip.domain import PromptMessage

ALLOWED_TEMPLATE_VARIABLES = {
    "description",
    "domain",
    "normalized_title",
    "prompt",
    "prompt_number",
    "title",
}


class PromptMessageConfig(ConfigModel):
    """One message template in a prompt profile."""

    role: Literal["system", "user", "assistant"]
    content: str = Field(min_length=1)


class PromptProfile(ConfigModel):
    """Versioned messages for one model-backed pipeline stage."""

    profile_id: str = Field(min_length=1)
    version: int = Field(ge=1)
    output_format: Literal["plain_text", "json"]
    messages: list[PromptMessageConfig] = Field(min_length=1)


@dataclass(frozen=True, slots=True)
class LoadedPromptProfile:
    """A validated profile together with its exact source bytes."""

    profile: PromptProfile
    source_bytes: bytes


def _validate_templates(profile: PromptProfile) -> None:
    for message in profile.messages:
        template = Template(message.content)
        if not template.is_valid():
            raise ValueError(
                f"Invalid template syntax in {message.role!r} profile message."
            )

        unknown_variables = set(template.get_identifiers()) - ALLOWED_TEMPLATE_VARIABLES
        if unknown_variables:
            names = ", ".join(sorted(unknown_variables))
            raise ValueError(f"Unknown prompt-profile variables: {names}")


def prompt_profile_variables(profile: PromptProfile) -> frozenset[str]:
    """Return every template variable referenced by a profile."""
    return frozenset(
        identifier
        for message in profile.messages
        for identifier in Template(message.content).get_identifiers()
    )


def validate_prompt_profile_variables(
    profile: PromptProfile,
    *,
    available: AbstractSet[str],
) -> None:
    """Reject variables that the configured pipeline stage cannot provide."""
    unavailable = prompt_profile_variables(profile) - available
    if unavailable:
        names = ", ".join(sorted(unavailable))
        raise ValueError(
            f"Prompt profile '{profile.profile_id}' uses variables unavailable "
            f"to this stage: {names}"
        )


def load_prompt_profile(path: Path) -> LoadedPromptProfile:
    """Read, validate, and identify one prompt profile."""
    source_path = Path(path)
    source_bytes = source_path.read_bytes()
    raw_profile = yaml.safe_load(source_bytes.decode("utf-8"))
    profile = PromptProfile.model_validate(raw_profile)
    _validate_templates(profile)

    return LoadedPromptProfile(
        profile=profile,
        source_bytes=source_bytes,
    )


def render_prompt_profile(
    profile: PromptProfile,
    *,
    variables: Mapping[str, str],
) -> tuple[PromptMessage, ...]:
    """Render one request and fail when a required value is missing."""
    missing = prompt_profile_variables(profile) - variables.keys()
    if missing:
        names = ", ".join(sorted(missing))
        raise ValueError(
            f"Prompt profile '{profile.profile_id}' is missing values for: {names}"
        )
    return tuple(
        PromptMessage(
            role=message.role,
            content=Template(message.content).substitute(variables),
        )
        for message in profile.messages
    )
