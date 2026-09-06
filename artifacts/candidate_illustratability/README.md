# Candidate illustratability: ratings and distribution

Source job: `20260902T162529Z_candidate-illustratability_a1cfe5f2`, completed on
2 September 2026. Q25, G3, Q38 and G4 each rated all 900 eligible candidates
(300 songs, 300 movies, 300 bands): **3,600 valid ratings, none missing**.
No images or title reconstructions are involved.

## Published inputs and outputs

Use the completed rating job in [`current/jobs/`](current/jobs/) with the
application, distribution notebook and stage inheritance. Its report is in
[`current/report/`](current/report/). Use `current/jobs/` as the website discovery
root; each Job/Run ID must occur only once within that root.

The supplied 90-title supplementary dataset and six development titles are in
`configs/datasets/`. The selector uses the stored four-model ratings, not new
model calls or reconstruction outcomes. `current/validation.json` records
checks of the rating data, title selection and report. Raw responses, recorded
settings, source identifiers and timestamps remain attached to the results.

## Inspect the evidence

- [Rating job](current/jobs/20260902T162529Z_candidate-illustratability_a1cfe5f2/): SQLite
  databases with raw responses, resolved configurations and prompt snapshots.
- [Distribution](current/report/candidate_pool_distribution.png) and
  [vector PDF](current/report/candidate_pool_distribution.pdf).
- [HTML report](current/report/candidate_distribution.html) and
  [executed notebook](current/report/candidate_distribution.executed.ipynb).
- [Per-title scores](current/report/candidate_pool_scores.csv): all four
  model ratings and their equally weighted mean, not only the selected titles.
- [Analysis manifest](current/report/manifest.json): source IDs, input hashes,
  package versions and analysis settings. Absolute paths record the author's
  execution environment; use the portable commands below on another machine.

The figure covers the **whole candidate pool**, not the 90-title main sample or
the held-out style pilot. The dedicated distribution notebook contains no style-job inputs or inactive
reconstruction sections.

## Method and interpretation

The saved `rating_v2` prompt requests an integer from 0 to 100. The rating runs
use temperature 0, seed `4001`, a 512-token output ceiling and thinking off.
Each histogram observation is one title's mean across all four models. All four
valid ratings are required; there is no imputation. There are 20 five-point bins,
left-inclusive and right-exclusive except the last bin, which includes 100.

| Domain | Complete titles | Mean of title means | Range of title means |
| --- | ---: | ---: | ---: |
| Songs | 300 | 58.59 | 10.00–92.50 |
| Movies | 300 | 77.68 | 38.75–96.25 |
| Bands | 300 | 53.58 | 18.75–95.00 |

Movies receive higher mean ratings in this run. Individual models differ
substantially in their use of the scale; the mean is a descriptive summary,
not human ground truth or a probability of successful reconstruction.

The profile makes domain differences, low/high-score concentrations and tails
visible. Skewness alone is not a reason to filter. The random main dataset is
unchanged; no filter or selection decision follows automatically from this
figure. The scientific rationale is in the thesis Methodology, under
“Candidate-Profile Review and Main-Sample Rationale”. The separate
high-illustratability supplement is described in
[EXPERIMENTS.md](../../EXPERIMENTS.md#illustratable-dataset).

## Reproduce the analysis without models

Run from the `semantic_roundtrip` repository root. `$PWD` makes the job path
absolute; it must identify the outer job directory, not a child run or database.
New outputs go to `notebooks/results/`, leaving this archived report unchanged.

```bash
uv sync --frozen --extra analysis
export RATING_JOB="$PWD/artifacts/candidate_illustratability/current/jobs/20260902T162529Z_candidate-illustratability_a1cfe5f2"
export OUTPUT_DIR="$PWD/notebooks/results/candidate_illustratability"

uv run jupyter nbconvert --to notebook --execute notebooks/illustratability_distribution.ipynb \
  --ExecutePreprocessor.timeout=1200 \
  --output candidate_distribution.executed --output-dir "$OUTPUT_DIR"
uv run jupyter nbconvert --to html --no-input \
  "$OUTPUT_DIR/candidate_distribution.executed.ipynb" \
  --output candidate_distribution --output-dir "$OUTPUT_DIR"
```

Alternatively, open `notebooks/illustratability_distribution.ipynb` with Jupyter after setting the
same variables, restart the kernel and run all cells. Repeating **model inference** is a different step:
use the rating-job command in [EXPERIMENTS.md](../../EXPERIMENTS.md#illustratable-dataset).
Stored responses reproduce this analysis; rerunning inference is not guaranteed
to produce byte-identical responses across deployments, even at temperature 0.

## Data integrity and reproducibility

SQLite integrity checks pass for all five databases. All four child runs are
complete, and their title rosters match the supplied eligible-candidate CSV.
The validation record checks all 3,600 ratings, all 900 candidates and the exact
90-title final and six-title development selections. The report identifies its
input files, analysis code and software versions; it is an analysis of stored
responses, not evidence of an additional rating run. Numerical results can be
reproduced from these responses; platform-specific rendering and new execution
timestamps need not be byte-identical.

This directory is included in Git, unlike generated `runs/` and notebook-result
directories. It is excluded from Docker images. The scoped `.gitattributes`
preserves archive bytes across Windows and Linux checkouts. SQLite may
recreate ignored temporary `-shm`/`-wal` files during read-only analysis; these
are not part of the published evidence.

From the repository root, check the published job, report and validation record:

```bash
cd artifacts/candidate_illustratability/current
shasum -a 256 -c SHA256SUMS
```
