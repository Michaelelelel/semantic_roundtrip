"""Provider-independent orchestration of semantic round-trip experiments."""

from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from typing import TypeVar

from semantic_roundtrip.adapters.factory import AdapterBundle
from semantic_roundtrip.config import AppConfig
from semantic_roundtrip.domain import BenchmarkItem
from semantic_roundtrip.evaluation import (
    EVALUATION_METHOD,
    apply_verification_policy,
    title_exact_match,
)
from semantic_roundtrip.persistence.database import RunDatabase
from semantic_roundtrip.persistence.run_manager import RunContext


ResultType = TypeVar("ResultType")


@dataclass(frozen=True, slots=True)
class PipelineSummary:
    """Counts of the records produced by one completed pipeline run."""

    dataset_items: int
    prompts: int
    images: int
    verifications: int
    predictions: int
    evaluations: int


def _run_stage(
    operation: Callable[[], ResultType],
    *,
    database: RunDatabase,
    stage: str,
    retry_limit: int,
    item_id: int | None = None,
    prompt_id: int | None = None,
    image_id: int | None = None,
) -> ResultType:
    """Run one adapter call and persist every failed attempt."""
    for attempt in range(1, retry_limit + 2):
        try:
            return operation()
        except Exception as error:
            database.add_stage_error(
                stage=stage,
                attempt=attempt,
                error=error,
                item_id=item_id,
                prompt_id=prompt_id,
                image_id=image_id,
            )
            if attempt > retry_limit:
                raise

    raise RuntimeError("Stage retry loop ended unexpectedly")


def run_pipeline(
    *,
    config: AppConfig,
    run_context: RunContext,
    database_path: Path,
    images_directory: Path,
    adapters: AdapterBundle,
) -> PipelineSummary:
    """Execute and persist one complete semantic round-trip experiment."""
    prompt_count = 0
    image_count = 0
    verification_count = 0
    prediction_count = 0
    evaluation_count = 0

    with RunDatabase(database_path, run_context) as database:
        database.update_run_status("running")

        try:
            for item_index, configured_item in enumerate(config.dataset.items):
                item = BenchmarkItem(
                    domain=configured_item.domain,
                    title=configured_item.title,
                )
                item_id = database.add_dataset_item(item_index, item)

                prompts = _run_stage(
                    lambda: adapters.prompt_generator.generate_prompts(
                        title=item.title,
                        domain=item.domain,
                        count=config.experiment.prompts_per_title,
                    ),
                    database=database,
                    stage="prompt_generation",
                    retry_limit=config.experiment.retry_limit,
                    item_id=item_id,
                )

                for prompt in prompts:
                    prompt_id = database.add_prompt(item_id, prompt)
                    prompt_count += 1

                    for seed in config.experiment.seeds:
                        image = _run_stage(
                            lambda: adapters.image_generator.generate_image(
                                prompt=prompt.text,
                                seed=seed,
                                output_directory=images_directory,
                            ),
                            database=database,
                            stage="image_generation",
                            retry_limit=config.experiment.retry_limit,
                            item_id=item_id,
                            prompt_id=prompt_id,
                        )
                        image_id = database.add_image(prompt_id, image)
                        image_count += 1

                        verification = _run_stage(
                            lambda: adapters.image_verifier.verify_image(
                                image_path=image.path
                            ),
                            database=database,
                            stage="verification",
                            retry_limit=config.experiment.retry_limit,
                            item_id=item_id,
                            prompt_id=prompt_id,
                            image_id=image_id,
                        )
                        verification_id = database.add_verification(
                            image_id,
                            verification,
                        )
                        verification_count += 1

                        prediction = _run_stage(
                            lambda: adapters.title_guesser.guess_title(
                                image_path=image.path,
                                domain=item.domain,
                            ),
                            database=database,
                            stage="title_guessing",
                            retry_limit=config.experiment.retry_limit,
                            item_id=item_id,
                            prompt_id=prompt_id,
                            image_id=image_id,
                        )
                        prediction_id = database.add_prediction(
                            image_id,
                            prediction,
                        )
                        prediction_count += 1

                        title_matches = title_exact_match(
                            item.title,
                            prediction.title,
                        )
                        included, score = apply_verification_policy(
                            title_matches=title_matches,
                            verification_passed=verification.passed,
                            failed_verification=(config.evaluation.failed_verification),
                        )
                        database.add_evaluation(
                            verification_id=verification_id,
                            prediction_id=prediction_id,
                            title_exact_match=title_matches,
                            included=included,
                            score=score,
                            method=EVALUATION_METHOD,
                        )
                        evaluation_count += 1
        except Exception:
            database.update_run_status("failed")
            raise

        database.update_run_status("completed")

    return PipelineSummary(
        dataset_items=len(config.dataset.items),
        prompts=prompt_count,
        images=image_count,
        verifications=verification_count,
        predictions=prediction_count,
        evaluations=evaluation_count,
    )
