"""Formatting shared by job and run status terminal views."""

from datetime import datetime

from semantic_roundtrip.status.models import EtaState


STAGE_LABELS = {
    "prompt_generation": "Prompt generation",
    "image_generation": "Image generation",
    "verification": "Verification",
    "title_guessing_direct": "Direct title guessing",
    "image_description": "Image description",
    "title_guessing_from_description": "Description title guessing",
    "evaluation": "Evaluation",
}


def format_timestamp(value: datetime | None) -> str:
    """Format one persisted timestamp compactly."""
    return "-" if value is None else value.isoformat(timespec="seconds")


def format_duration(seconds: float | None) -> str:
    """Format elapsed seconds without suggesting sub-second precision."""
    if seconds is None:
        return "-"

    total = max(0, round(seconds))
    days, remainder = divmod(total, 86_400)
    hours, remainder = divmod(remainder, 3_600)
    minutes, seconds = divmod(remainder, 60)
    clock = f"{hours:02d}:{minutes:02d}:{seconds:02d}"
    return clock if days == 0 else f"{days}d {clock}"


def format_stage(stage: str | None) -> str:
    """Return a human-readable pipeline stage label."""
    if stage is None:
        return "-"
    return STAGE_LABELS.get(stage, stage.replace("_", " ").title())


def format_eta(state: EtaState, seconds: float | None) -> str:
    """Format the deliberately conservative current-stage estimate."""
    if state == "loading_model":
        return "loading model"
    if state == "unloading_model":
        return "unloading model"
    if state == "calculating":
        return "calculating"
    if state == "estimated" and seconds is not None:
        return f"~{format_duration(seconds)}"
    return "-"
