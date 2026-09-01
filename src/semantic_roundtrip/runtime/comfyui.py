"""Runtime controller for ComfyUI."""

import time

import requests

from semantic_roundtrip.runtime.base import (
    RuntimeController,
    RuntimeControllerError,
    RuntimeTarget,
)

DEFAULT_REQUEST_TIMEOUT_SECONDS = 30.0
DEFAULT_RELEASE_GRACE_SECONDS = 1.0


class ComfyUIRuntimeController(RuntimeController):
    """Release ComfyUI models while keeping checkpoint loading workflow-driven."""

    def __init__(
        self,
        control_url: str,
        *,
        request_timeout_seconds: float = DEFAULT_REQUEST_TIMEOUT_SECONDS,
        release_grace_seconds: float = DEFAULT_RELEASE_GRACE_SECONDS,
        session: requests.Session | None = None,
    ) -> None:
        self._control_url = control_url.rstrip("/")
        self._request_timeout_seconds = request_timeout_seconds
        self._release_grace_seconds = release_grace_seconds
        self._session = session if session is not None else requests.Session()

    def load(self, target: RuntimeTarget) -> None:
        """Let the first real ComfyUI workflow load its configured checkpoint."""

    def unload(self, target: RuntimeTarget) -> None:
        try:
            response = self._session.post(
                f"{self._control_url}/free",
                json={
                    "unload_models": True,
                    "free_memory": True,
                },
                timeout=self._request_timeout_seconds,
            )
            response.raise_for_status()
        except requests.RequestException as error:
            raise RuntimeControllerError(
                f"ComfyUI model release request failed: {error}"
            ) from error

        # ComfyUI acknowledges /free before its worker consumes the release flag.
        if self._release_grace_seconds > 0:
            time.sleep(self._release_grace_seconds)
