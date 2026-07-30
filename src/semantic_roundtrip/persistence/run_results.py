"""Persistence for successful pipeline inputs and outputs."""

import sqlite3
from dataclasses import dataclass
from pathlib import Path
from typing import Literal

from semantic_roundtrip.domain import (
    BenchmarkItem,
    GeneratedPrompt,
    ImageArtifact,
    ImageDescription,
    PromptResponse,
    TitlePrediction,
    VerificationResult,
)
from semantic_roundtrip.persistence.run_manager import RunContext
from semantic_roundtrip.persistence.sqlite import utc_now


@dataclass(frozen=True, slots=True)
class ResultCounts:
    dataset_items: int
    prompts: int
    images: int
    verifications: int
    image_descriptions: int
    predictions: int
    evaluations: int


@dataclass(frozen=True, slots=True)
class PromptWorkItem:
    """One persisted prompt together with its source benchmark item."""

    item_id: int
    item_index: int
    item: BenchmarkItem
    prompt_id: int
    prompt: GeneratedPrompt


@dataclass(frozen=True, slots=True)
class ImageWorkItem:
    """One persisted image together with its prompt and benchmark item."""

    item_id: int
    item_index: int
    item: BenchmarkItem
    prompt_id: int
    prompt: GeneratedPrompt
    image_id: int
    image: ImageArtifact


def _relative_path(path: Path, run_directory: Path) -> str:
    return path.relative_to(run_directory).as_posix()


class RunResultStore:
    """Read and write successful artifacts for one experiment run."""

    def __init__(
        self,
        connection: sqlite3.Connection,
        run_context: RunContext,
    ) -> None:
        self._connection = connection
        self._run_context = run_context

    def _insert(self, statement: str, parameters: tuple[object, ...]) -> int:
        with self._connection:
            cursor = self._connection.execute(statement, parameters)
        return int(cursor.lastrowid)

    def get_or_add_dataset_item(
        self,
        item_index: int,
        item: BenchmarkItem,
    ) -> int:
        row = self._connection.execute(
            """
            SELECT item_id, domain, title
            FROM dataset_items
            WHERE run_id = ? AND item_index = ?
            """,
            (self._run_context.run_id, item_index),
        ).fetchone()
        if row is not None:
            if row["domain"] != item.domain or row["title"] != item.title:
                raise ValueError(
                    f"Stored dataset item {item_index} differs from the snapshot."
                )
            return int(row["item_id"])

        return self._insert(
            """
            INSERT INTO dataset_items (run_id, item_index, domain, title)
            VALUES (?, ?, ?, ?)
            """,
            (
                self._run_context.run_id,
                item_index,
                item.domain,
                item.title,
            ),
        )

    def get_prompt(
        self,
        item_id: int,
        prompt_index: int,
    ) -> tuple[int, GeneratedPrompt] | None:
        row = self._connection.execute(
            """
            SELECT prompt_id, prompt_index, text
            FROM prompts
            WHERE item_id = ? AND prompt_index = ?
            """,
            (item_id, prompt_index),
        ).fetchone()
        if row is None:
            return None
        return (
            int(row["prompt_id"]),
            GeneratedPrompt(index=int(row["prompt_index"]), text=row["text"]),
        )

    def add_prompt(
        self,
        *,
        item_id: int,
        prompt: GeneratedPrompt,
        sampling_seed: int,
        response: PromptResponse,
    ) -> int:
        """Persist one successful prompt-generation response."""
        return self._insert(
            """
            INSERT INTO prompts (
                item_id,
                prompt_index,
                sampling_seed,
                text,
                backend_request_id,
                raw_response,
                created_at
            )
            VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            (
                item_id,
                prompt.index,
                sampling_seed,
                prompt.text,
                response.backend_request_id,
                response.raw_response,
                utc_now(),
            ),
        )

    def list_prompts(self) -> list[PromptWorkItem]:
        """Return stored prompts in deterministic dataset and prompt order."""
        rows = self._connection.execute(
            """
            SELECT
                items.item_id,
                items.item_index,
                items.domain,
                items.title,
                prompts.prompt_id,
                prompts.prompt_index,
                prompts.text
            FROM prompts
            JOIN dataset_items AS items
                ON items.item_id = prompts.item_id
            WHERE items.run_id = ?
            ORDER BY items.item_index, prompts.prompt_index
            """,
            (self._run_context.run_id,),
        ).fetchall()
        return [
            PromptWorkItem(
                item_id=int(row["item_id"]),
                item_index=int(row["item_index"]),
                item=BenchmarkItem(domain=row["domain"], title=row["title"]),
                prompt_id=int(row["prompt_id"]),
                prompt=GeneratedPrompt(
                    index=int(row["prompt_index"]),
                    text=row["text"],
                ),
            )
            for row in rows
        ]

    def get_image(
        self,
        prompt_id: int,
        seed: int,
    ) -> tuple[int, ImageArtifact] | None:
        row = self._connection.execute(
            """
            SELECT image_id, path, seed, raw_response, backend_job_id
            FROM images
            WHERE prompt_id = ? AND seed = ?
            """,
            (prompt_id, seed),
        ).fetchone()
        if row is None:
            return None
        return (
            int(row["image_id"]),
            ImageArtifact(
                path=self._run_context.directory / row["path"],
                seed=int(row["seed"]),
                raw_response=row["raw_response"],
                backend_job_id=row["backend_job_id"],
            ),
        )

    def add_image(self, prompt_id: int, image: ImageArtifact) -> int:
        return self._insert(
            """
            INSERT INTO images (
                prompt_id,
                seed,
                path,
                backend_job_id,
                raw_response
            )
            VALUES (?, ?, ?, ?, ?)
            """,
            (
                prompt_id,
                image.seed,
                _relative_path(image.path, self._run_context.directory),
                image.backend_job_id,
                image.raw_response,
            ),
        )

    def list_images(self) -> list[ImageWorkItem]:
        """Return stored images in deterministic dataset, prompt, and seed order."""
        rows = self._connection.execute(
            """
            SELECT
                items.item_id,
                items.item_index,
                items.domain,
                items.title,
                prompts.prompt_id,
                prompts.prompt_index,
                prompts.text,
                images.image_id,
                images.path,
                images.seed,
                images.raw_response,
                images.backend_job_id
            FROM images
            JOIN prompts
                ON prompts.prompt_id = images.prompt_id
            JOIN dataset_items AS items
                ON items.item_id = prompts.item_id
            WHERE items.run_id = ?
            ORDER BY items.item_index, prompts.prompt_index, images.seed
            """,
            (self._run_context.run_id,),
        ).fetchall()
        return [
            ImageWorkItem(
                item_id=int(row["item_id"]),
                item_index=int(row["item_index"]),
                item=BenchmarkItem(domain=row["domain"], title=row["title"]),
                prompt_id=int(row["prompt_id"]),
                prompt=GeneratedPrompt(
                    index=int(row["prompt_index"]),
                    text=row["text"],
                ),
                image_id=int(row["image_id"]),
                image=ImageArtifact(
                    path=self._run_context.directory / row["path"],
                    seed=int(row["seed"]),
                    raw_response=row["raw_response"],
                    backend_job_id=row["backend_job_id"],
                ),
            )
            for row in rows
        ]

    def get_verification(
        self,
        image_id: int,
    ) -> tuple[int, VerificationResult] | None:
        row = self._connection.execute(
            """
            SELECT verification_id, passed, reason, raw_response
            FROM verifications
            WHERE image_id = ?
            """,
            (image_id,),
        ).fetchone()
        if row is None:
            return None
        return (
            int(row["verification_id"]),
            VerificationResult(
                passed=bool(row["passed"]),
                reason=row["reason"],
                raw_response=row["raw_response"],
            ),
        )

    def add_verification(
        self,
        image_id: int,
        result: VerificationResult,
    ) -> int:
        return self._insert(
            """
            INSERT INTO verifications (image_id, passed, reason, raw_response)
            VALUES (?, ?, ?, ?)
            """,
            (image_id, int(result.passed), result.reason, result.raw_response),
        )

    def get_image_description(
        self,
        image_id: int,
    ) -> tuple[int, ImageDescription] | None:
        row = self._connection.execute(
            """
            SELECT
                description_id,
                text,
                backend_request_id,
                raw_response
            FROM image_descriptions
            WHERE image_id = ?
            """,
            (image_id,),
        ).fetchone()
        if row is None:
            return None
        return (
            int(row["description_id"]),
            ImageDescription(
                text=row["text"],
                backend_request_id=row["backend_request_id"],
                raw_response=row["raw_response"],
            ),
        )

    def add_image_description(
        self,
        image_id: int,
        description: ImageDescription,
    ) -> int:
        return self._insert(
            """
            INSERT INTO image_descriptions (
                image_id,
                text,
                backend_request_id,
                raw_response,
                created_at
            )
            VALUES (?, ?, ?, ?, ?)
            """,
            (
                image_id,
                description.text,
                description.backend_request_id,
                description.raw_response,
                utc_now(),
            ),
        )

    def get_prediction(
        self,
        image_id: int,
    ) -> tuple[int, TitlePrediction] | None:
        row = self._connection.execute(
            """
            SELECT
                prediction_id,
                description_id,
                input_kind,
                title,
                confidence,
                confidence_type,
                raw_response
            FROM predictions
            WHERE image_id = ?
            """,
            (image_id,),
        ).fetchone()
        if row is None:
            return None
        return (
            int(row["prediction_id"]),
            TitlePrediction(
                title=row["title"],
                confidence=row["confidence"],
                confidence_type=row["confidence_type"],
                raw_response=row["raw_response"],
            ),
        )

    def add_prediction(
        self,
        image_id: int,
        prediction: TitlePrediction,
        *,
        input_kind: Literal["image", "description"],
        description_id: int | None = None,
    ) -> int:
        if (input_kind == "description") != (description_id is not None):
            raise ValueError(
                "Description predictions require description_id; "
                "image predictions must not provide one."
            )

        return self._insert(
            """
            INSERT INTO predictions (
                image_id,
                description_id,
                input_kind,
                title,
                confidence,
                confidence_type,
                raw_response
            )
            VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            (
                image_id,
                description_id,
                input_kind,
                prediction.title,
                prediction.confidence,
                prediction.confidence_type,
                prediction.raw_response,
            ),
        )

    def add_evaluation_if_missing(
        self,
        *,
        verification_id: int,
        prediction_id: int,
        exact_match: bool,
        casefold_contains_match: bool,
        included: bool,
        primary_score: bool | None,
        exact_method: str,
        contains_method: str,
    ) -> int:
        row = self._connection.execute(
            """
            SELECT evaluation_id
            FROM evaluations
            WHERE prediction_id = ?
            """,
            (prediction_id,),
        ).fetchone()
        if row is not None:
            return int(row["evaluation_id"])

        stored_score = None if primary_score is None else int(primary_score)
        return self._insert(
            """
            INSERT INTO evaluations (
                verification_id,
                prediction_id,
                exact_match,
                casefold_contains_match,
                included,
                primary_score,
                exact_method,
                contains_method
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                verification_id,
                prediction_id,
                int(exact_match),
                int(casefold_contains_match),
                int(included),
                stored_score,
                exact_method,
                contains_method,
            ),
        )

    def get_evaluation_id(self, prediction_id: int) -> int | None:
        """Return the stored evaluation for one prediction, when present."""
        row = self._connection.execute(
            """
            SELECT evaluation_id
            FROM evaluations
            WHERE prediction_id = ?
            """,
            (prediction_id,),
        ).fetchone()
        return None if row is None else int(row["evaluation_id"])

    def counts(self) -> ResultCounts:
        """Count all successfully stored result rows."""
        row = self._connection.execute(
            """
            SELECT
                (SELECT COUNT(*) FROM dataset_items) AS dataset_items,
                (SELECT COUNT(*) FROM prompts) AS prompts,
                (SELECT COUNT(*) FROM images) AS images,
                (SELECT COUNT(*) FROM verifications) AS verifications,
                (SELECT COUNT(*) FROM image_descriptions) AS image_descriptions,
                (SELECT COUNT(*) FROM predictions) AS predictions,
                (SELECT COUNT(*) FROM evaluations) AS evaluations
            """
        ).fetchone()
        return ResultCounts(
            dataset_items=int(row["dataset_items"]),
            prompts=int(row["prompts"]),
            images=int(row["images"]),
            verifications=int(row["verifications"]),
            image_descriptions=int(row["image_descriptions"]),
            predictions=int(row["predictions"]),
            evaluations=int(row["evaluations"]),
        )
