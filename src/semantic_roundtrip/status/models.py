"""Read models shared by CLI status views and the future status interface."""

from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Literal


EtaState = Literal[
    "none",
    "calculating",
    "estimated",
    "loading_model",
    "unloading_model",
]


@dataclass(frozen=True, slots=True)
class StageStatus:
    """Persisted progress for one configured pipeline stage."""

    name: str
    model: str | None
    produced: int
    expected: int
    pending: int
    running: int
    failed: int


@dataclass(frozen=True, slots=True)
class RunStatus:
    """Complete read-only status for one experiment run."""

    directory: Path
    run_id: str
    name: str
    status: str
    created_at: datetime
    started_at: datetime | None
    last_update: datetime | None
    finished_at: datetime | None
    elapsed_seconds: float | None
    stages: tuple[StageStatus, ...]
    active_stage: str | None
    eta_state: EtaState
    eta_seconds: float | None
    last_error: str | None

    @property
    def failed_tasks(self) -> int:
        """Return terminal adapter-task failures without changing run lifecycle."""
        return sum(stage.failed for stage in self.stages)


@dataclass(frozen=True, slots=True)
class UnavailableStatus:
    """A discovered job or run whose persisted state cannot be read."""

    kind: Literal["job", "run"]
    directory: Path
    error: str
    status: Literal["unavailable"] = "unavailable"


@dataclass(frozen=True, slots=True)
class ChildRunStatus:
    """Lightweight child-run metadata used while listing a complete job."""

    run_id: str
    status: str
    last_update: datetime | None
    failed_tasks: int
    last_error: str | None


@dataclass(frozen=True, slots=True)
class JobEntryStatus:
    """One job entry and the current state of its child run."""

    index: int
    name: str
    status: str
    run_directory: Path
    child: ChildRunStatus | UnavailableStatus
    models: tuple[str, ...]
    last_error: str | None

    @property
    def failed_tasks(self) -> int:
        """Return failed tasks from the child run when it is readable."""
        if isinstance(self.child, UnavailableStatus):
            return 0
        return self.child.failed_tasks


@dataclass(frozen=True, slots=True)
class JobStatus:
    """Complete read-only status for one persisted job."""

    directory: Path
    job_id: str
    name: str
    status: str
    created_at: datetime
    started_at: datetime | None
    last_update: datetime | None
    finished_at: datetime | None
    elapsed_seconds: float | None
    entries: tuple[JobEntryStatus, ...]
    completed_entries: int
    total_entries: int
    active_entry_name: str | None
    active_run_id: str | None
    active_stage: str | None
    eta_state: EtaState
    eta_seconds: float | None
    last_error: str | None

    @property
    def failed_tasks(self) -> int:
        """Return failed adapter tasks across every readable child run."""
        return sum(entry.failed_tasks for entry in self.entries)


JobDiscoveryResult = JobStatus | UnavailableStatus
RunDiscoveryResult = RunStatus | UnavailableStatus
