"""Provider-independent work performed by individual pipeline stages."""

from pathlib import Path

from semantic_roundtrip.adapters.errors import AdapterError
from semantic_roundtrip.adapters.factory import AdapterBundle
from semantic_roundtrip.config import PredictionInputKind, ResolvedAppConfig
from semantic_roundtrip.config_resolution import configured_prediction_inputs
from semantic_roundtrip.domain import (
    BenchmarkItem,
    GeneratedPrompt,
)
from semantic_roundtrip.evaluation import (
    EXACT_MATCH_METHOD,
    title_exact_match,
)
from semantic_roundtrip.persistence.run.database import RunDatabase
from semantic_roundtrip.persistence.run.results import ImageWorkItem
from semantic_roundtrip.pipeline.tasks import (
    load_or_run_single,
    raise_if_pause_requested,
    run_task,
)
from semantic_roundtrip.prompting import PromptProfile, render_prompt_profile


def _load_or_generate_prompt(
    *,
    database: RunDatabase,
    adapters: AdapterBundle,
    prompt_profile: PromptProfile,
    item: BenchmarkItem,
    item_id: int,
    prompt_index: int,
    sampling_seed: int,
    retry_limit: int,
) -> tuple[int, GeneratedPrompt] | None:
    raise_if_pause_requested(database)
    task = database.tasks.get_or_create(
        task_key=f"prompt_generation:{item.item_key}:{prompt_index}",
        stage="prompt_generation",
        expected_outputs=1,
        item_id=item_id,
        seed=sampling_seed,
    )
    existing = database.results.get_prompt(item_id, prompt_index)

    if existing is not None:
        if task.status != "completed":
            database.tasks.mark_completed(task.task_id, 1)
        return existing

    if task.status == "completed":
        raise RuntimeError(f"Task {task.task_key} is completed but has no prompt.")
    if task.status == "failed":
        return None

    messages = render_prompt_profile(
        prompt_profile,
        title=item.title,
        domain=item.domain,
        prompt_index=prompt_index,
    )

    def generate() -> tuple[int, GeneratedPrompt]:
        response = adapters.prompt_generator.generate_prompt(
            messages=messages,
            seed=sampling_seed,
        )
        prompt = GeneratedPrompt(index=prompt_index, text=response.text)
        prompt_id = database.results.add_prompt(
            item_id=item_id,
            prompt=prompt,
            sampling_seed=sampling_seed,
            response=response,
        )
        return prompt_id, prompt

    try:
        return run_task(
            generate,
            database=database,
            task=task,
            retry_limit=retry_limit,
            item_id=item_id,
        )
    except AdapterError:
        return None


def _image_task_suffix(image: ImageWorkItem) -> str:
    return f"{image.item.item_key}:{image.prompt.index}:{image.image.seed}"


def execute_prompt_generation_stage(
    *,
    config: ResolvedAppConfig,
    database: RunDatabase,
    adapters: AdapterBundle,
    prompt_profile: PromptProfile,
) -> None:
    """Generate every missing visual prompt before the next stage starts."""
    for item_index, configured_item in enumerate(config.dataset.items):
        item = BenchmarkItem(
            item_key=configured_item.id,
            domain=configured_item.domain,
            title=configured_item.title,
        )
        item_id = database.results.get_or_add_dataset_item(item_index, item)
        for prompt_index, sampling_seed in enumerate(config.experiment.prompt_seeds):
            _load_or_generate_prompt(
                database=database,
                adapters=adapters,
                prompt_profile=prompt_profile,
                item=item,
                item_id=item_id,
                prompt_index=prompt_index,
                sampling_seed=sampling_seed,
                retry_limit=config.experiment.retry_limit,
            )


def execute_image_generation_stage(
    *,
    config: ResolvedAppConfig,
    database: RunDatabase,
    images_directory: Path,
    adapters: AdapterBundle,
) -> None:
    """Generate every missing image from the persisted prompts."""
    for prompt in database.results.list_prompts():
        for seed in config.experiment.image_seeds:
            task_suffix = f"{prompt.item.item_key}:{prompt.prompt.index}:{seed}"
            load_or_run_single(
                database=database,
                stage="image_generation",
                task_suffix=task_suffix,
                existing=database.results.get_image(prompt.prompt_id, seed),
                operation=lambda: adapters.image_generator.generate_image(
                    prompt=prompt.prompt.text,
                    seed=seed,
                    output_directory=(images_directory / f"prompt_{prompt.prompt_id}"),
                ),
                save=lambda result: database.results.add_image(
                    prompt.prompt_id,
                    result,
                ),
                retry_limit=config.experiment.retry_limit,
                item_id=prompt.item_id,
                prompt_id=prompt.prompt_id,
                seed=seed,
            )


def execute_verification_stage(
    *,
    config: ResolvedAppConfig,
    database: RunDatabase,
    adapters: AdapterBundle,
) -> None:
    """Verify every persisted image before title guessing starts."""
    for image in database.results.list_images():
        load_or_run_single(
            database=database,
            stage="verification",
            task_suffix=_image_task_suffix(image),
            existing=database.results.get_verification(image.image_id),
            operation=lambda: adapters.image_verifier.verify_image(
                image_path=image.image.path
            ),
            save=lambda result: database.results.add_verification(
                image.image_id,
                result,
            ),
            retry_limit=config.experiment.retry_limit,
            item_id=image.item_id,
            prompt_id=image.prompt_id,
            seed=image.image.seed,
            image_id=image.image_id,
        )


def execute_image_description_stage(
    *,
    config: ResolvedAppConfig,
    database: RunDatabase,
    adapters: AdapterBundle,
) -> None:
    """Describe every persisted image when the optional route is configured."""
    if config.stages.image_description is None:
        return
    if adapters.image_describer is None:
        raise RuntimeError(
            "Image-description configuration has no image-describer adapter."
        )

    for image in database.results.list_images():
        load_or_run_single(
            database=database,
            stage="image_description",
            task_suffix=_image_task_suffix(image),
            existing=database.results.get_image_description(image.image_id),
            operation=lambda: adapters.image_describer.describe_image(
                image_path=image.image.path,
                domain=image.item.domain,
            ),
            save=lambda result: database.results.add_image_description(
                image.image_id,
                result,
            ),
            retry_limit=config.experiment.retry_limit,
            item_id=image.item_id,
            prompt_id=image.prompt_id,
            seed=image.image.seed,
            image_id=image.image_id,
        )


def execute_direct_title_guessing_stage(
    *,
    config: ResolvedAppConfig,
    database: RunDatabase,
    adapters: AdapterBundle,
) -> None:
    """Guess every title directly from its persisted image."""
    if config.stages.title_guessing.direct is None:
        return

    if adapters.image_title_guesser is None:
        raise RuntimeError("Direct title guessing has no image-title adapter.")

    for image in database.results.list_images():
        load_or_run_single(
            database=database,
            stage="title_guessing_direct",
            task_suffix=_image_task_suffix(image),
            existing=database.results.get_prediction(image.image_id, "image"),
            operation=lambda: adapters.image_title_guesser.guess_title(
                image_path=image.image.path,
                domain=image.item.domain,
            ),
            save=lambda result: database.results.add_prediction(
                image.image_id,
                result,
                input_kind="image",
            ),
            retry_limit=config.experiment.retry_limit,
            item_id=image.item_id,
            prompt_id=image.prompt_id,
            seed=image.image.seed,
            image_id=image.image_id,
        )


def execute_description_title_guessing_stage(
    *,
    config: ResolvedAppConfig,
    database: RunDatabase,
    adapters: AdapterBundle,
) -> None:
    """Guess every title from its persisted image description."""
    if config.stages.title_guessing.from_description is None:
        return

    if adapters.text_title_guesser is None:
        raise RuntimeError("Description title guessing has no text-title adapter.")

    for image in database.results.list_images():
        stored_description = database.results.get_image_description(image.image_id)
        if stored_description is None:
            continue
        description_id, description = stored_description

        load_or_run_single(
            database=database,
            stage="title_guessing_from_description",
            task_suffix=_image_task_suffix(image),
            existing=database.results.get_prediction(image.image_id, "description"),
            operation=lambda: adapters.text_title_guesser.guess_title(
                description=description.text,
                domain=image.item.domain,
            ),
            save=lambda result: database.results.add_prediction(
                image.image_id,
                result,
                input_kind="description",
                description_id=description_id,
            ),
            retry_limit=config.experiment.retry_limit,
            item_id=image.item_id,
            prompt_id=image.prompt_id,
            seed=image.image.seed,
            image_id=image.image_id,
        )


def execute_evaluation_stage(
    *,
    config: ResolvedAppConfig,
    database: RunDatabase,
) -> None:
    """Evaluate every persisted prediction as an independently resumable task."""
    for image in database.results.list_images():
        verification_entry = database.results.get_verification(image.image_id)
        if verification_entry is None:
            continue

        verification_id, _ = verification_entry
        for input_kind in configured_prediction_inputs(config):
            _evaluate_prediction(
                database=database,
                image=image,
                verification_id=verification_id,
                input_kind=input_kind,
            )


def _evaluate_prediction(
    *,
    database: RunDatabase,
    image: ImageWorkItem,
    verification_id: int,
    input_kind: PredictionInputKind,
) -> None:
    """Evaluate one configured prediction route for one image."""
    raise_if_pause_requested(database)
    prediction_entry = database.results.get_prediction(image.image_id, input_kind)
    if prediction_entry is None:
        return

    prediction_id, prediction = prediction_entry
    task = database.tasks.get_or_create(
        task_key=f"evaluation:{input_kind}:{_image_task_suffix(image)}",
        stage="evaluation",
        expected_outputs=1,
        item_id=image.item_id,
        prompt_id=image.prompt_id,
        image_id=image.image_id,
        seed=image.image.seed,
    )
    evaluation_id = database.results.get_evaluation_id(prediction_id)
    if evaluation_id is not None:
        if task.status != "completed":
            database.tasks.mark_completed(task.task_id, 1)
        return
    if task.status == "completed":
        raise RuntimeError(f"Task {task.task_key} is completed but has no evaluation.")

    def evaluate() -> int:
        exact_match = title_exact_match(image.item.title, prediction.title)
        return database.results.add_evaluation_if_missing(
            verification_id=verification_id,
            prediction_id=prediction_id,
            exact_match=exact_match,
            exact_method=EXACT_MATCH_METHOD,
        )

    run_task(
        evaluate,
        database=database,
        task=task,
        retry_limit=0,
        item_id=image.item_id,
        prompt_id=image.prompt_id,
        image_id=image.image_id,
    )
