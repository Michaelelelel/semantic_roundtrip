"""Build the thesis title dataset from frozen IMDb and ListenBrainz files."""

import csv
import gzip
import json
import random
import re
import time
import unicodedata
from argparse import ArgumentParser, Namespace
from collections.abc import Iterator
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import requests
import yaml

DOMAINS = ("songs", "movies", "bands")
DEFAULT_SOURCE_DIRECTORY = Path("data/title_sources/v1")
DEFAULT_OUTPUT = Path("configs/datasets/final_titles_v1.yaml")
DEFAULT_REPORT = Path("configs/datasets/final_titles_v1_sources.csv")
DEFAULT_CANDIDATE_OUTPUT = Path("configs/datasets/eligible_top300_v1.yaml")
DEFAULT_CANDIDATE_REPORT = Path("configs/datasets/eligible_top300_v1_sources.csv")
DEFAULT_EXCLUSIONS = Path("configs/datasets/development_titles_v1.yaml")
LISTENBRAINZ_METADATA_URL = "https://api.listenbrainz.org/1/metadata"
VERSION_LABEL = re.compile(
    r"(?:[\(\[][^\)\]]*?|\s[-–—]\s.*?)\b"
    r"(live|remaster(?:ed)?|remix|edit|mix|acoustic|demo|instrumental|mono|stereo)\b",
    re.IGNORECASE,
)


@dataclass(frozen=True, slots=True)
class Candidate:
    domain: str
    title: str
    source: str
    source_rank: int
    source_id: str
    source_url: str
    year: int
    popularity: int
    artist: str = ""
    selection_group: str = ""


def parse_arguments() -> Namespace:
    parser = ArgumentParser(
        description=(
            "Create a reproducible random title dataset from the downloaded "
            "source snapshot."
        )
    )
    parser.add_argument(
        "--source-directory",
        type=Path,
        default=DEFAULT_SOURCE_DIRECTORY,
    )
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument("--report", type=Path, default=DEFAULT_REPORT)
    parser.add_argument(
        "--candidate-output",
        type=Path,
        default=DEFAULT_CANDIDATE_OUTPUT,
    )
    parser.add_argument(
        "--candidate-report",
        type=Path,
        default=DEFAULT_CANDIDATE_REPORT,
    )
    parser.add_argument("--exclusions", type=Path, default=DEFAULT_EXCLUSIONS)
    parser.add_argument("--dataset-id", default="final_titles_v1")
    parser.add_argument("--titles-per-domain", type=int, default=30)
    parser.add_argument("--candidate-pool-size", type=int, default=300)
    parser.add_argument("--cutoff-year", type=int, default=2018)
    parser.add_argument("--seed", type=int, default=20260811)
    parser.add_argument(
        "--fetch-metadata",
        action="store_true",
        help="Download the two small ListenBrainz metadata snapshots and exit.",
    )
    return parser.parse_args()


def read_json(path: Path) -> Any:
    with path.open(encoding="utf-8") as file:
        return json.load(file)


def write_json(path: Path, value: Any) -> None:
    temporary_path = path.with_suffix(f"{path.suffix}.part")
    temporary_path.write_text(
        json.dumps(value, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    temporary_path.replace(path)


def chunks(values: list[str], size: int) -> Iterator[list[str]]:
    for start in range(0, len(values), size):
        yield values[start : start + size]


def request_json(
    session: requests.Session,
    method: str,
    url: str,
    **kwargs: Any,
) -> Any:
    for attempt in range(1, 4):
        try:
            response = session.request(method, url, timeout=180, **kwargs)
            response.raise_for_status()
            return response.json()
        except requests.RequestException, ValueError:
            if attempt == 3:
                raise
            time.sleep(attempt * 3)
    raise RuntimeError("Metadata request retry loop ended unexpectedly.")


def fetch_listenbrainz_metadata(source_directory: Path) -> None:
    """Freeze release years and artist types for the downloaded top lists."""
    recordings = read_json(source_directory / "listenbrainz_recordings.json")[
        "payload"
    ]["recordings"]
    artists = read_json(source_directory / "listenbrainz_artists.json")["payload"][
        "artists"
    ]

    recording_ids = list(
        dict.fromkeys(
            row["recording_mbid"] for row in recordings if row.get("recording_mbid")
        )
    )
    artist_ids = list(
        dict.fromkeys(row["artist_mbid"] for row in artists if row.get("artist_mbid"))
    )

    session = requests.Session()
    session.headers["User-Agent"] = (
        "semantic-roundtrip-thesis/1.0 "
        "(https://github.com/Michaelelelel/semantic_roundtrip)"
    )

    recording_metadata: dict[str, Any] = {}
    recording_batches = list(chunks(recording_ids, 100))
    for index, batch in enumerate(recording_batches, start=1):
        payload = request_json(
            session,
            "POST",
            f"{LISTENBRAINZ_METADATA_URL}/recording/",
            json={"recording_mbids": batch, "inc": "artist release"},
        )
        if not isinstance(payload, dict):
            raise TypeError("Unexpected ListenBrainz recording metadata response.")
        recording_metadata.update(payload)
        print(f"Recording metadata: {index}/{len(recording_batches)}")

    artist_metadata: list[dict[str, Any]] = []
    artist_batches = list(chunks(artist_ids, 50))
    for index, batch in enumerate(artist_batches, start=1):
        payload = request_json(
            session,
            "GET",
            f"{LISTENBRAINZ_METADATA_URL}/artist/",
            params={"artist_mbids": ",".join(batch), "inc": "artist"},
        )
        if not isinstance(payload, list):
            raise TypeError("Unexpected ListenBrainz artist metadata response.")
        artist_metadata.extend(payload)
        print(f"Artist metadata: {index}/{len(artist_batches)}")

    write_json(
        source_directory / "listenbrainz_recording_metadata.json",
        recording_metadata,
    )
    write_json(
        source_directory / "listenbrainz_artist_metadata.json",
        artist_metadata,
    )


def normalized_title(title: str) -> str:
    return " ".join(unicodedata.normalize("NFC", title).split()).casefold()


def uses_latin_script(title: str) -> bool:
    return all(
        not character.isalpha() or "LATIN" in unicodedata.name(character, "")
        for character in title
    )


def length_group(title: str) -> str:
    word_count = len(title.split())
    if word_count == 1:
        return "short"
    if word_count <= 3:
        return "medium"
    return "long"


def year_from(value: Any) -> int | None:
    match = re.match(r"^(\d{4})", str(value or ""))
    return int(match.group(1)) if match else None


def load_exclusions(path: Path) -> set[tuple[str, str]]:
    profile = yaml.safe_load(path.read_text(encoding="utf-8"))
    return {
        (item["domain"], normalized_title(item["title"])) for item in profile["items"]
    }


def build_song_candidates(source_directory: Path) -> list[Candidate]:
    recordings = read_json(source_directory / "listenbrainz_recordings.json")[
        "payload"
    ]["recordings"]
    metadata = read_json(source_directory / "listenbrainz_recording_metadata.json")
    candidates = []

    for source_rank, row in enumerate(recordings, start=1):
        recording_id = row.get("recording_mbid")
        details = metadata.get(recording_id, {})
        year = year_from((details.get("release") or {}).get("year"))
        if not recording_id or year is None:
            continue

        artist_ids = row.get("artist_mbids") or []
        if not artist_ids:
            artist_ids = [
                artist["artist_mbid"]
                for artist in (details.get("artist") or {}).get("artists", [])
                if artist.get("artist_mbid")
            ]
        artist = " ".join(str(row.get("artist_name", "")).split())
        selection_group = (
            artist_ids[0] if artist_ids else f"name:{normalized_title(artist)}"
        )
        candidates.append(
            Candidate(
                domain="songs",
                title=" ".join(str(row.get("track_name", "")).split()),
                source="ListenBrainz all-time recordings / MusicBrainz",
                source_rank=source_rank,
                source_id=recording_id,
                source_url=f"https://musicbrainz.org/recording/{recording_id}",
                year=year,
                popularity=int(row["listen_count"]),
                artist=artist,
                selection_group=selection_group,
            )
        )
    return candidates


def build_band_candidates(source_directory: Path) -> list[Candidate]:
    artists = read_json(source_directory / "listenbrainz_artists.json")["payload"][
        "artists"
    ]
    metadata_rows = read_json(source_directory / "listenbrainz_artist_metadata.json")
    metadata = {row.get("artist_mbid") or row.get("mbid"): row for row in metadata_rows}
    candidates = []

    for source_rank, row in enumerate(artists, start=1):
        artist_id = row.get("artist_mbid")
        details = metadata.get(artist_id, {})
        year = year_from(details.get("begin_year"))
        if not artist_id or details.get("type") != "Group" or year is None:
            continue
        candidates.append(
            Candidate(
                domain="bands",
                title=" ".join(str(details.get("name", "")).split()),
                source="ListenBrainz all-time artists / MusicBrainz",
                source_rank=source_rank,
                source_id=artist_id,
                source_url=f"https://musicbrainz.org/artist/{artist_id}",
                year=year,
                popularity=int(row["listen_count"]),
            )
        )
    return candidates


def build_movie_candidates(source_directory: Path) -> list[Candidate]:
    ratings_path = source_directory / "imdb_title_ratings.tsv.gz"
    with gzip.open(ratings_path, "rt", encoding="utf-8", newline="") as file:
        votes = {
            row["tconst"]: int(row["numVotes"])
            for row in csv.DictReader(file, delimiter="\t")
        }

    movies: list[tuple[int, str, str, int]] = []
    basics_path = source_directory / "imdb_title_basics.tsv.gz"
    with gzip.open(basics_path, "rt", encoding="utf-8", newline="") as file:
        for row in csv.DictReader(file, delimiter="\t"):
            year = year_from(row["startYear"])
            popularity = votes.get(row["tconst"])
            if (
                row["titleType"] == "movie"
                and row["isAdult"] == "0"
                and year is not None
                and popularity is not None
            ):
                movies.append((popularity, row["tconst"], row["primaryTitle"], year))

    movies.sort(key=lambda row: (-row[0], row[1]))
    return [
        Candidate(
            domain="movies",
            title=title,
            source="IMDb non-commercial datasets",
            source_rank=source_rank,
            source_id=title_id,
            source_url=f"https://www.imdb.com/title/{title_id}/",
            year=year,
            popularity=popularity,
        )
        for source_rank, (popularity, title_id, title, year) in enumerate(
            movies,
            start=1,
        )
    ]


def eligible_candidate_pool(
    candidates: list[Candidate],
    *,
    domain: str,
    exclusions: set[tuple[str, str]],
    cutoff_year: int,
    size: int,
) -> list[Candidate]:
    pool = []
    seen_titles: set[str] = set()

    for candidate in candidates:
        normalized = normalized_title(candidate.title)
        if (
            not normalized
            or candidate.year > cutoff_year
            or not uses_latin_script(candidate.title)
            or (domain, normalized) in exclusions
            or normalized in seen_titles
            or (domain == "songs" and VERSION_LABEL.search(candidate.title) is not None)
        ):
            continue
        seen_titles.add(normalized)
        pool.append(candidate)
        if len(pool) == size:
            break

    if len(pool) != size:
        raise ValueError(
            f"Only {len(pool)} eligible {domain} titles were found; {size} are required."
        )
    return pool


def select_titles(
    pools: dict[str, list[Candidate]],
    *,
    titles_per_domain: int,
    seed: int,
) -> list[Candidate]:
    selected = []

    for domain in DOMAINS:
        candidates = list(pools[domain])
        random.Random(f"{seed}:{domain}").shuffle(candidates)
        used_selection_groups: set[str] = set()
        domain_selection = []
        for candidate in candidates:
            selection_group = candidate.selection_group
            if selection_group and selection_group in used_selection_groups:
                continue
            domain_selection.append(candidate)
            if selection_group:
                used_selection_groups.add(selection_group)
            if len(domain_selection) == titles_per_domain:
                break

        if len(domain_selection) != titles_per_domain:
            raise ValueError(
                f"Only {len(domain_selection)} selectable {domain} titles were "
                f"found; {titles_per_domain} are required."
            )
        selected.extend(domain_selection)

    return sorted(
        selected,
        key=lambda row: (DOMAINS.index(row.domain), row.source_rank),
    )


def item_id(candidate: Candidate, used_ids: set[str]) -> str:
    ascii_title = (
        unicodedata.normalize("NFKD", candidate.title)
        .encode("ascii", "ignore")
        .decode()
    )
    title_slug = re.sub(r"[^a-z0-9]+", "_", ascii_title.casefold()).strip("_")
    source_slug = re.sub(r"[^a-z0-9]+", "_", candidate.source_id.casefold()).strip("_")
    base_id = f"{candidate.domain}_{title_slug or source_slug}"
    candidate_id = base_id
    if candidate_id in used_ids:
        candidate_id = f"{base_id}_{source_slug[:12]}"
    if candidate_id in used_ids:
        raise ValueError(f"Could not create a unique ID for {candidate.title}.")
    used_ids.add(candidate_id)
    return candidate_id


def write_outputs(
    selected: list[Candidate],
    *,
    dataset_id: str,
    output_path: Path,
    report_path: Path,
) -> None:
    used_ids: set[str] = set()
    rows = [(item_id(candidate, used_ids), candidate) for candidate in selected]
    profile = {
        "schema_version": 1,
        "dataset_id": dataset_id,
        "items": [
            {"id": identifier, "domain": row.domain, "title": row.title}
            for identifier, row in rows
        ],
    }

    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(
        "# Generated by scripts/datasets/build_dataset.py.\n"
        + yaml.safe_dump(profile, sort_keys=False, allow_unicode=True),
        encoding="utf-8",
    )

    report_path.parent.mkdir(parents=True, exist_ok=True)
    fieldnames = (
        "id",
        "domain",
        "title",
        "source",
        "source_rank",
        "source_id",
        "source_item_url",
        "artist",
        "metadata_year",
        "popularity",
        "length_group",
    )
    with report_path.open("w", encoding="utf-8", newline="") as file:
        writer = csv.DictWriter(file, fieldnames=fieldnames, lineterminator="\n")
        writer.writeheader()
        for identifier, row in rows:
            writer.writerow(
                {
                    "id": identifier,
                    "domain": row.domain,
                    "title": row.title,
                    "source": row.source,
                    "source_rank": row.source_rank,
                    "source_id": row.source_id,
                    "source_item_url": row.source_url,
                    "artist": row.artist,
                    "metadata_year": row.year,
                    "popularity": row.popularity,
                    "length_group": length_group(row.title),
                }
            )


def write_candidate_outputs(
    pools: dict[str, list[Candidate]],
    *,
    output_path: Path,
    report_path: Path,
) -> None:
    """Write the complete eligible pool used by the rating supplement."""
    candidates = [candidate for domain in DOMAINS for candidate in pools[domain]]
    used_ids: set[str] = set()
    rows = [(item_id(candidate, used_ids), candidate) for candidate in candidates]
    profile = {
        "schema_version": 1,
        "dataset_id": "eligible_top300_v1",
        "items": [
            {"id": identifier, "domain": row.domain, "title": row.title}
            for identifier, row in rows
        ],
    }

    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(
        "# Generated by scripts/datasets/build_dataset.py.\n"
        + yaml.safe_dump(profile, sort_keys=False, allow_unicode=True),
        encoding="utf-8",
    )

    report_path.parent.mkdir(parents=True, exist_ok=True)
    fieldnames = (
        "id",
        "domain",
        "title",
        "source",
        "source_rank",
        "source_id",
        "source_item_url",
        "artist",
        "selection_group",
        "metadata_year",
        "popularity",
        "length_group",
    )
    with report_path.open("w", encoding="utf-8", newline="") as file:
        writer = csv.DictWriter(file, fieldnames=fieldnames, lineterminator="\n")
        writer.writeheader()
        for identifier, row in rows:
            writer.writerow(
                {
                    "id": identifier,
                    "domain": row.domain,
                    "title": row.title,
                    "source": row.source,
                    "source_rank": row.source_rank,
                    "source_id": row.source_id,
                    "source_item_url": row.source_url,
                    "artist": row.artist,
                    "selection_group": row.selection_group,
                    "metadata_year": row.year,
                    "popularity": row.popularity,
                    "length_group": length_group(row.title),
                }
            )


def require_source_files(source_directory: Path) -> None:
    filenames = (
        "listenbrainz_recordings.json",
        "listenbrainz_artists.json",
        "listenbrainz_recording_metadata.json",
        "listenbrainz_artist_metadata.json",
        "imdb_title_basics.tsv.gz",
        "imdb_title_ratings.tsv.gz",
    )
    missing = [name for name in filenames if not (source_directory / name).exists()]
    if missing:
        raise FileNotFoundError(
            "Missing dataset source files: "
            + ", ".join(missing)
            + ". Run scripts/datasets/download_sources.sh first."
        )


def main() -> None:
    arguments = parse_arguments()

    if arguments.fetch_metadata:
        fetch_listenbrainz_metadata(arguments.source_directory)
        return
    if arguments.titles_per_domain <= 0:
        raise ValueError("--titles-per-domain must be positive.")
    if arguments.candidate_pool_size < arguments.titles_per_domain:
        raise ValueError("--candidate-pool-size must be at least --titles-per-domain.")

    require_source_files(arguments.source_directory)
    exclusions = load_exclusions(arguments.exclusions)
    candidates = {
        "songs": build_song_candidates(arguments.source_directory),
        "movies": build_movie_candidates(arguments.source_directory),
        "bands": build_band_candidates(arguments.source_directory),
    }
    pools = {
        domain: eligible_candidate_pool(
            candidates[domain],
            domain=domain,
            exclusions=exclusions,
            cutoff_year=arguments.cutoff_year,
            size=arguments.candidate_pool_size,
        )
        for domain in DOMAINS
    }
    write_candidate_outputs(
        pools,
        output_path=arguments.candidate_output,
        report_path=arguments.candidate_report,
    )
    selected = select_titles(
        pools,
        titles_per_domain=arguments.titles_per_domain,
        seed=arguments.seed,
    )
    write_outputs(
        selected,
        dataset_id=arguments.dataset_id,
        output_path=arguments.output,
        report_path=arguments.report,
    )

    print(
        f"Selected {len(selected)} titles ({arguments.titles_per_domain} per domain)."
    )
    print(f"Dataset: {arguments.output}")
    print(f"Source report: {arguments.report}")
    print(f"Candidate dataset: {arguments.candidate_output}")
    print(f"Candidate report: {arguments.candidate_report}")


if __name__ == "__main__":
    main()
