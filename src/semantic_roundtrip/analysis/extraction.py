"""Convert one persisted run into every expected study observation."""

from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path

from semantic_roundtrip.analysis.models import ExtractedRun, Observation
from semantic_roundtrip.config import ResolvedAppConfig, StageName
from semantic_roundtrip.config_resolution import (
    configured_prediction_inputs,
    get_stage_config,
    load_effective_config,
)
from semantic_roundtrip.evaluation import (
    title_exact_match,
    title_normalized_exact_match,
)
from semantic_roundtrip.persistence.run.analysis_queries import (
    StoredImage,
    StoredPrediction,
    StoredPrompt,
    StoredStageError,
    read_analysis_rows,
)
from semantic_roundtrip.persistence.run.config_snapshot import (
    EFFECTIVE_CONFIG_FILENAME,
)
from semantic_roundtrip.persistence.run.queries import read_run_record
from semantic_roundtrip.persistence.run.schema import database_path_for_run


@dataclass(frozen=True, slots=True)
class BackendIdentity:
    model: str


def _backend_identity(
    config: ResolvedAppConfig,
    stage_name: StageName,
) -> BackendIdentity:
    stage = get_stage_config(config, stage_name)
    if stage is None:
        raise ValueError(f"Stage '{stage_name}' is not configured.")
    backend = config.backends[stage.backend]
    model = (
        backend.settings.get("model_id")
        or backend.settings.get("checkpoint")
        or backend.adapter
    )
    return BackendIdentity(model=str(model))


def _optional_backend_identity(
    config: ResolvedAppConfig,
    stage_name: StageName,
) -> BackendIdentity | None:
    if get_stage_config(config, stage_name) is None:
        return None
    return _backend_identity(config, stage_name)


def _unique_map[T, K](
    values: tuple[T, ...],
    key: Callable[[T], K],
    label: str,
) -> dict[K, T]:
    result: dict[K, T] = {}
    for value in values:
        item_key = key(value)
        if item_key in result:
            raise ValueError(f"Duplicate {label} identity: {item_key}")
        result[item_key] = value
    return result


def _latest_matching_error(
    errors: tuple[StoredStageError, ...],
    *,
    item_id: str,
    prompt: StoredPrompt | None,
    image: StoredImage | None,
    image_seed: int,
    prediction_stage: str,
) -> StoredStageError | None:
    relevant_stages = {
        "prompt_generation",
        "image_generation",
        "verification",
        prediction_stage,
    }
    if prediction_stage == "title_guessing_from_description":
        relevant_stages.add("image_description")

    for error in reversed(errors):
        if error.stage not in relevant_stages:
            continue
        if image is not None and error.image_id == image.image_id:
            return error
        if (
            image is None
            and prompt is not None
            and error.prompt_id == prompt.prompt_id
            and error.stage == "image_generation"
            and error.seed == image_seed
        ):
            return error
        if prompt is None and error.item_key == item_id:
            return error
    return None


def extract_run(
    run_directory: Path,
    *,
    condition_id: str,
    condition_label: str,
) -> ExtractedRun:
    """Read one completed run without depending on its stored evaluation rows."""
    run_directory = run_directory.resolve()
    database_path = database_path_for_run(run_directory)
    run_record = read_run_record(database_path)
    if run_record.status != "completed":
        raise ValueError(
            f"Study condition '{condition_id}' uses run status "
            f"'{run_record.status}'; only completed runs can be analyzed."
        )

    config = load_effective_config(run_directory / EFFECTIVE_CONFIG_FILENAME)
    if config.run.name != run_record.name:
        raise ValueError("Run snapshot and database names do not match.")

    stored = read_analysis_rows(database_path)
    prompts = _unique_map(
        stored.prompts,
        lambda prompt: (prompt.item_key, prompt.prompt_index),
        "prompt",
    )
    images = _unique_map(
        stored.images,
        lambda image: (image.item_key, image.prompt_index, image.image_seed),
        "image",
    )
    predictions = _unique_map(
        stored.predictions,
        lambda prediction: (prediction.image_id, prediction.input_kind),
        "prediction",
    )

    prompt_model = _backend_identity(config, "prompt_generation").model
    image_model = _backend_identity(config, "image_generation").model
    verifier_model = _backend_identity(config, "verification").model
    describer = _optional_backend_identity(config, "image_description")
    route_models = {
        "image": _optional_backend_identity(config, "title_guessing_direct"),
        "description": _optional_backend_identity(
            config,
            "title_guessing_from_description",
        ),
    }
    records: list[Observation] = []

    for item_index, item in enumerate(config.dataset.items):
        for prompt_index, expected_prompt_seed in enumerate(
            config.experiment.prompt_seeds
        ):
            prompt = prompts.get((item.id, prompt_index))
            if prompt is not None and prompt.sampling_seed != expected_prompt_seed:
                raise ValueError(
                    f"Stored prompt seed for {item.id}:{prompt_index} differs "
                    "from the effective configuration."
                )

            for image_seed in config.experiment.image_seeds:
                image = images.get((item.id, prompt_index, image_seed))
                for input_kind in configured_prediction_inputs(config):
                    route = "direct" if input_kind == "image" else "description"
                    prediction_stage = (
                        "title_guessing_direct"
                        if input_kind == "image"
                        else "title_guessing_from_description"
                    )
                    route_model = route_models[input_kind]
                    if route_model is None:
                        raise ValueError(f"Missing model for configured {route} route.")

                    prediction: StoredPrediction | None = None
                    if image is not None:
                        prediction = predictions.get((image.image_id, input_kind))
                    error = None
                    if prediction is None:
                        error = _latest_matching_error(
                            stored.errors,
                            item_id=item.id,
                            prompt=prompt,
                            image=image,
                            image_seed=image_seed,
                            prediction_stage=prediction_stage,
                        )

                    strict_match = (
                        None
                        if prediction is None
                        else title_exact_match(item.title, prediction.title)
                    )
                    normalized_match = (
                        None
                        if prediction is None
                        else title_normalized_exact_match(item.title, prediction.title)
                    )
                    verification_passed = (
                        image is not None and image.verification_passed is True
                    )

                    records.append(
                        Observation(
                            condition_id=condition_id,
                            condition_label=condition_label,
                            run_id=run_record.run_id,
                            experiment_name=run_record.name,
                            dataset_id=config.dataset.dataset_id,
                            item_id=item.id,
                            item_index=item_index,
                            domain=item.domain,
                            expected_title=item.title,
                            prompt_index=prompt_index,
                            prompt_seed=expected_prompt_seed,
                            prompt_id=None if prompt is None else prompt.prompt_id,
                            prompt_text=None if prompt is None else prompt.text,
                            prompt_model=prompt_model,
                            image_seed=image_seed,
                            image_id=None if image is None else image.image_id,
                            image_path=None if image is None else image.path,
                            image_model=image_model,
                            verification_passed=(
                                None if image is None else image.verification_passed
                            ),
                            verification_reason=(
                                None if image is None else image.verification_reason
                            ),
                            verifier_model=verifier_model,
                            image_description=(
                                None if image is None else image.description
                            ),
                            describer_model=(
                                None if describer is None else describer.model
                            ),
                            route=route,
                            prediction_model=route_model.model,
                            prediction_status=(
                                "completed"
                                if prediction is not None
                                else "failed"
                                if error is not None
                                else "missing"
                            ),
                            prediction_id=(
                                None if prediction is None else prediction.prediction_id
                            ),
                            predicted_title=(
                                None if prediction is None else prediction.title
                            ),
                            confidence=(
                                None if prediction is None else prediction.confidence
                            ),
                            confidence_type=(
                                None
                                if prediction is None
                                else prediction.confidence_type
                            ),
                            strict_exact_match=strict_match,
                            normalized_exact_match=normalized_match,
                            end_to_end_strict_score=int(
                                verification_passed and strict_match is True
                            ),
                            end_to_end_normalized_score=int(
                                verification_passed and normalized_match is True
                            ),
                            error_stage=None if error is None else error.stage,
                            error_type=None if error is None else error.error_type,
                            error_message=None if error is None else error.message,
                        )
                    )

    return ExtractedRun(
        condition_id=condition_id,
        condition_label=condition_label,
        run_directory=run_directory,
        run_id=run_record.run_id,
        experiment_name=run_record.name,
        records=tuple(records),
        tasks=stored.tasks,
        runtime_events=stored.runtime_events,
    )
