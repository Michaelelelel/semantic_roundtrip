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


class ComfyUIImageSettings(ConfigModel):
    """Settings for ComfyUI image generation."""

    base_url: str = Field(min_length=1)
    model_id: str = Field(min_length=1)
    workflow_path: Path
    checkpoint: str = Field(min_length=1)
    sampler_node_id: str = "3"
    checkpoint_node_id: str = "4"
    positive_prompt_node_id: str = "6"
    save_image_node_id: str = "9"
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
        try:
            workflow[self._config.positive_prompt_node_id]["inputs"]["text"] = prompt
            workflow[self._config.sampler_node_id]["inputs"]["seed"] = seed
            workflow[self._config.checkpoint_node_id]["inputs"]["ckpt_name"] = (
                self._config.checkpoint
            )
            workflow[self._config.save_image_node_id]["inputs"]["filename_prefix"] = (
                f"semantic_roundtrip_{identifier}"
            )
        except KeyError as error:
            raise AdapterError(
                f"Configured ComfyUI workflow node or input is missing: {error}"
            ) from error
        return workflow

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
                if isinstance(status, dict) and status.get("completed"):
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
