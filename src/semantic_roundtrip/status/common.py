"""Shared calculations and expected read failures for status discovery."""

import sqlite3
from datetime import datetime, timezone
from pathlib import Path
from typing import Literal

import yaml

from semantic_roundtrip.status.models import UnavailableStatus


STATUS_READ_ERRORS = (OSError, ValueError, sqlite3.Error, yaml.YAMLError)


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
        end = now if now is not None else datetime.now(timezone.utc)

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
