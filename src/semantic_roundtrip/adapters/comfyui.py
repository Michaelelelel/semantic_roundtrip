"""Image generation through ComfyUI's HTTP API."""

import copy
import json
import time
from hashlib import sha256
from pathlib import Path
from typing import Any

import requests
from pydantic import Field

from semantic_roundtrip.adapters.errors import AdapterError
from semantic_roundtrip.config import ConfigModel
from semantic_roundtrip.domain import ImageArtifact


class ComfyUIWorkflowInput(ConfigModel):
    """Location of one configurable input in a ComfyUI workflow."""

    node_id: str = Field(min_length=1)
    input_name: str = Field(min_length=1)


class ComfyUIWorkflowInputs(ConfigModel):
    """Workflow inputs supplied dynamically for every generated image."""

    prompt: ComfyUIWorkflowInput
    seed: ComfyUIWorkflowInput
    filename_prefix: ComfyUIWorkflowInput


class ComfyUIImageSettings(ConfigModel):
    """Settings for ComfyUI image generation."""

    base_url: str = Field(min_length=1)
    model_id: str = Field(min_length=1)
    workflow_path: Path
    workflow_inputs: ComfyUIWorkflowInputs
    workflow_overrides: dict[str, dict[str, Any]] = Field(default_factory=dict)
    request_timeout_seconds: float = Field(default=30, gt=0)
    generation_timeout_seconds: float = Field(default=900, gt=0)
    poll_interval_seconds: float = Field(default=2, gt=0)


class ComfyUIImageGenerator:
    """Submit a configured workflow and download its first output image."""

    def __init__(self, settings: ComfyUIImageSettings) -> None:
        self._config = settings
        self._base_url = settings.base_url.rstrip("/")
        self._session = requests.Session()
        with Path(settings.workflow_path).open("r", encoding="utf-8") as file:
            self._workflow: dict[str, Any] = json.load(file)

    def generate_image(
        self,
        *,
        prompt: str,
        seed: int,
        output_directory: Path,
    ) -> ImageArtifact:
        output_directory.mkdir(parents=True, exist_ok=True)
        identifier = sha256(f"{prompt}\0{seed}".encode()).hexdigest()[:16]
        workflow = self._prepare_workflow(prompt, seed, identifier)
        submission_data, submission_raw = self._post_json(
            f"{self._base_url}/prompt",
            {"prompt": workflow},
        )

        try:
            prompt_id = str(submission_data["prompt_id"])
        except KeyError as error:
            raise AdapterError(
                "ComfyUI did not return a prompt_id.",
                submission_raw,
            ) from error

        image_info, history_raw = self._wait_for_image(prompt_id)
        source_filename = str(image_info["filename"])
        suffix = Path(source_filename).suffix or ".png"
        image_path = output_directory / f"comfy_{identifier}_seed_{seed}{suffix}"

        self._download_image(image_info, image_path)
        raw_response = json.dumps(
            {
                "submission_raw": submission_raw,
                "history_raw": history_raw,
            },
            ensure_ascii=False,
        )
        return ImageArtifact(
            path=image_path,
            seed=seed,
            raw_response=raw_response,
            backend_job_id=prompt_id,
        )

    def _prepare_workflow(
        self,
        prompt: str,
        seed: int,
        identifier: str,
    ) -> dict[str, Any]:
        workflow = copy.deepcopy(self._workflow)
        for node_id, inputs in self._config.workflow_overrides.items():
            for input_name, value in inputs.items():
                self._set_workflow_input(
                    workflow,
                    node_id=node_id,
                    input_name=input_name,
                    value=value,
                )

        dynamic_inputs = self._config.workflow_inputs
        self._set_bound_input(workflow, dynamic_inputs.prompt, prompt)
        self._set_bound_input(workflow, dynamic_inputs.seed, seed)
        self._set_bound_input(
            workflow,
            dynamic_inputs.filename_prefix,
            f"semantic_roundtrip_{identifier}",
        )
        return workflow

    def _set_bound_input(
        self,
        workflow: dict[str, Any],
        binding: ComfyUIWorkflowInput,
        value: Any,
    ) -> None:
        self._set_workflow_input(
            workflow,
            node_id=binding.node_id,
            input_name=binding.input_name,
            value=value,
        )

    @staticmethod
    def _set_workflow_input(
        workflow: dict[str, Any],
        *,
        node_id: str,
        input_name: str,
        value: Any,
    ) -> None:
        node = workflow.get(node_id)
        inputs = None if not isinstance(node, dict) else node.get("inputs")
        if not isinstance(inputs, dict) or input_name not in inputs:
            raise AdapterError(
                "Configured ComfyUI workflow input is missing: "
                f"node '{node_id}', input '{input_name}'."
            )
        inputs[input_name] = copy.deepcopy(value)

    def _post_json(
        self,
        url: str,
        payload: dict[str, Any],
    ) -> tuple[dict[str, Any], str]:
        try:
            response = self._session.post(
                url,
                json=payload,
                timeout=self._config.request_timeout_seconds,
            )
        except requests.RequestException as error:
            raise AdapterError(f"ComfyUI request failed: {error}") from error

        raw_response = response.text
        try:
            response.raise_for_status()
            data = response.json()
            if not isinstance(data, dict):
                raise TypeError("response is not an object")
        except (requests.HTTPError, TypeError, ValueError) as error:
            raise AdapterError(
                f"ComfyUI returned an invalid response from {url}.",
                raw_response,
            ) from error
        return data, raw_response

    def _wait_for_image(
        self,
        prompt_id: str,
    ) -> tuple[dict[str, Any], str]:
        deadline = time.monotonic() + self._config.generation_timeout_seconds
        last_raw_response: str | None = None

        while time.monotonic() < deadline:
            history, last_raw_response = self._get_history(prompt_id)
            prompt_history = history.get(prompt_id)

            if isinstance(prompt_history, dict):
                for output in prompt_history.get("outputs", {}).values():
                    for image in output.get("images", []):
                        if isinstance(image, dict) and "filename" in image:
                            return image, last_raw_response

                status = prompt_history.get("status", {})
                if isinstance(status, dict):
                    if status.get("status_str") == "error":
                        raise AdapterError(
                            f"ComfyUI job {prompt_id} failed: "
                            f"{_execution_error_message(status)}",
                            last_raw_response,
                        )
                    if status.get("completed"):
                        raise AdapterError(
                            "ComfyUI completed the job without an output image.",
                            last_raw_response,
                        )

            time.sleep(self._config.poll_interval_seconds)

        raise AdapterError(
            f"ComfyUI job {prompt_id} exceeded the generation timeout.",
            last_raw_response,
        )

    def _get_history(self, prompt_id: str) -> tuple[dict[str, Any], str]:
        url = f"{self._base_url}/history/{prompt_id}"
        try:
            response = self._session.get(
                url,
                timeout=self._config.request_timeout_seconds,
            )
        except requests.RequestException as error:
            raise AdapterError(f"ComfyUI history request failed: {error}") from error

        raw_response = response.text
        try:
            response.raise_for_status()
            data = response.json()
            if not isinstance(data, dict):
                raise TypeError("history response is not an object")
        except (requests.HTTPError, TypeError, ValueError) as error:
            raise AdapterError(
                "ComfyUI returned invalid history data.",
                raw_response,
            ) from error
        return data, raw_response

    def _download_image(
        self,
        image_info: dict[str, Any],
        destination: Path,
    ) -> None:
        params = {
            "filename": image_info["filename"],
            "subfolder": image_info.get("subfolder", ""),
            "type": image_info.get("type", "output"),
        }
        try:
            response = self._session.get(
                f"{self._base_url}/view",
                params=params,
                timeout=self._config.request_timeout_seconds,
            )
            response.raise_for_status()
        except requests.RequestException as error:
            raw_response = getattr(error.response, "text", None)
            raise AdapterError(
                f"Could not download the ComfyUI image: {error}",
                raw_response,
            ) from error

        temporary_path = destination.with_suffix(f"{destination.suffix}.part")
        temporary_path.write_bytes(response.content)
        temporary_path.replace(destination)


def build_comfyui_image_generator(
    raw_settings: dict[str, Any],
) -> ComfyUIImageGenerator:
    settings = ComfyUIImageSettings.model_validate(raw_settings)
    return ComfyUIImageGenerator(settings)


def _execution_error_message(status: dict[str, Any]) -> str:
    """Return ComfyUI's most useful execution-error message."""
    for message in reversed(status.get("messages", [])):
        if not isinstance(message, list) or len(message) != 2:
            continue
        event, details = message
        if event != "execution_error" or not isinstance(details, dict):
            continue
        error = details.get("exception_message")
        if isinstance(error, str) and error.strip():
            return error.strip()
    return "ComfyUI reported an execution error."
