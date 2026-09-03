# Candidate illustratability: archived ratings and distribution

Source job: `20260902T162529Z_candidate-illustratability_a1cfe5f2`, completed on
2 September 2026. Q25, G3, Q38 and G4 each rated all 900 eligible candidates
(300 songs, 300 movies, 300 bands): **3,600 valid ratings, none missing**.
No images or title reconstructions are involved.

## Inspect the evidence

- [Original job](20260902T162529Z_candidate-illustratability_a1cfe5f2/): SQLite
  databases with raw responses, resolved configurations and prompt snapshots.
- [Distribution](report/candidate_pool_distribution.png) and
  [vector PDF](report/candidate_pool_distribution.pdf).
- [HTML report](report/candidate_distribution.html) and
  [executed notebook](report/candidate_distribution.executed.ipynb).
- [Per-title scores](report/candidate_pool_scores.csv): all four
  model ratings and their equally weighted mean, not only the selected titles.
- [Analysis manifest](report/manifest.json): source IDs, input hashes,
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
export RATING_JOB="$PWD/artifacts/candidate_illustratability/20260902T162529Z_candidate-illustratability_a1cfe5f2"
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
use the rating-job command in [PILOT.md](../../PILOT.md#3-obtain-the-full-candidate-ratings).
Stored responses reproduce this analysis; rerunning inference is not guaranteed
to produce byte-identical responses across deployments, even at temperature 0.

## Archive provenance

The author downloaded the completed DGX job into `bachelor_runs_from_dgx/` and
copied it here on 3 September 2026 using `rsync -a`. All 23 persistent files are
byte-identical to that download. The five `-wal` files were checked to be empty;
only these empty logs and the five temporary `-shm` files were omitted.
SQLite integrity checks passed for all five databases, all four child runs were
completed, and their title rosters matched the shipped eligible-candidate CSV.
The original download was retained unchanged.

The report was regenerated with the dedicated distribution notebook after the
notebook split. All model scores, title means, bin counts and the rendered PNG
are identical to the previous combined-notebook output. Only report organization
and provenance exports changed; the source job remains untouched.

This directory is included in Git, unlike generated `runs/` and notebook-result
directories. It is excluded from Docker images. To check the archived files:

```bash
cd artifacts/candidate_illustratability
shasum -a 256 -c SHA256SUMS
```

`SHA256SUMS` covers the persistent job files and the archived report. SQLite may
recreate ignored temporary `-shm`/`-wal` files during read-only analysis; these
are not part of the published evidence.
