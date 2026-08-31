"""Read-only queries for inspecting persisted pipeline results."""

import sqlite3
from collections import defaultdict
from dataclasses import dataclass
from pathlib import Path

from semantic_roundtrip.config import ResolvedAppConfig
from semantic_roundtrip.config_resolution import (
    configured_stage_names,
    expected_output_count,
)
from semantic_roundtrip.evaluation import title_exact_match
from semantic_roundtrip.inheritance.dependencies import dependency_closure
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
class RouteAccuracy:
    """End-to-end Strict Exact Match over the fixed planned denominator."""

    correct: int
    expected: int
    predictions: int

    @property
    def percent(self) -> float:
        return 100 * self.correct / self.expected


@dataclass(frozen=True, slots=True)
class ResultTrace:
    """One title, optionally expanded into its existing prompt/image products."""

    item_index: int
    item_key: str
    domain: str
    expected_title: str
    illustratability_score: int | None
    prompt_id: int | None
    prompt_index: int | None
    prompt_sampling_seed: int | None
    prompt_text: str | None
    image_id: int | None
    image_seed: int | None
    verification_passed: bool | None
    verification_reason: str | None
    image_description: str | None
    direct_result: PredictionTrace | None
    description_result: PredictionTrace | None
    terminal_stages: frozenset[str]


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
    config: ResolvedAppConfig,
    *,
    page: int,
    page_size: int,
) -> ResultTracePage:
    """Include every configured title, even before its first persisted output."""
    if page < 1:
        raise ValueError("Result page must be at least 1.")
    if page_size < 1:
        raise ValueError("Result page size must be at least 1.")

    # Dataset rows are inserted lazily by the runner. Anchor the display in its
    # frozen snapshot, without writing placeholder rows into the run database.
    placeholders = ", ".join("(?, ?, ?, ?)" for _ in config.dataset.items)
    dataset_sql = f"""
        WITH configured_items(item_index, item_key, domain, title) AS (
            VALUES {placeholders}
        ), items AS (
            SELECT configured_items.*, dataset_items.item_id
            FROM configured_items
            LEFT JOIN dataset_items USING (item_index)
        )
    """
    dataset_parameters = tuple(
        value
        for index, item in enumerate(config.dataset.items)
        for value in (index, item.id, item.domain, item.title)
    )
    connection = connect_run_database(database_path, read_only=True)
    try:
        require_run_schema(connection)
        total_traces = int(
            connection.execute(
                dataset_sql
                + """
                SELECT COUNT(*)
                FROM items
                LEFT JOIN prompts ON prompts.item_id = items.item_id
                LEFT JOIN images
                    ON images.prompt_id = prompts.prompt_id
                """,
                dataset_parameters,
            ).fetchone()[0]
        )
        rows = connection.execute(
            dataset_sql
            + """
            SELECT
                items.item_id,
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
            FROM items
            LEFT JOIN prompts ON prompts.item_id = items.item_id
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
            (*dataset_parameters, page_size, (page - 1) * page_size),
        ).fetchall()
        tasks_by_item = defaultdict(list)
        for task in connection.execute(
            "SELECT stage, status, item_id, prompt_id, image_id, seed FROM stage_tasks"
        ):
            tasks_by_item[task["item_id"]].append(task)
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
            prompt_id=row["prompt_id"],
            prompt_index=row["prompt_index"],
            prompt_sampling_seed=row["prompt_sampling_seed"],
            prompt_text=row["prompt_text"],
            image_id=None if row["image_id"] is None else int(row["image_id"]),
            image_seed=(None if row["image_seed"] is None else int(row["image_seed"])),
            verification_passed=_optional_bool(row["verification_passed"]),
            verification_reason=row["verification_reason"],
            image_description=row["image_description"],
            direct_result=_prediction_trace(row, "direct"),
            description_result=_prediction_trace(row, "description"),
            terminal_stages=_terminal_stages(
                row, tasks_by_item[row["item_id"]], config
            ),
        )
        for row in rows
    )
    return ResultTracePage(
        traces=traces,
        page=page,
        page_size=page_size,
        total_traces=total_traces,
    )


def _terminal_stages(
    row: sqlite3.Row,
    tasks: list[sqlite3.Row],
    config: ResolvedAppConfig,
) -> frozenset[str]:
    """Recognize exhausted work, including a collapsed pre-prompt/image trace."""
    states = defaultdict(list)
    for task in tasks:
        stage = task["stage"]
        if stage == "prompt_generation":
            if (
                row["prompt_id"] is not None
                and task["seed"] != row["prompt_sampling_seed"]
            ):
                continue
        elif stage != "illustratability_rating":
            if row["prompt_id"] is not None and task["prompt_id"] != row["prompt_id"]:
                continue
            if row["image_id"] is not None and task["seed"] != row["image_seed"]:
                continue
        states[stage].append(task["status"])

    prompts = 1 if row["prompt_id"] is not None else len(config.experiment.prompt_seeds)
    images = (
        1
        if row["image_id"] is not None
        else prompts * len(config.experiment.image_seeds)
    )
    expected = {"illustratability_rating": 1, "prompt_generation": prompts}
    return frozenset(
        stage
        for stage, statuses in states.items()
        if len(statuses) == expected.get(stage, images)
        and all(status in {"completed", "failed"} for status in statuses)
    )


def read_route_accuracies(
    database_path: Path,
    config: ResolvedAppConfig,
) -> dict[str, RouteAccuracy]:
    """Summarize both routes without dropping failed or missing observations."""
    stages = set(configured_stage_names(config))
    if config.inherit is not None:
        stages.update(dependency_closure(config.inherit.stages))
    routes = {
        kind: stage
        for kind, stage in (
            ("image", "title_guessing_direct"),
            ("description", "title_guessing_from_description"),
        )
        if stage in stages
    }
    if not routes:
        return {}

    connection = connect_run_database(database_path, read_only=True)
    try:
        require_run_schema(connection)
        rows = connection.execute(
            """
            SELECT
                predictions.input_kind,
                predictions.title AS predicted_title,
                items.title AS expected_title,
                verifications.passed
            FROM predictions
            JOIN images USING (image_id)
            JOIN prompts USING (prompt_id)
            JOIN dataset_items AS items USING (item_id)
            LEFT JOIN verifications USING (image_id)
            """
        ).fetchall()
    finally:
        connection.close()
    return {
        kind: RouteAccuracy(
            correct=sum(
                row["passed"] == 1
                and title_exact_match(row["expected_title"], row["predicted_title"])
                for row in rows
                if row["input_kind"] == kind
            ),
            expected=expected_output_count(config, stage),
            predictions=sum(row["input_kind"] == kind for row in rows),
        )
        for kind, stage in routes.items()
    }


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
