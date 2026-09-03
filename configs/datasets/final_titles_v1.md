# `final_titles_v1`

`final_titles_v1` contains 30 songs, 30 movie titles and 30 band names. A change
to the source snapshot, rules, seed or sample size requires a new dataset
version.

## Selection

For each domain, traverse its popularity ranking and retain the first 300
eligible entries. Shuffle that pool with seed `20260811` and select 30 titles.
There are no title-length quotas.

Eligibility rules:

- release by 2018; bands are MusicBrainz `Group` entities formed by 2018;
- Latin-script title;
- no duplicate title or any of the six development titles;
- no adult movie entries;
- no song variants labelled live, remix, remaster, edit, mix, acoustic, demo,
  instrumental, mono or stereo;
- at most one selected song per primary artist.

Popularity bounds the candidate pool; it is not compared numerically across
sources. Fixed-seed sampling avoids manual selection by expected success. Title
length remains descriptive only.

There is no illustratability filter. The separate 900-candidate rating profile
supports this choice, including low/high-score concentrations and domain
differences. The protocol retains the random main sample; skewness alone does
not trigger filtering. Any later change requires a documented
protocol decision and a new dataset version, not an overwrite of this sample.

## Sources

- Songs: [ListenBrainz sitewide all-time recordings](https://listenbrainz.readthedocs.io/en/latest/users/api/statistics.html),
  enriched with MusicBrainz metadata.
- Bands: [ListenBrainz sitewide all-time artists](https://listenbrainz.readthedocs.io/en/latest/users/api/statistics.html),
  restricted with MusicBrainz artist metadata.
- Movies: [IMDb non-commercial datasets](https://developer.imdb.com/non-commercial-datasets/),
  ranked by `numVotes`.

The downloaded source snapshot stays outside Git. The repository keeps the
selected YAML and item-level source report so every condition uses the same
titles.

## Rebuild

From the repository root:

```bash
./scripts/datasets/download_sources.sh
.venv/bin/python scripts/datasets/build_dataset.py
```

Outputs:

- `configs/datasets/final_titles_v1.yaml`;
- `configs/datasets/final_titles_v1_sources.csv`;
- `configs/datasets/eligible_top300_v1.yaml`;
- `configs/datasets/eligible_top300_v1_sources.csv`.

The first two files are the random main dataset. The latter two are the complete
900-candidate profile used only by the separately documented rating and
high-illustratability supplement. A reproducibility check must rebuild all four
files byte-for-byte. Any method change creates V2 instead of overwriting V1.

## Scope

The sample represents popular eligible entries in ListenBrainz and IMDb, not all
works or bands. Four generated observations per title estimate generation
variability but do not create additional independent titles. Domain results are
subgroup estimates for these 30 titles and should not be generalized as small
population-wide effects.
