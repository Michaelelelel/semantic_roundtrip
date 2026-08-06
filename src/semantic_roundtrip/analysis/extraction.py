"""Convert persisted run state into deterministic expected prediction rows."""

from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path

from semantic_roundtrip.analysis.models import ExtractedRun, PredictionRecord
from semantic_roundtrip.config import ResolvedAppConfig, StageName
from semantic_roundtrip.config_resolution import (
    STAGE_NAMES,
    configured_prediction_inputs,
    get_stage_config,
    load_effective_config,
)
from semantic_roundtrip.evaluation import (
    EXACT_MATCH_METHOD,
    NORMALIZED_EXACT_METHOD,
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


ANALYZABLE_RUN_STATUSES = frozenset({"completed", "failed", "interrupted"})
ACTIVE_RUN_STATUSES = frozenset({"running", "pausing"})


@dataclass(frozen=True, slots=True)
class BackendIdentity:
    alias: str
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
    return BackendIdentity(alias=stage.backend, model=str(model))


def _optional_backend_identity(
    config: ResolvedAppConfig,
    stage_name: StageName,
) -> BackendIdentity | None:
    if get_stage_config(config, stage_name) is None:
        return None
    return _backend_identity(config, stage_name)


def _stack_id(config: ResolvedAppConfig) -> str:
    parts: list[str] = []
    for stage_name in STAGE_NAMES:
        identity = _optional_backend_identity(config, stage_name)
        if identity is not None:
            parts.append(f"{stage_name}={identity.model}")
    return " | ".join(parts)


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
        "evaluation",
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


def _validate_run_state(status: str, *, require_terminal: bool) -> None:
    if status in ACTIVE_RUN_STATUSES:
        raise ValueError(f"Cannot evaluate a run while its status is '{status}'.")
    if require_terminal and status not in ANALYZABLE_RUN_STATUSES:
        raise ValueError(
            f"Run status '{status}' is not terminal; complete or stop it first."
        )


def extract_run(
    run_directory: Path,
    *,
    job_id: str | None = None,
    job_entry: str | None = None,
    require_terminal: bool = True,
) -> ExtractedRun:
    """Create every expected image-route row for one persisted run."""
    run_directory = run_directory.resolve()
    database_path = database_path_for_run(run_directory)
    run_record = read_run_record(database_path)
    _validate_run_state(run_record.status, require_terminal=require_terminal)
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

    prompt_backend = _backend_identity(config, "prompt_generation")
    image_backend = _backend_identity(config, "image_generation")
    verifier_backend = _backend_identity(config, "verification")
    describer_backend = _optional_backend_identity(config, "image_description")
    route_backends = {
        "image": _optional_backend_identity(config, "title_guessing_direct"),
        "description": _optional_backend_identity(
            config,
            "title_guessing_from_description",
        ),
    }
    stack_id = _stack_id(config)
    records: list[PredictionRecord] = []

    for item_index, item in enumerate(config.dataset.items):
        for prompt_index in range(config.experiment.prompts_per_title):
            prompt = prompts.get((item.id, prompt_index))
            expected_prompt_seed = config.experiment.prompt_seed + prompt_index
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
                    backend = route_backends[input_kind]
                    if backend is None:
                        raise ValueError(
                            f"Missing backend for configured {route} route."
                        )
                    prediction: StoredPrediction | None = None
                    if image is not None:
                        prediction = predictions.get((image.image_id, input_kind))
                    error = _latest_matching_error(
                        stored.errors,
                        item_id=item.id,
                        prompt=prompt,
                        image=image,
                        image_seed=image_seed,
                        prediction_stage=prediction_stage,
                    )

                    if prediction is None:
                        prediction_status = "failed" if error is not None else "missing"
                    elif prediction.exact_match is None:
                        prediction_status = "incomplete_evaluation"
                    else:
                        prediction_status = "completed"

                    exact_match: bool | None = None
                    normalized_match: bool | None = None
                    if prediction is not None and prediction.exact_match is not None:
                        if prediction.exact_method != EXACT_MATCH_METHOD:
                            raise ValueError(
                                f"Unsupported exact-match method for prediction "
                                f"{prediction.prediction_id}: "
                                f"{prediction.exact_method!r}"
                            )
                        calculated_exact = title_exact_match(
                            item.title,
                            prediction.title,
                        )
                        if calculated_exact != prediction.exact_match:
                            raise ValueError(
                                f"Stored exact-match result for prediction "
                                f"{prediction.prediction_id} is inconsistent."
                            )
                        exact_match = prediction.exact_match
                        normalized_match = title_normalized_exact_match(
                            item.title,
                            prediction.title,
                        )

                    verification_passed = (
                        image is not None and image.verification_passed is True
                    )

                    records.append(
                        PredictionRecord(
                            job_id=job_id,
                            job_entry=job_entry,
                            run_id=run_record.run_id,
                            experiment_name=run_record.name,
                            run_status=run_record.status,
                            stack_id=stack_id,
                            dataset_id=config.dataset.dataset_id,
                            item_id=item.id,
                            item_index=item_index,
                            domain=item.domain,
                            expected_title=item.title,
                            prompt_index=prompt_index,
                            prompt_seed=expected_prompt_seed,
                            prompt_id=None if prompt is None else prompt.prompt_id,
                            prompt_text=None if prompt is None else prompt.text,
                            prompt_backend=prompt_backend.alias,
                            prompt_model=prompt_backend.model,
                            image_seed=image_seed,
                            image_id=None if image is None else image.image_id,
                            image_path=None if image is None else image.path,
                            image_backend=image_backend.alias,
                            image_model=image_backend.model,
                            verification_passed=(
                                None if image is None else image.verification_passed
                            ),
                            verification_reason=(
                                None if image is None else image.verification_reason
                            ),
                            verifier_backend=verifier_backend.alias,
                            verifier_model=verifier_backend.model,
                            image_description=(
                                None if image is None else image.description
                            ),
                            describer_backend=(
                                None
                                if describer_backend is None
                                else describer_backend.alias
                            ),
                            describer_model=(
                                None
                                if describer_backend is None
                                else describer_backend.model
                            ),
                            route=route,
                            prediction_input=input_kind,
                            prediction_backend=backend.alias,
                            prediction_model=backend.model,
                            prediction_status=prediction_status,
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
                            exact_match=exact_match,
                            normalized_exact_match=normalized_match,
                            exact_method=(
                                None if prediction is None else prediction.exact_method
                            ),
                            normalized_method=(
                                NORMALIZED_EXACT_METHOD
                                if normalized_match is not None
                                else None
                            ),
                            end_to_end_score=int(
                                verification_passed and exact_match is True
                            ),
                            normalized_end_to_end_score=int(
                                verification_passed and normalized_match is True
                            ),
                            error_stage=None if error is None else error.stage,
                            error_type=None if error is None else error.error_type,
                            error_message=None if error is None else error.message,
                        )
                    )

    return ExtractedRun(
        run_id=run_record.run_id,
        experiment_name=run_record.name,
        run_status=run_record.status,
        records=tuple(records),
        tasks=stored.tasks,
        runtime_events=stored.runtime_events,
    )
