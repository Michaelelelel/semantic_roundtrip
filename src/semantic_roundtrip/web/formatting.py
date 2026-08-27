"""Small formatting helpers used only by the HTML status views."""

from datetime import UTC, datetime

from semantic_roundtrip.status.models import EtaState

STAGE_LABELS = {
    "prompt_generation": "Prompt generation",
    "image_generation": "Image generation",
    "verification": "Verification",
    "title_guessing_direct": "Direct title guessing",
    "image_description": "Image description",
    "title_guessing_from_description": "Description title guessing",
}


def format_datetime(value: datetime | None) -> str:
    """Format persisted timestamps consistently in UTC."""
    if value is None:
        return "-"
    return value.astimezone(UTC).strftime("%Y-%m-%d %H:%M:%S UTC")


def format_duration(seconds: float | None) -> str:
    """Format a duration without misleading sub-second precision."""
    if seconds is None:
        return "-"

    total = max(0, round(seconds))
    days, remainder = divmod(total, 86_400)
    hours, remainder = divmod(remainder, 3_600)
    minutes, seconds = divmod(remainder, 60)
    clock = f"{hours:02d}:{minutes:02d}:{seconds:02d}"
    return clock if days == 0 else f"{days}d {clock}"


def format_stage(stage: str | None) -> str:
    """Return the readable label for one pipeline stage."""
    if stage is None:
        return "-"
    return STAGE_LABELS.get(stage, stage.replace("_", " ").title())


def format_eta(state: EtaState, seconds: float | None) -> str:
    """Format the conservative current-stage estimate."""
    if state == "loading_model":
        return "Loading model"
    if state == "unloading_model":
        return "Unloading model"
    if state == "calculating":
        return "Calculating"
    if state == "estimated" and seconds is not None:
        return f"~{format_duration(seconds)}"
    return "-"
