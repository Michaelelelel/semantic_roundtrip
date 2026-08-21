# Study analysis

Jobs execute experiments. A study selects completed runs and declares the
scientific comparisons, even when the runs came from different jobs or machines.

## Configuration

Create a study directory below the mounted `runs/` root and copy the example:

```bash
mkdir -p runs/final-study
cp configs/studies/final_study.example.yaml runs/final-study/study.yaml
```

Each entry under `conditions` names exactly one completed run:

```yaml
conditions:
  current:
    run: ../some-job/runs/some-run
    label: Current system
```

The condition ID, such as `current`, is used by groups. The optional label is
shown in figures. Run paths are resolved relative to the directory containing
`study.yaml` and may point into different job directories.

## Group kinds

Each group answers one question and creates one high-resolution PNG named after
the group, for example `figures/complete_systems.png`. All figures report the
overall result and the individual domains with 95% title-bootstrap intervals.

### `accuracy`: absolute performance

```yaml
groups:
  complete_systems:
    kind: accuracy
    conditions:
      - legacy
      - intermediate
      - current
    route: direct
```

The figure shows the title-level end-to-end Strict Exact accuracy of every
condition. The vertical scale runs from 0% to 100%. `route` may be `direct` or
`description` and defaults to `direct`.

Use this group for the main question: how accurately does each configured system
reconstruct titles?

### `paired`: difference from one reference

```yaml
groups:
  image_models:
    kind: paired
    conditions:
      - sd15
      - sdxl
      - current
    reference: current
    route: direct
```

For every non-reference condition, the analyzer pairs matching titles and
calculates:

```text
condition accuracy - reference accuracy
```

The figure reports this difference in percentage points. Positive values mean the
condition performed better; negative values mean the reference performed better.
Zero means no observed difference. The selected runs must contain the same dataset,
titles, prompt seeds, image seeds, and repetition counts for the selected route.

Use this group for a controlled local comparison around an anchor, such as changing
only the prompt, image, or reconstruction model.

### `routes`: description route versus direct route

```yaml
groups:
  reconstruction_routes:
    kind: routes
    conditions:
      - llava
      - qwen_vl
      - current
```

Within every condition, the analyzer pairs the two predictions produced from the
same expected images and calculates:

```text
description-route accuracy - direct-route accuracy
```

The figure reports the difference in percentage points:

- positive: the description route performed better;
- negative: the direct route performed better;
- zero: both routes had the same observed accuracy.

For example, `-25 pp` means the description route was 25 percentage points less
accurate than the direct route. A `routes` group has no `reference`; each condition
is compared with itself. Every selected run must contain both routes on the same
title and seed grid.

## Shared validation

- Every condition must be used by at least one group.
- A run directory may only appear once under `conditions`.
- Conditions in the same group must have matching datasets, titles, and seed grids.
- `paired` requires at least two conditions and a reference included in the group.
- `routes` requires both direct and description predictions.
- Group IDs become figure filenames and should describe the research question.

## Run the analysis

```bash
semantic-roundtrip study analyze --study runs/final-study
```

With Docker:

```bash
sudo docker compose -f compose.yaml run --rm runner \
  semantic-roundtrip study analyze --study runs/final-study
```

The command reads the SQLite databases directly and never modifies a run. It writes
CSV evidence tables and exactly one PNG for each group into `results/`. Strict
end-to-end exact accuracy is the primary metric. Normalized Exact, failures,
verifier results, and runtimes are supporting diagnostics.

Use `--force` only when an existing results directory should be replaced.

## Recommended thesis use

- Use `accuracy` figures for the primary complete-system results.
- Use `paired` figures for model substitutions relative to the fixed anchor.
- Use `routes` only for experiments that actually study direct versus
  description-mediated reconstruction.
- Explain absolute accuracies before interpreting differences.
- Keep the same condition order and domain colors across related figures.
- Interpret point estimates together with their confidence intervals, not only by
  whether an interval crosses zero.
