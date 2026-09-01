"""Shared calculations and expected read failures for status discovery."""

from datetime import UTC, datetime
from pathlib import Path
from typing import Literal

import yaml

from semantic_roundtrip.persistence.sqlite import PERSISTENCE_ERRORS
from semantic_roundtrip.status.models import UnavailableStatus

STATUS_READ_ERRORS = (OSError, ValueError, yaml.YAMLError, *PERSISTENCE_ERRORS)


def elapsed_seconds(
    *,
    status: str,
    started_at: datetime | None,
    heartbeat_at: datetime | None,
    finished_at: datetime | None,
    now: datetime | None = None,
) -> float | None:
    """Calculate elapsed wall time without increasing while safely paused."""
    if started_at is None:
        return None

    if finished_at is not None:
        end = finished_at
    elif status == "paused" and heartbeat_at is not None:
        end = heartbeat_at
    else:
        end = now if now is not None else datetime.now(UTC)

    return max(0.0, (end - started_at).total_seconds())


def unavailable(
    kind: Literal["job", "run"],
    directory: Path,
    error: BaseException,
) -> UnavailableStatus:
    """Create a concise unavailable-resource record."""
    return UnavailableStatus(
        kind=kind,
        directory=directory,
        error=f"{type(error).__name__}: {error}",
    )
