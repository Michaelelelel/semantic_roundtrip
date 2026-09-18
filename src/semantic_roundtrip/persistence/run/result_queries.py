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
from semantic_roundtrip.inheritance.source import resolve_stage_provenance
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
    """Full-denominator Strict Exact Match, with separate image-policy results."""

    correct: int
    title_aware_correct: int | None
    expected: int
    predictions: int
    prompt_verification_configured: bool = False
    image_verification_configured: bool = False

    @property
    def percent(self) -> float | None:
        return None if self.expected == 0 else 100 * self.correct / self.expected

    @property
    def title_aware_percent(self) -> float | None:
        if self.title_aware_correct is None or self.expected == 0:
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
    """A title/prompt slot, optionally expanded into its existing images."""

    item_index: int
    item_key: str
    domain: str
    expected_title: str
    illustratability_score: int | None
    prompt_id: int | None
    prompt_index: int | None
    prompt_sampling_seed: int | None
    prompt_text: str | None
    prompt_origin_run_id: str | None
    prompt_origin_id: int | None
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
    prompt_result: PredictionTrace | None
    prompt_prediction_origin_run_id: str | None
    prompt_prediction_origin_id: int | None
    prompt_task_statuses: dict[str, str]
    prompt_task_errors: dict[str, str]
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
    run_directory: Path,
) -> tuple[bool, frozenset[str]]:
    """Read local configuration and persisted tasks for inherited checks."""
    prompt = config.stages.verification_prompt is not None
    if config.inherit is not None:
        prompt |= "verification_prompt" in dependency_closure(config.inherit.stages)
    image = set(configured_image_verification_policies(config))
    if config.inherit is not None and "verification_image" in dependency_closure(
        config.inherit.stages
    ):
        source = resolve_stage_provenance(config, run_directory, "verification_image")
        if source is None:
            raise ValueError("Inherited image verification has no defining snapshot.")
        image.update(configured_image_verification_policies(source[0]))
    for row in connection.execute(
        "SELECT stage, task_key FROM stage_tasks "
        "WHERE stage IN ('verification_prompt', 'verification_image')"
    ):
        task_key = str(row["task_key"])
        prompt |= row["stage"] == "verification_prompt"
        for policy in ("strict", "title_aware"):
            if task_key.startswith(f"verification_image:{policy}:"):
                image.add(policy)
    return prompt, frozenset(image)


def read_result_trace_page(
    database_path: Path,
    config: ResolvedAppConfig,
    *,
    page: int,
    page_size: int,
) -> ResultTracePage:
    """Include planned prompt slots when enabled, and existing image products."""
    if page < 1:
        raise ValueError("Result page must be at least 1.")
    if page_size < 1:
        raise ValueError("Result page size must be at least 1.")

    stages = set(configured_stage_names(config))
    if config.inherit is not None:
        stages.update(dependency_closure(config.inherit.stages))
    prompt_route_configured = "title_guessing_from_prompt" in stages
    if not config.dataset.items or (
        prompt_route_configured and not config.experiment.prompt_seeds
    ):
        return ResultTracePage((), page, page_size, 0)

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
    prompt_join = "LEFT JOIN prompts ON prompts.item_id = items.item_id"
    prompt_index_column = "prompts.prompt_index"
    prompt_seed_column = "prompts.sampling_seed"
    if prompt_route_configured:
        # Keep missing seeds distinct without constructing item x seed VALUES
        # in Python. Existing images expand a slot, not its prompt prediction.
        seed_placeholders = ", ".join("(?, ?)" for _ in config.experiment.prompt_seeds)
        dataset_sql += f"""
            , planned_prompts(prompt_index, sampling_seed) AS (
                VALUES {seed_placeholders}
            )
        """
        dataset_parameters += tuple(
            value
            for index, seed in enumerate(config.experiment.prompt_seeds)
            for value in (index, seed)
        )
        prompt_join = """
            CROSS JOIN planned_prompts
            LEFT JOIN prompts ON prompts.item_id = items.item_id
                AND prompts.prompt_index = planned_prompts.prompt_index
        """
        prompt_index_column = "planned_prompts.prompt_index"
        prompt_seed_column = (
            "COALESCE(prompts.sampling_seed, planned_prompts.sampling_seed)"
        )
    connection = connect_run_database(database_path, read_only=True)
    try:
        require_run_schema(connection)
        prompt_verification_configured, image_policies = (
            _configured_verification_checks(connection, config, database_path.parent)
        )
        total_traces = int(
            connection.execute(
                dataset_sql
                + f"""
                SELECT COUNT(*)
                FROM items
                {prompt_join}
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
                {prompt_index_column} AS prompt_index,
                {prompt_seed_column} AS prompt_sampling_seed,
                prompts.text AS prompt_text,
                COALESCE(prompts.origin_run_id, run_metadata.run_id)
                    AS prompt_origin_run_id,
                COALESCE(prompts.origin_prompt_id, prompts.prompt_id)
                    AS prompt_origin_id,
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
                    AS description_confidence_type,
                prompt_predictions.prompt_prediction_id,
                prompt_predictions.title AS prompt_title,
                prompt_predictions.confidence AS prompt_confidence,
                prompt_predictions.confidence_type AS prompt_confidence_type,
                COALESCE(prompt_predictions.origin_run_id, run_metadata.run_id)
                    AS prompt_prediction_origin_run_id,
                COALESCE(prompt_predictions.origin_prompt_prediction_id,
                         prompt_predictions.prompt_prediction_id)
                    AS prompt_prediction_origin_id
            FROM items
            CROSS JOIN run_metadata
            {prompt_join}
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
            LEFT JOIN prompt_predictions
                ON prompt_predictions.prompt_id = prompts.prompt_id
            ORDER BY
                items.item_index,
                {prompt_index_column},
                images.seed,
                images.image_id
            LIMIT ? OFFSET ?
            """,
            (*dataset_parameters, page_size, (page - 1) * page_size),
        ).fetchall()
        tasks_by_item = defaultdict(list)
        task_errors = {}
        item_ids = tuple(
            dict.fromkeys(row["item_id"] for row in rows if row["item_id"] is not None)
        )
        if item_ids:
            item_placeholders = ", ".join("?" for _ in item_ids)
            for task in connection.execute(
                f"""
                SELECT task_id, stage, status, item_id, prompt_id, image_id, seed
                FROM stage_tasks WHERE item_id IN ({item_placeholders})
                """,
                item_ids,
            ):
                tasks_by_item[task["item_id"]].append(task)
            # Only prompt-route terminal errors for this page are needed. The
            # ordered rows keep the latest failed attempt for each task.
            for error in connection.execute(
                f"""
                SELECT errors.task_id, errors.error_type || ': ' || errors.message
                    AS error
                FROM stage_errors AS errors
                JOIN stage_tasks AS tasks USING (task_id)
                WHERE tasks.item_id IN ({item_placeholders})
                    AND tasks.status = 'failed'
                    AND tasks.stage IN ('prompt_generation', 'verification_prompt',
                                        'title_guessing_from_prompt')
                ORDER BY errors.error_id
                """,
                item_ids,
            ):
                task_errors[error["task_id"]] = error["error"]
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
            prompt_origin_run_id=(
                row["prompt_origin_run_id"] if row["prompt_id"] is not None else None
            ),
            prompt_origin_id=row["prompt_origin_id"],
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
            title_aware_image_verification_configured=("title_aware" in image_policies),
            title_aware_image_verification_passed=_optional_bool(
                row["title_aware_image_verification_passed"]
            ),
            title_aware_image_verification_reason=row[
                "title_aware_image_verification_reason"
            ],
            image_description=row["image_description"],
            direct_result=_prediction_trace(row, "direct"),
            description_result=_prediction_trace(row, "description"),
            prompt_result=_prediction_trace(row, "prompt"),
            prompt_prediction_origin_run_id=(
                row["prompt_prediction_origin_run_id"]
                if row["prompt_prediction_id"] is not None
                else None
            ),
            prompt_prediction_origin_id=row["prompt_prediction_origin_id"],
            prompt_task_statuses={
                task["stage"]: task["status"]
                for task in _prompt_tasks(row, tasks_by_item[row["item_id"]])
            },
            prompt_task_errors={
                task["stage"]: task_errors[task["task_id"]]
                for task in _prompt_tasks(row, tasks_by_item[row["item_id"]])
                if task["task_id"] in task_errors
            },
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


def _prompt_tasks(row: sqlite3.Row, tasks: list[sqlite3.Row]) -> list[sqlite3.Row]:
    """Match this prompt's own tasks, never sibling prompts or image failures."""
    return [
        task
        for task in tasks
        if (
            task["stage"] == "prompt_generation"
            and task["seed"] == row["prompt_sampling_seed"]
        )
        or (
            task["stage"] in {"verification_prompt", "title_guessing_from_prompt"}
            and row["prompt_id"] is not None
            and task["prompt_id"] == row["prompt_id"]
        )
    ]


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
    single_prompt = row["prompt_index"] is not None
    for task in tasks:
        stage = task["stage"]
        if stage == "prompt_generation":
            if single_prompt and task["seed"] != row["prompt_sampling_seed"]:
                continue
        elif stage in {"verification_prompt", "title_guessing_from_prompt"}:
            if single_prompt and (
                row["prompt_id"] is None or task["prompt_id"] != row["prompt_id"]
            ):
                continue
        elif stage == "verification_image":
            if single_prompt and (
                row["prompt_id"] is None or task["prompt_id"] != row["prompt_id"]
            ):
                continue
            if row["image_id"] is not None and task["image_id"] not in {
                None,
                row["image_id"],
            }:
                continue
        elif stage != "illustratability_rating":
            if single_prompt and (
                row["prompt_id"] is None or task["prompt_id"] != row["prompt_id"]
            ):
                continue
            if row["image_id"] is not None and task["seed"] != row["image_seed"]:
                continue
        states[stage].append(task["status"])

    prompts = 1 if single_prompt else len(config.experiment.prompt_seeds)
    images = (
        1
        if row["image_id"] is not None
        else prompts * len(config.experiment.image_seeds)
    )
    expected = {
        "illustratability_rating": 1,
        "prompt_generation": prompts,
        "verification_prompt": prompts if prompt_verification_configured else 0,
        "verification_image": len(image_policies) * images,
        "title_guessing_from_prompt": prompts,
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
    """Summarize three routes without dropping failed or missing observations."""
    stages = set(configured_stage_names(config))
    if config.inherit is not None:
        stages.update(dependency_closure(config.inherit.stages))
    routes = {
        kind: stage
        for kind, stage in (
            ("image", "title_guessing_direct"),
            ("description", "title_guessing_from_description"),
            ("prompt", "title_guessing_from_prompt"),
        )
        if stage in stages
    }
    if not routes:
        return {}

    connection = connect_run_database(database_path, read_only=True)
    try:
        require_run_schema(connection)
        prompt_configured, image_policies = _configured_verification_checks(
            connection, config, database_path.parent
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
        prompt_rows = connection.execute(
            """
            SELECT prompt_predictions.title AS predicted_title,
                items.title AS expected_title,
                prompt_verifications.passed AS prompt_passed
            FROM prompt_predictions
            JOIN prompts USING (prompt_id)
            JOIN dataset_items AS items USING (item_id)
            LEFT JOIN prompt_verifications USING (prompt_id)
            """
        ).fetchall()
    finally:
        connection.close()
    accuracies = {
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
            prompt_verification_configured=prompt_configured,
            image_verification_configured="strict" in image_policies,
        )
        for kind, stage in routes.items()
        if kind != "prompt"
    }
    if "prompt" in routes:
        accuracies["prompt"] = RouteAccuracy(
            correct=sum(
                (not prompt_configured or row["prompt_passed"] == 1)
                and title_exact_match(row["expected_title"], row["predicted_title"])
                for row in prompt_rows
            ),
            title_aware_correct=None,
            expected=expected_output_count(config, routes["prompt"]),
            predictions=len(prompt_rows),
            prompt_verification_configured=prompt_configured,
        )
    return accuracies


def read_verification_summary(
    database_path: Path,
    config: ResolvedAppConfig,
) -> tuple[VerificationCheckSummary, ...]:
    """Summarize persisted decisions without recomputing historical runs."""
    connection = connect_run_database(database_path, read_only=True)
    try:
        require_run_schema(connection)
        prompt_configured, image_policies = _configured_verification_checks(
            connection, config, database_path.parent
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
