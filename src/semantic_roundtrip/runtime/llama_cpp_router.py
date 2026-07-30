"""Runtime controller for a llama.cpp model-router server."""

import time
from typing import Any

import requests

from semantic_roundtrip.runtime.base import (
    RuntimeController,
    RuntimeControllerError,
    RuntimeTarget,
)


DEFAULT_REQUEST_TIMEOUT_SECONDS = 30.0
DEFAULT_TRANSITION_TIMEOUT_SECONDS = 900.0
DEFAULT_POLL_INTERVAL_SECONDS = 0.5


class LlamaCppRouterController(RuntimeController):
    """Control one llama.cpp model-router server through its HTTP API."""

    def __init__(
        self,
        control_url: str,
        *,
        request_timeout_seconds: float = DEFAULT_REQUEST_TIMEOUT_SECONDS,
        transition_timeout_seconds: float = DEFAULT_TRANSITION_TIMEOUT_SECONDS,
        poll_interval_seconds: float = DEFAULT_POLL_INTERVAL_SECONDS,
        session: requests.Session | None = None,
    ) -> None:
        self._control_url = control_url.rstrip("/")
        self._request_timeout_seconds = request_timeout_seconds
        self._transition_timeout_seconds = transition_timeout_seconds
        self._poll_interval_seconds = poll_interval_seconds
        self._session = session if session is not None else requests.Session()

    def load(self, target: RuntimeTarget) -> None:
        model_id = _require_model_id(target)
        self._post_model_action("load", model_id)
        self._wait_for_status(model_id, expected_status="loaded")

    def unload(self, target: RuntimeTarget) -> None:
        model_id = _require_model_id(target)
        self._post_model_action("unload", model_id)
        self._wait_for_status(model_id, expected_status="unloaded")

    def _post_model_action(self, action: str, model_id: str) -> None:
        url = f"{self._control_url}/models/{action}"
        try:
            response = self._session.post(
                url,
                json={"model": model_id},
                timeout=self._transition_timeout_seconds,
            )
        except requests.RequestException as error:
            raise RuntimeControllerError(
                f"llama.cpp model {action} request failed: {error}"
            ) from error

        raw_response = response.text
        try:
            response.raise_for_status()
            data = response.json()
            if not isinstance(data, dict) or data.get("success") is not True:
                raise TypeError("response does not report success")
        except (requests.HTTPError, TypeError, ValueError) as error:
            raise RuntimeControllerError(
                f"llama.cpp could not {action} model '{model_id}': "
                f"{raw_response or 'invalid response'}"
            ) from error

    def _wait_for_status(self, model_id: str, *, expected_status: str) -> None:
        deadline = time.monotonic() + self._transition_timeout_seconds
        last_status: str | None = None

        while True:
            model = self._find_model(model_id)
            if model is None:
                if expected_status == "unloaded":
                    return
                last_status = "missing"
            else:
                status = model.get("status")
                if not isinstance(status, dict):
                    raise RuntimeControllerError(
                        f"llama.cpp returned no status for model '{model_id}'."
                    )

                value = status.get("value")
                if not isinstance(value, str):
                    raise RuntimeControllerError(
                        f"llama.cpp returned an invalid status for model '{model_id}'."
                    )
                last_status = value
                if value == expected_status:
                    return
                if status.get("failed") is True:
                    raise RuntimeControllerError(
                        f"llama.cpp model '{model_id}' entered failed state "
                        f"while waiting for '{expected_status}'."
                    )

            if time.monotonic() >= deadline:
                raise RuntimeControllerError(
                    f"Timed out waiting for llama.cpp model '{model_id}' to become "
                    f"'{expected_status}' (last status: {last_status})."
                )
            time.sleep(self._poll_interval_seconds)

    def _find_model(self, model_id: str) -> dict[str, Any] | None:
        url = f"{self._control_url}/models"
        try:
            response = self._session.get(
                url,
                timeout=self._request_timeout_seconds,
            )
        except requests.RequestException as error:
            raise RuntimeControllerError(
                f"Could not read llama.cpp model status: {error}"
            ) from error

        raw_response = response.text
        try:
            response.raise_for_status()
            payload = response.json()
            models = payload["data"]
            if not isinstance(models, list):
                raise TypeError("'data' is not a list")
        except (KeyError, requests.HTTPError, TypeError, ValueError) as error:
            raise RuntimeControllerError(
                "llama.cpp returned invalid model status data: "
                f"{raw_response or 'empty response'}"
            ) from error

        for model in models:
            if isinstance(model, dict) and model.get("id") == model_id:
                return model
        return None


def _require_model_id(target: RuntimeTarget) -> str:
    if target.model_id is None:
        raise ValueError(f"Runtime target for stage '{target.stage}' has no model ID.")
    return target.model_id
