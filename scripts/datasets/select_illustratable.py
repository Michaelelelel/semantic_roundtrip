"""Select the direct illustratability supplement from a completed rating job."""

from __future__ import annotations

import csv
import sqlite3
from argparse import ArgumentParser, Namespace
from dataclasses import dataclass
from pathlib import Path

import yaml

DOMAINS = ("songs", "movies", "bands")
MODELS = ("q25", "g3", "q38", "g4")
ENTRY_MODELS = {f"rating_{model}": model for model in MODELS}
DEFAULT_CANDIDATES = Path("configs/datasets/eligible_top300_v1_sources.csv")
DEFAULT_FINAL_OUTPUT = Path("configs/datasets/illustratable_titles_v1.yaml")
DEFAULT_FINAL_REPORT = Path("configs/datasets/illustratable_titles_v1_sources.csv")
DEFAULT_DEVELOPMENT_OUTPUT = Path(
    "configs/datasets/development_illustratable_titles_v1.yaml"
)
DEFAULT_DEVELOPMENT_REPORT = Path(
    "configs/datasets/development_illustratable_titles_v1_sources.csv"
)


@dataclass(frozen=True, slots=True)
class RatedCandidate:
    identifier: str
    domain: str
    title: str
    source_rank: int
    source_id: str
    selection_group: str
    source_row: dict[str, str]
    scores: dict[str, int]

    @property
    def consensus_score(self) -> float:
        return sum(self.scores.values()) / len(MODELS)


def parse_arguments() -> Namespace:
    parser = ArgumentParser(
        description=(
            "Create the high-illustratability final and development datasets "
            "from one completed four-model candidate-rating job."
        )
    )
    parser.add_argument("--job", type=Path, required=True)
    parser.add_argument("--candidates", type=Path, default=DEFAULT_CANDIDATES)
    parser.add_argument("--final-output", type=Path, default=DEFAULT_FINAL_OUTPUT)
    parser.add_argument("--final-report", type=Path, default=DEFAULT_FINAL_REPORT)
    parser.add_argument(
        "--development-output",
        type=Path,
        default=DEFAULT_DEVELOPMENT_OUTPUT,
    )
    parser.add_argument(
        "--development-report",
        type=Path,
        default=DEFAULT_DEVELOPMENT_REPORT,
    )
    return parser.parse_args()


def _read_yaml(path: Path) -> object:
    with path.open(encoding="utf-8") as file:
        return yaml.safe_load(file)


def load_candidate_rows(path: Path) -> dict[str, dict[str, str]]:
    with path.open(encoding="utf-8", newline="") as file:
        rows = list(csv.DictReader(file))
    candidates = {row["id"]: row for row in rows}
    if len(candidates) != len(rows):
        raise ValueError("Candidate report contains duplicate IDs.")
    counts = {
        domain: sum(row["domain"] == domain for row in rows) for domain in DOMAINS
    }
    if counts != dict.fromkeys(DOMAINS, 300):
        raise ValueError(f"Expected 300 candidates per domain, got {counts}.")
    return candidates


def _read_job_runs(job_directory: Path) -> dict[str, Path]:
    snapshot = _read_yaml(job_directory / "job_snapshot.yaml")
    if not isinstance(snapshot, dict) or not isinstance(snapshot.get("entries"), list):
        raise TypeError("Rating job snapshot has no entry list.")
    names = {int(entry["index"]): str(entry["name"]) for entry in snapshot["entries"]}
    if set(names.values()) != set(ENTRY_MODELS):
        raise ValueError("Rating job must contain exactly: " + ", ".join(ENTRY_MODELS))

    database_path = job_directory / "job_state.sqlite"
    uri = f"file:{database_path.resolve()}?mode=ro"
    with sqlite3.connect(uri, uri=True) as connection:
        connection.row_factory = sqlite3.Row
        rows = connection.execute(
            "SELECT entry_index, run_directory, status "
            "FROM job_entries ORDER BY entry_index"
        ).fetchall()
    runs: dict[str, Path] = {}
    for row in rows:
        name = names[int(row["entry_index"])]
        if row["status"] != "completed":
            raise ValueError(
                f"Rating entry '{name}' is {row['status']}, not completed."
            )
        runs[name] = job_directory / str(row["run_directory"])
    if set(runs) != set(ENTRY_MODELS):
        raise ValueError("Rating job database and snapshot entries differ.")
    return runs


def load_ratings(job_directory: Path) -> dict[str, dict[str, int]]:
    """Return candidate ID -> model ID -> score from four completed runs."""
    ratings: dict[str, dict[str, int]] = {}
    for entry_name, run_directory in _read_job_runs(job_directory).items():
        model = ENTRY_MODELS[entry_name]
        database_path = run_directory / "pipeline_state.sqlite"
        uri = f"file:{database_path.resolve()}?mode=ro"
        with sqlite3.connect(uri, uri=True) as connection:
            connection.row_factory = sqlite3.Row
            rows = connection.execute(
                """
                SELECT items.item_key, ratings.score
                FROM dataset_items AS items
                LEFT JOIN illustratability_ratings AS ratings
                    ON ratings.item_id = items.item_id
                ORDER BY items.item_index
                """
            ).fetchall()
        for row in rows:
            if row["score"] is not None:
                ratings.setdefault(str(row["item_key"]), {})[model] = int(row["score"])
    return ratings


def rated_candidates(
    candidate_rows: dict[str, dict[str, str]],
    ratings: dict[str, dict[str, int]],
) -> list[RatedCandidate]:
    complete = []
    for identifier, row in candidate_rows.items():
        scores = ratings.get(identifier, {})
        if set(scores) != set(MODELS):
            continue
        complete.append(
            RatedCandidate(
                identifier=identifier,
                domain=row["domain"],
                title=row["title"],
                source_rank=int(row["source_rank"]),
                source_id=row["source_id"],
                selection_group=row["selection_group"],
                source_row=row,
                scores=scores,
            )
        )
    return complete


def select_candidates(
    candidates: list[RatedCandidate],
    *,
    final_count: int = 30,
    development_count: int = 2,
) -> tuple[list[RatedCandidate], list[RatedCandidate]]:
    """Select ranked, non-overlapping final and development title sets."""
    final: list[RatedCandidate] = []
    development: list[RatedCandidate] = []
    required = final_count + development_count
    for domain in DOMAINS:
        ranked = sorted(
            (candidate for candidate in candidates if candidate.domain == domain),
            key=lambda row: (-row.consensus_score, row.source_rank, row.source_id),
        )
        chosen: list[RatedCandidate] = []
        used_groups: set[str] = set()
        for candidate in ranked:
            group = candidate.selection_group if domain == "songs" else ""
            if group and group in used_groups:
                continue
            chosen.append(candidate)
            if group:
                used_groups.add(group)
            if len(chosen) == required:
                break
        if len(chosen) != required:
            raise ValueError(
                f"Only {len(chosen)} fully rated/selectable {domain} candidates "
                f"were found; {required} are required."
            )
        final.extend(chosen[:final_count])
        development.extend(chosen[final_count:])
    return final, development


def _atomic_text(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(f"{path.suffix}.part")
    temporary.write_text(text, encoding="utf-8")
    temporary.replace(path)


def write_dataset(path: Path, dataset_id: str, rows: list[RatedCandidate]) -> None:
    profile = {
        "schema_version": 1,
        "dataset_id": dataset_id,
        "items": [
            {"id": row.identifier, "domain": row.domain, "title": row.title}
            for row in rows
        ],
    }
    _atomic_text(
        path,
        "# Generated by scripts/datasets/select_illustratable.py.\n"
        + yaml.safe_dump(profile, sort_keys=False, allow_unicode=True),
    )


def write_report(path: Path, rows: list[RatedCandidate], split: str) -> None:
    base_fields = list(rows[0].source_row)
    fieldnames = [
        *base_fields,
        *(f"{model}_score" for model in MODELS),
        "consensus_score",
        "selection_split",
    ]
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(f"{path.suffix}.part")
    with temporary.open("w", encoding="utf-8", newline="") as file:
        writer = csv.DictWriter(file, fieldnames=fieldnames, lineterminator="\n")
        writer.writeheader()
        for row in rows:
            writer.writerow(
                {
                    **row.source_row,
                    **{f"{model}_score": row.scores[model] for model in MODELS},
                    "consensus_score": f"{row.consensus_score:.2f}",
                    "selection_split": split,
                }
            )
    temporary.replace(path)


def main() -> None:
    arguments = parse_arguments()
    job_directory = arguments.job.expanduser().resolve()
    candidates = load_candidate_rows(arguments.candidates)
    ratings = load_ratings(job_directory)
    complete = rated_candidates(candidates, ratings)
    counts = {
        domain: sum(row.domain == domain for row in complete) for domain in DOMAINS
    }
    if any(count < 32 for count in counts.values()):
        raise ValueError(f"Too few complete four-model ratings: {counts}.")
    final, development = select_candidates(complete)
    write_dataset(arguments.final_output, "illustratable_titles_v1", final)
    write_report(arguments.final_report, final, "final")
    write_dataset(
        arguments.development_output,
        "development_illustratable_titles_v1",
        development,
    )
    write_report(arguments.development_report, development, "development")
    print(f"Complete ratings: {counts}")
    print(f"Final dataset: {arguments.final_output}")
    print(f"Development dataset: {arguments.development_output}")


if __name__ == "__main__":
    main()
