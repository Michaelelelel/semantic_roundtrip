"""One active model session shared by the sequential pipeline stages."""

from collections.abc import Callable
from dataclasses import dataclass

from semantic_roundtrip.config import ResolvedAppConfig, StageName
from semantic_roundtrip.persistence.run.database import RunDatabase
from semantic_roundtrip.persistence.run.runtime_events import RuntimeAction
from semantic_roundtrip.runtime.base import RuntimeController, RuntimeTarget
from semantic_roundtrip.runtime.factory import (
    create_runtime_controller,
    resolve_runtime_target,
)


ControllerFactory = Callable[[RuntimeTarget], RuntimeController]


@dataclass(frozen=True, slots=True)
class ActiveRuntime:
    target: RuntimeTarget
    controller: RuntimeController


class RuntimeSession:
    """Load, reuse, switch, and finally release one active runtime model."""

    def __init__(
        self,
        database: RunDatabase,
        *,
        controller_factory: ControllerFactory = create_runtime_controller,
    ) -> None:
        self._database = database
        self._controller_factory = controller_factory
        self._active: ActiveRuntime | None = None

    def activate_stage(
        self,
        config: ResolvedAppConfig,
        stage: StageName,
    ) -> None:
        """Make one stage's model active, reusing an identical active target."""
        target = resolve_runtime_target(config, stage)
        if self._active is not None and self._active.target.identity == target.identity:
            self._record_reuse(target)
            self._active = ActiveRuntime(
                target=target,
                controller=self._active.controller,
            )
            return

        self.release()
        controller = self._controller_factory(target)
        self._active = ActiveRuntime(target=target, controller=controller)
        runtime_event_id = self._begin_event(target, action="load")
        try:
            controller.load(target)
        except BaseException as error:
            self._database.runtime_events.fail(runtime_event_id, error)
            raise
        else:
            self._database.runtime_events.complete(runtime_event_id)

    def release(self) -> None:
        """Unload the active model, if one is currently tracked."""
        active = self._active
        if active is None:
            return

        runtime_event_id = self._begin_event(active.target, action="unload")
        try:
            active.controller.unload(active.target)
        except BaseException as error:
            self._database.runtime_events.fail(runtime_event_id, error)
            raise
        else:
            self._active = None
            self._database.runtime_events.complete(runtime_event_id)

    def _record_reuse(self, target: RuntimeTarget) -> None:
        runtime_event_id = self._begin_event(target, action="reuse")
        self._database.runtime_events.complete(runtime_event_id)

    def _begin_event(
        self,
        target: RuntimeTarget,
        *,
        action: RuntimeAction,
    ) -> int:
        return self._database.runtime_events.begin(
            stage=target.stage,
            backend_alias=target.backend_alias,
            controller=target.controller,
            resource_group=target.resource_group,
            model_id=target.model_id,
            action=action,
        )
