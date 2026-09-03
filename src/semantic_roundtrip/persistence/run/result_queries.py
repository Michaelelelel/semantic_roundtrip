"""Read-only queries for inspecting persisted pipeline results."""

import sqlite3
from collections import defaultdict
from dataclasses import dataclass
from pathlib import Path

from semantic_roundtrip.config import ResolvedAppConfig
from semantic_roundtrip.config_resolution import (
    configured_image_verification_policies,
    configured_stage_names,
    expected_output_count,
)
from semantic_roundtrip.evaluation import (
    PROMPT_TITLE_MATCH_METHOD,
    STRICT_IMAGE_VERIFICATION_METHOD,
    TITLE_AWARE_IMAGE_VERIFICATION_METHOD,
    title_exact_match,
)
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
    """Strict-title accuracy under both image policies."""

    correct: int
    title_aware_correct: int | None
    expected: int
    predictions: int

    @property
    def percent(self) -> float:
        return 100 * self.correct / self.expected

    @property
    def title_aware_percent(self) -> float | None:
        if self.title_aware_correct is None:
            return None
        return 100 * self.title_aware_correct / self.expected


@dataclass(frozen=True, slots=True)
class VerificationCheckSummary:
    """Persisted decisions for one verification policy."""

    key: str
    label: str
    expected: int
    decided: int
    passed: int
    method: str

    @property
    def unavailable(self) -> int:
        return self.expected - self.decided

    @property
    def rejected(self) -> int:
        return self.decided - self.passed


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
    prompt_verification_configured: bool
    prompt_verification_passed: bool | None
    prompt_verification_reason: str | None
    image_id: int | None
    image_seed: int | None
    strict_image_verification_configured: bool
    strict_image_verification_passed: bool | None
    strict_image_verification_reason: str | None
    title_aware_image_verification_configured: bool
    title_aware_image_verification_passed: bool | None
    title_aware_image_verification_reason: str | None
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


def _configured_verification_checks(
    connection: sqlite3.Connection,
    config: ResolvedAppConfig,
) -> tuple[bool, frozenset[str]]:
    """Read local configuration and persisted tasks for inherited checks."""
    verification = config.stages.verification
    prompt = verification is not None and verification.prompt is not None
    image = set(configured_image_verification_policies(config))
    for row in connection.execute(
        "SELECT task_key FROM stage_tasks WHERE stage = 'verification'"
    ):
        task_key = str(row["task_key"])
        prompt |= task_key.startswith(
            "verification:prompt:reference_title_absent:"
        )
        for policy in ("strict", "title_aware"):
            if task_key.startswith(f"verification:image:{policy}:"):
                image.add(policy)
    return prompt, frozenset(image)


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
        prompt_verification_configured, image_policies = (
            _configured_verification_checks(connection, config)
        )
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
        verification_columns = """
            prompt_verifications.passed AS prompt_verification_passed,
            prompt_verifications.reason AS prompt_verification_reason,
            strict_verifications.passed
                AS strict_image_verification_passed,
            strict_verifications.reason
                AS strict_image_verification_reason,
            title_aware_verifications.passed
                AS title_aware_image_verification_passed,
            title_aware_verifications.reason
                AS title_aware_image_verification_reason,
        """
        verification_joins = """
            LEFT JOIN prompt_verifications
                ON prompt_verifications.prompt_id = prompts.prompt_id
                AND prompt_verifications.policy = 'reference_title_absent'
            LEFT JOIN image_verifications AS strict_verifications
                ON strict_verifications.image_id = images.image_id
                AND strict_verifications.policy = 'strict'
            LEFT JOIN image_verifications AS title_aware_verifications
                ON title_aware_verifications.image_id = images.image_id
                AND title_aware_verifications.policy = 'title_aware'
        """
        rows = connection.execute(
            dataset_sql
            + f"""
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
                {verification_columns}
                images.image_id,
                images.seed AS image_seed,
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
            {verification_joins}
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
            prompt_verification_configured=prompt_verification_configured,
            prompt_verification_passed=_optional_bool(
                row["prompt_verification_passed"]
            ),
            prompt_verification_reason=row["prompt_verification_reason"],
            image_id=None if row["image_id"] is None else int(row["image_id"]),
            image_seed=(None if row["image_seed"] is None else int(row["image_seed"])),
            strict_image_verification_configured="strict" in image_policies,
            strict_image_verification_passed=_optional_bool(
                row["strict_image_verification_passed"]
            ),
            strict_image_verification_reason=row["strict_image_verification_reason"],
            title_aware_image_verification_configured=(
                "title_aware" in image_policies
            ),
            title_aware_image_verification_passed=_optional_bool(
                row["title_aware_image_verification_passed"]
            ),
            title_aware_image_verification_reason=row[
                "title_aware_image_verification_reason"
            ],
            image_description=row["image_description"],
            direct_result=_prediction_trace(row, "direct"),
            description_result=_prediction_trace(row, "description"),
            terminal_stages=_terminal_stages(
                row,
                tasks_by_item[row["item_id"]],
                config,
                prompt_verification_configured=prompt_verification_configured,
                image_policies=image_policies,
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
    *,
    prompt_verification_configured: bool,
    image_policies: frozenset[str],
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
        elif stage == "verification":
            if row["prompt_id"] is not None and task["prompt_id"] != row["prompt_id"]:
                continue
            if row["image_id"] is not None and task["image_id"] not in {
                None,
                row["image_id"],
            }:
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
    expected = {
        "illustratability_rating": 1,
        "prompt_generation": prompts,
        "verification": (
            (prompts if prompt_verification_configured else 0)
            + len(image_policies) * images
        ),
    }
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
        prompt_configured, image_policies = _configured_verification_checks(
            connection, config
        )
        verification_columns = """
            strict_verifications.passed AS strict_passed,
            prompt_verifications.passed AS prompt_passed,
            title_aware_verifications.passed AS title_aware_passed
        """
        verification_joins = """
            LEFT JOIN prompt_verifications
                ON prompt_verifications.prompt_id = prompts.prompt_id
                AND prompt_verifications.policy = 'reference_title_absent'
            LEFT JOIN image_verifications AS strict_verifications
                ON strict_verifications.image_id = images.image_id
                AND strict_verifications.policy = 'strict'
            LEFT JOIN image_verifications AS title_aware_verifications
                ON title_aware_verifications.image_id = images.image_id
                AND title_aware_verifications.policy = 'title_aware'
        """
        rows = connection.execute(
            f"""
            SELECT
                predictions.input_kind,
                predictions.title AS predicted_title,
                items.title AS expected_title,
                {verification_columns}
            FROM predictions
            JOIN images USING (image_id)
            JOIN prompts ON prompts.prompt_id = images.prompt_id
            JOIN dataset_items AS items USING (item_id)
            {verification_joins}
            """
        ).fetchall()
    finally:
        connection.close()
    return {
        kind: RouteAccuracy(
            correct=sum(
                ("strict" not in image_policies or row["strict_passed"] == 1)
                and (not prompt_configured or row["prompt_passed"] == 1)
                and title_exact_match(row["expected_title"], row["predicted_title"])
                for row in rows
                if row["input_kind"] == kind
            ),
            title_aware_correct=(
                None
                if "title_aware" not in image_policies
                else sum(
                    row["title_aware_passed"] == 1
                    and (not prompt_configured or row["prompt_passed"] == 1)
                    and title_exact_match(row["expected_title"], row["predicted_title"])
                    for row in rows
                    if row["input_kind"] == kind
                )
            ),
            expected=expected_output_count(config, stage),
            predictions=sum(row["input_kind"] == kind for row in rows),
        )
        for kind, stage in routes.items()
    }


def read_verification_summary(
    database_path: Path,
    config: ResolvedAppConfig,
) -> tuple[VerificationCheckSummary, ...]:
    """Summarize persisted decisions without recomputing historical runs."""
    connection = connect_run_database(database_path, read_only=True)
    try:
        require_run_schema(connection)
        prompt_configured, image_policies = _configured_verification_checks(
            connection, config
        )
        prompt_row = connection.execute(
            """
            SELECT
                COUNT(*) AS decided,
                COALESCE(SUM(passed), 0) AS passed,
                GROUP_CONCAT(DISTINCT method) AS methods
            FROM prompt_verifications
            WHERE policy = 'reference_title_absent'
            """
        ).fetchone()
        image_rows = {
            row["policy"]: row
            for row in connection.execute(
                """
                SELECT
                    policy,
                    COUNT(*) AS decided,
                    COALESCE(SUM(passed), 0) AS passed,
                    GROUP_CONCAT(DISTINCT method) AS methods
                FROM image_verifications
                GROUP BY policy
                """
            )
        }
        expected_prompts = len(config.dataset.items) * len(
            config.experiment.prompt_seeds
        )
        expected_images = expected_prompts * len(config.experiment.image_seeds)
        checks: list[VerificationCheckSummary] = []
        if prompt_configured:
            checks.append(
                VerificationCheckSummary(
                    key="prompt",
                    label="Prompt title-absence check",
                    expected=expected_prompts,
                    decided=int(prompt_row["decided"]),
                    passed=int(prompt_row["passed"]),
                    method=prompt_row["methods"] or PROMPT_TITLE_MATCH_METHOD,
                )
            )
        if "strict" in image_policies:
            row = image_rows.get("strict")
            checks.append(
                VerificationCheckSummary(
                    key="strict_image",
                    label="Strict image text check",
                    expected=expected_images,
                    decided=0 if row is None else int(row["decided"]),
                    passed=0 if row is None else int(row["passed"]),
                    method=(None if row is None else row["methods"])
                    or STRICT_IMAGE_VERIFICATION_METHOD,
                )
            )
        if "title_aware" in image_policies:
            row = image_rows.get("title_aware")
            checks.append(
                VerificationCheckSummary(
                    key="title_aware_image",
                    label="Title-aware image text check",
                    expected=expected_images,
                    decided=0 if row is None else int(row["decided"]),
                    passed=0 if row is None else int(row["passed"]),
                    method=(None if row is None else row["methods"])
                    or TITLE_AWARE_IMAGE_VERIFICATION_METHOD,
                )
            )
    finally:
        connection.close()
    return tuple(checks)


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
