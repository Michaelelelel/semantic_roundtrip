"""Read-only queries for inspecting persisted pipeline results."""

import sqlite3
from dataclasses import dataclass
from pathlib import Path

from semantic_roundtrip.evaluation import title_exact_match
from semantic_roundtrip.persistence.run.schema import (
    connect_run_database,
    require_run_schema,
)


@dataclass(frozen=True, slots=True)
class PredictionTrace:
    """One route-specific title prediction and its visible exact match."""

    title: str
    confidence: float | None
    confidence_type: str | None
    exact_match: bool | None


@dataclass(frozen=True, slots=True)
class IllustratabilityTrace:
    """One title and its persisted model-estimated illustratability."""

    item_index: int
    item_key: str
    domain: str
    title: str
    score: int


@dataclass(frozen=True, slots=True)
class ResultTrace:
    """One prompt and its available downstream pipeline products."""

    item_index: int
    item_key: str
    domain: str
    expected_title: str
    illustratability_score: int | None
    prompt_id: int
    prompt_index: int
    prompt_sampling_seed: int
    prompt_text: str
    image_id: int | None
    image_seed: int | None
    verification_passed: bool | None
    verification_reason: str | None
    image_description: str | None
    direct_result: PredictionTrace | None
    description_result: PredictionTrace | None


@dataclass(frozen=True, slots=True)
class ResultTracePage:
    """One bounded page of pipeline result traces."""

    traces: tuple[ResultTrace, ...]
    page: int
    page_size: int
    total_traces: int

    @property
    def total_pages(self) -> int:
        return max(1, (self.total_traces + self.page_size - 1) // self.page_size)

    @property
    def has_previous(self) -> bool:
        return self.page > 1

    @property
    def has_next(self) -> bool:
        return self.page < self.total_pages


def _optional_bool(value: object | None) -> bool | None:
    return None if value is None else bool(value)


def _prediction_trace(row: sqlite3.Row, prefix: str) -> PredictionTrace | None:
    if row[f"{prefix}_prediction_id"] is None:
        return None
    confidence = row[f"{prefix}_confidence"]
    title = row[f"{prefix}_title"]
    return PredictionTrace(
        title=title,
        confidence=None if confidence is None else float(confidence),
        confidence_type=row[f"{prefix}_confidence_type"],
        exact_match=title_exact_match(row["expected_title"], title),
    )


def read_result_trace_page(
    database_path: Path,
    *,
    page: int,
    page_size: int,
) -> ResultTracePage:
    """Read one deterministic page of prompt-to-result traces."""
    if page < 1:
        raise ValueError("Result page must be at least 1.")
    if page_size < 1:
        raise ValueError("Result page size must be at least 1.")

    connection = connect_run_database(database_path, read_only=True)
    try:
        require_run_schema(connection)
        total_traces = int(
            connection.execute(
                """
                SELECT COUNT(*)
                FROM prompts
                JOIN dataset_items AS items
                    ON items.item_id = prompts.item_id
                LEFT JOIN images
                    ON images.prompt_id = prompts.prompt_id
                """
            ).fetchone()[0]
        )
        rows = connection.execute(
            """
            SELECT
                items.item_index,
                items.item_key,
                items.domain,
                items.title AS expected_title,
                illustratability_ratings.score AS illustratability_score,
                prompts.prompt_id,
                prompts.prompt_index,
                prompts.sampling_seed AS prompt_sampling_seed,
                prompts.text AS prompt_text,
                images.image_id,
                images.seed AS image_seed,
                verifications.passed AS verification_passed,
                verifications.reason AS verification_reason,
                image_descriptions.text AS image_description,
                direct_predictions.prediction_id AS direct_prediction_id,
                direct_predictions.title AS direct_title,
                direct_predictions.confidence AS direct_confidence,
                direct_predictions.confidence_type AS direct_confidence_type,
                description_predictions.prediction_id
                    AS description_prediction_id,
                description_predictions.title AS description_title,
                description_predictions.confidence AS description_confidence,
                description_predictions.confidence_type
                    AS description_confidence_type
            FROM prompts
            JOIN dataset_items AS items
                ON items.item_id = prompts.item_id
            LEFT JOIN illustratability_ratings
                ON illustratability_ratings.item_id = items.item_id
            LEFT JOIN images
                ON images.prompt_id = prompts.prompt_id
            LEFT JOIN verifications
                ON verifications.image_id = images.image_id
            LEFT JOIN image_descriptions
                ON image_descriptions.image_id = images.image_id
            LEFT JOIN predictions AS direct_predictions
                ON direct_predictions.image_id = images.image_id
                AND direct_predictions.input_kind = 'image'
            LEFT JOIN predictions AS description_predictions
                ON description_predictions.image_id = images.image_id
                AND description_predictions.input_kind = 'description'
            ORDER BY
                items.item_index,
                prompts.prompt_index,
                images.seed,
                images.image_id
            LIMIT ? OFFSET ?
            """,
            (page_size, (page - 1) * page_size),
        ).fetchall()
    finally:
        connection.close()

    traces = tuple(
        ResultTrace(
            item_index=int(row["item_index"]),
            item_key=row["item_key"],
            domain=row["domain"],
            expected_title=row["expected_title"],
            illustratability_score=(
                None
                if row["illustratability_score"] is None
                else int(row["illustratability_score"])
            ),
            prompt_id=int(row["prompt_id"]),
            prompt_index=int(row["prompt_index"]),
            prompt_sampling_seed=int(row["prompt_sampling_seed"]),
            prompt_text=row["prompt_text"],
            image_id=None if row["image_id"] is None else int(row["image_id"]),
            image_seed=(None if row["image_seed"] is None else int(row["image_seed"])),
            verification_passed=_optional_bool(row["verification_passed"]),
            verification_reason=row["verification_reason"],
            image_description=row["image_description"],
            direct_result=_prediction_trace(row, "direct"),
            description_result=_prediction_trace(row, "description"),
        )
        for row in rows
    )
    return ResultTracePage(
        traces=traces,
        page=page,
        page_size=page_size,
        total_traces=total_traces,
    )


def read_illustratability_ratings(
    database_path: Path,
) -> tuple[IllustratabilityTrace, ...]:
    """Read all successful title ratings in deterministic dataset order."""
    connection = connect_run_database(database_path, read_only=True)
    try:
        require_run_schema(connection)
        rows = connection.execute(
            """
            SELECT
                items.item_index,
                items.item_key,
                items.domain,
                items.title,
                ratings.score
            FROM illustratability_ratings AS ratings
            JOIN dataset_items AS items ON items.item_id = ratings.item_id
            ORDER BY items.item_index
            """
        ).fetchall()
    finally:
        connection.close()
    return tuple(
        IllustratabilityTrace(
            item_index=int(row["item_index"]),
            item_key=row["item_key"],
            domain=row["domain"],
            title=row["title"],
            score=int(row["score"]),
        )
        for row in rows
    )


def read_image_artifact_path(database_path: Path, image_id: int) -> Path | None:
    """Read the stored run-relative path for one generated image."""
    connection = connect_run_database(database_path, read_only=True)
    try:
        require_run_schema(connection)
        row = connection.execute(
            "SELECT path FROM images WHERE image_id = ?",
            (image_id,),
        ).fetchone()
    finally:
        connection.close()

    return None if row is None else Path(row["path"])
