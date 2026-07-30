"""Runtime controller for backends without local model management."""

from semantic_roundtrip.runtime.base import RuntimeController, RuntimeTarget


class NoOpRuntimeController(RuntimeController):
    """Represent a backend whose process does not own local model residency."""

    def load(self, target: RuntimeTarget) -> None:
        pass

    def unload(self, target: RuntimeTarget) -> None:
        pass
