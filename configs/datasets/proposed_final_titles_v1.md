# Proposed final title dataset V1

This dataset is the proposed input for the final thesis experiments. Review and
freeze it before inspecting final model results.

## Selection

- Domains: songs, movies and bands.
- 60 titles per domain: 20 one-word, 20 two-to-three-word and 20 four-or-more-word titles.
- Works must be released by 2018; bands must be MusicBrainz `Group` entities formed by 2018.
- The six development titles are excluded.
- Only Latin-script titles are included.
- Songs labelled as live, remix, remaster, edit, mix, acoustic, demo,
  instrumental, mono or stereo versions are excluded.
- The 300 most popular eligible candidates per domain form the sampling pool.
- Sampling uses the fixed seed `20260811`.
- At most one selected song comes from each primary artist.

Popularity defines the candidate pool only. ListenBrainz listen counts are not
compared numerically with IMDb vote counts.

## Sources

- Songs: [ListenBrainz sitewide all-time recordings](https://listenbrainz.readthedocs.io/en/latest/users/api/statistics.html), enriched with MusicBrainz metadata.
- Bands: [ListenBrainz sitewide all-time artists](https://listenbrainz.readthedocs.io/en/latest/users/api/statistics.html), restricted using MusicBrainz artist metadata.
- Movies: [IMDb non-commercial datasets](https://developer.imdb.com/non-commercial-datasets/), ranked by `numVotes`.

The source files are downloaded once and kept locally because they are large or
updated over time. The selected YAML and its CSV source report are committed so
every model stack receives exactly the same titles.

## Build

From the repository root:

```bash
./scripts/datasets/download_sources.sh
.venv/bin/python scripts/datasets/build_dataset.py
```

The first command creates `data/title_sources/v1/`, which is ignored by Git. The
second command writes:

- `configs/datasets/proposed_final_titles_v1.yaml` for the pipeline;
- `configs/datasets/proposed_final_titles_v1_sources.csv` for review and thesis provenance.

To test another valid size without changing the method:

```bash
.venv/bin/python scripts/datasets/build_dataset.py \
  --titles-per-domain 90 \
  --candidate-pool-size 600
```

The number must be a positive multiple of three. A larger sample also needs a
larger popularity pool, and the build stops clearly if the downloaded top 1,000
entries do not contain enough titles in one length group. Once V1 is approved,
changing a source snapshot or selection rule should create V2 instead of
overwriting V1.

## Limitation

The dataset represents popular titles in the ListenBrainz and IMDb communities,
not all existing works or bands. Balancing title lengths improves comparisons but
does not reproduce their natural distribution. These limitations belong in the
thesis methodology.
