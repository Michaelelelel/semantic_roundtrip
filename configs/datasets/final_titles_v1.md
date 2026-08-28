# Final title dataset V1

This dataset is frozen for the final thesis experiments. Any later change creates
a new dataset version and a new study revision.

## Selection

- Domains: songs, movies and bands.
- 30 titles per domain: 10 one-word, 10 two-to-three-word and 10 four-or-more-word titles.
- Works must be released by 2018; bands must be MusicBrainz `Group` entities formed by 2018.
- The six development titles are excluded.
- Only Latin-script titles are included.
- Songs labelled as live, remix, remaster, edit, mix, acoustic, demo,
  instrumental, mono or stereo versions are excluded.
- The 300 most popular eligible candidates per domain form the sampling pool.
- Sampling uses the fixed seed `20260811`.
- At most one selected song comes from each primary artist.

The source rankings are traversed from most to least popular. Release/formation
year, script, duplicate-title, development-title, entity-type, adult-content,
and song-version filters are applied before traversal stops at 300 retained
titles per domain. The one-song-per-primary-artist rule is applied later, during
the fixed-seed selection of the final 30 songs.

Popularity defines the candidate pool only. ListenBrainz listen counts are not
compared numerically with IMDb vote counts.

### Rationale for the selection rules

- A popularity-bounded pool reduces extremely obscure cultural references while
  fixed-seed sampling prevents manual selection according to expected visual or
  reconstruction success.
- Equal short, medium, and long groups prevent title length from being
  distributed differently across domains, which matters especially for Exact
  Match.
- The 2018 cutoff reduces the risk that very recent entries systematically favor
  newer checkpoints; it does not claim that any title occurred in a particular
  training set.
- Latin-script restriction keeps script handling and string comparison more
  comparable across the selected models and domains.
- Song-version filters remove near-duplicate or qualified variants whose suffixes
  would create a distinct Exact-Match problem unrelated to visual semantics.
- Excluding development titles prevents technical prompt and adapter work from
  using final observations.
- The one-song-per-primary-artist rule limits dependence on one artist's cultural
  associations and prevents a popular artist from dominating the song sample.

## Sources

- Songs: [ListenBrainz sitewide all-time recordings](https://listenbrainz.readthedocs.io/en/latest/users/api/statistics.html), enriched with MusicBrainz metadata.
- Bands: [ListenBrainz sitewide all-time artists](https://listenbrainz.readthedocs.io/en/latest/users/api/statistics.html), restricted using MusicBrainz artist metadata.
- Movies: [IMDb non-commercial datasets](https://developer.imdb.com/non-commercial-datasets/), ranked by `numVotes`.

The source files are downloaded once and kept locally because they are large or
updated over time. The selected YAML and its CSV source report are committed so
every model stack receives exactly the same titles.

## Why 30 titles per domain

The study currently uses 90 independent titles: 30 songs, 30 movies and 30 bands.
Every model condition receives exactly the same titles, which allows paired
title-level comparisons. Two prompt seeds and two image seeds create four repeated
observations for every title and condition. These repetitions measure generation
variability, but they are not counted as additional independent titles.

This size is appropriate for the scoped bachelor study because the primary goal is
to compare complete systems and selected model substitutions across the full
90-title dataset, not to estimate small population-wide differences inside each
domain. The balanced design also retains ten short, ten medium and ten long titles
per domain. Increasing the sample to 60 titles per domain would improve the
precision of domain-specific estimates, but would also double the largest part of
the execution cost. Domain-specific results are therefore reported as secondary
subgroup results with uncertainty intervals and without claims about small effects.

The choice is not a technical limit. The generation script accepts a larger count,
so a later study can extend the dataset with the same eligibility, balancing and
fixed-seed selection procedure. Such an extension must be stored under a new dataset
version and decided before inspecting its final model results.

## Build

From the repository root:

```bash
./scripts/datasets/download_sources.sh
.venv/bin/python scripts/datasets/build_dataset.py
```

The first command creates `data/title_sources/v1/`, which is ignored by Git. The
second command writes:

- `configs/datasets/final_titles_v1.yaml` for the pipeline;
- `configs/datasets/final_titles_v1_sources.csv` for review and thesis provenance.

To extend the dataset to 60 titles per domain without changing the method:

```bash
.venv/bin/python scripts/datasets/build_dataset.py \
  --titles-per-domain 60
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
