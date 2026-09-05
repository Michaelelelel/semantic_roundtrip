#!/usr/bin/env bash
set -euo pipefail

REPOSITORY_ROOT=$(cd "$(dirname "$0")/../.." && pwd)
cd "$REPOSITORY_ROOT"

SOURCE_DIRECTORY=${1:-data/title_sources/v1}
mkdir -p "$SOURCE_DIRECTORY"

download() {
  url=$1
  destination=$2

  if [[ -f "$destination" ]]; then
    echo "Keep $destination"
    return
  fi

  echo "Download $url"
  curl --fail --location --retry 5 --retry-all-errors \
    --output "$destination.part" "$url"
  mv "$destination.part" "$destination"
}

download \
  "https://datasets.imdbws.com/title.basics.tsv.gz" \
  "$SOURCE_DIRECTORY/imdb_title_basics.tsv.gz"
download \
  "https://datasets.imdbws.com/title.ratings.tsv.gz" \
  "$SOURCE_DIRECTORY/imdb_title_ratings.tsv.gz"
download \
  "https://api.listenbrainz.org/1/stats/sitewide/recordings?range=all_time&count=1000" \
  "$SOURCE_DIRECTORY/listenbrainz_recordings.json"
download \
  "https://api.listenbrainz.org/1/stats/sitewide/artists?range=all_time&count=1000" \
  "$SOURCE_DIRECTORY/listenbrainz_artists.json"

PYTHON=.venv/bin/python
if [[ ! -x "$PYTHON" ]]; then
  PYTHON=python3
fi

if [[ ! -f "$SOURCE_DIRECTORY/listenbrainz_recording_metadata.json" \
   || ! -f "$SOURCE_DIRECTORY/listenbrainz_artist_metadata.json" ]]; then
  "$PYTHON" scripts/datasets/build_dataset.py \
    --source-directory "$SOURCE_DIRECTORY" \
    --fetch-metadata
fi

if [[ ! -f "$SOURCE_DIRECTORY/retrieved_at_utc.txt" ]]; then
  date -u +%Y-%m-%dT%H:%M:%SZ > "$SOURCE_DIRECTORY/retrieved_at_utc.txt"
fi

echo "Source snapshot: $SOURCE_DIRECTORY"
