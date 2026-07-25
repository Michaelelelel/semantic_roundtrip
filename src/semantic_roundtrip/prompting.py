"""Loading and rendering of versioned model prompt profiles."""

from dataclasses import dataclass
from pathlib import Path
from string import Template
from typing import Literal

import yaml
from pydantic import Field

from semantic_roundtrip.config import ConfigModel
from semantic_roundtrip.domain import PromptMessage


ALLOWED_TEMPLATE_VARIABLES = {"title", "domain", "prompt_number"}


class PromptMessageConfig(ConfigModel):
    """One message template in a prompt profile."""

    role: Literal["system", "user", "assistant"]
    content: str = Field(min_length=1)


class PromptProfile(ConfigModel):
    """Versioned instructions for one prompt-generation request."""

    profile_id: str = Field(min_length=1)
    version: int = Field(ge=1)
    output_format: Literal["plain_text"]
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
    title: str,
    domain: str | None,
    prompt_index: int,
) -> tuple[PromptMessage, ...]:
    """Render one independent prompt-generation request."""
    if prompt_index < 0:
        raise ValueError("Prompt index must not be negative.")

    values = {
        "title": title,
        "domain": domain or "",
        "prompt_number": str(prompt_index + 1),
    }
    return tuple(
        PromptMessage(
            role=message.role,
            content=Template(message.content).substitute(values),
        )
        for message in profile.messages
    )
