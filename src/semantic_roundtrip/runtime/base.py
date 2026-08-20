"""Shared contracts and values for runtime controllers."""

from abc import ABC, abstractmethod
from dataclasses import dataclass

from semantic_roundtrip.config import StageName


class RuntimeControllerError(RuntimeError):
    """Report a failed model residency transition."""


@dataclass(frozen=True, slots=True)
class RuntimeIdentity:
    """Fields that determine whether two stages can reuse one loaded model."""

    controller: str
    control_url: str | None
    resource_group: str
    model_id: str | None


@dataclass(frozen=True, slots=True)
class RuntimeTarget:
    """The resolved runtime and model required by one configured stage."""

    stage: StageName
    backend_alias: str
    controller: str
    control_url: str | None
    resource_group: str
    model_id: str | None

    @property
    def identity(self) -> RuntimeIdentity:
        return RuntimeIdentity(
            controller=self.controller,
            control_url=self.control_url,
            resource_group=self.resource_group,
            model_id=self.model_id,
        )


class RuntimeController(ABC):
    """Load and unload the model represented by one runtime target."""

    @abstractmethod
    def load(self, target: RuntimeTarget) -> None:
        """Make the target model ready for inference."""

    @abstractmethod
    def unload(self, target: RuntimeTarget) -> None:
        """Release resources held by the target model."""
