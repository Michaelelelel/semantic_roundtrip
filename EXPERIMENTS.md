# Reproduce the thesis experiments

This guide runs the main, four-style and supplementary designs documented in
the thesis Methodology. Exact settings are in
[STUDY_DESIGN.md](configs/jobs/final_study/STUDY_DESIGN.md).

## Prerequisites and scope

1. Complete [DGX installation](RUNNING.md#one-time-dgx-setup) if needed.
2. Follow [environment, build and services](RUNNING.md#services-and-shell-setup).
3. Use the same code/config revision across hosts. Run one model job at a time
   per shared runtime stack.

These commands use the `RUN_ROOT` configured in `.env`. If you deliberately
select another run directory through the shell, preserve `RUN_ROOT` through
`sudo` as described in [shell setup](RUNNING.md#once-per-terminal-or-tmux-window).
The CLI and analysis use the [documented application formats](RUNNING.md#run-storage-and-reproducibility).

The random main dataset has 90 titles (30 per domain), without illustratability
or title-length quotas. Each title uses two prompt seeds crossed with two image
seeds. Use the shipped dataset; do not redraw it for a new condition.

Every image-dependent study condition persists the same three checks: normalized
reference-title absence in the generated prompt, blind image rejection of any
meaningful readable text, and title-aware image rejection of the reference
title only. The first image policy with Strict Exact Match is primary; the
title-aware and normalized variants are sensitivity outcomes. Verification
affects scoring but never stops generation or reconstruction.
Prompt reconstruction adds one prediction per stored prompt plus domain, with
the prompt check only; image seeds and image policies do not enter that score.

The main study uses Direct Core, Local Indirect and either the two-part Aqueduct
extension or its single-job alternative. This gives four main jobs with the
split, or three with the single extension, plus six supplementary jobs and the
candidate-rating job. Direct Core also supplies the unrestricted condition of
the four-style comparison:

| Group | Job config | Design / research question | Prerequisite |
| --- | --- | --- | --- |
| Main | `direct_core.yaml` | 4 x 4 direct; four paired indirect baselines (RQ1, RQ3, SQ4) | services ready |
| Main | `indirect_local.yaml` | 2 x 4 x 2 local indirect (RQ2, SQ4) | services ready |
| Main, split part 1 | `aqueduct_v4_independent.yaml` | 8 additions: V4 PG x 4 ID x D32/O120 TG (RQ2, SQ4) | idle local model stack; API key |
| Main, split part 2 | `aqueduct_v4_completion.yaml` | 12 additions: D32/O120/V4 PG x 4 ID x V4 TG (RQ2, SQ4) | exact completed local-indirect and independent V4 jobs; API key |
| Main, single-job alternative | `aqueduct_v4_extension.yaml` | the same 20 additions completing 3 x 4 x 3 (RQ2, SQ4) | exact completed local-indirect job; API key |
| Supplement | `direct_sketch.yaml` | 4 x 4 sketch (SQ2) | services ready |
| Supplement | `direct_comic.yaml` | 4 x 4 comic (SQ2) | services ready |
| Supplement | `direct_photorealistic.yaml` | 4 x 4 photorealistic (SQ2) | services ready |
| Supplement | `direct_thinking.yaml` | 4 x 4 native-thinking comparison (SQ3) | exact completed direct-core job |
| Supplement | `direct_illustratable.yaml` | 4 x 4 selected-title comparison (SQ5) | completed ratings, selection and runner rebuild |
| Supplement | `direct_prompt_only.yaml` | 4 x 4 prompt/direct and four-diagonal three-way comparison (SQ1) | selected unrestricted reference; exact completed direct-core source |

RQ1–RQ3 are primary research questions; SQ1–SQ5 are secondary research
questions covering prompt reconstruction, visual style, native thinking, title
domains and illustratability, respectively. SQ4 compares title domains using the
main jobs, without an additional experiment. The main/supplementary job grouping
describes execution, not question priority.

All job configs above are under `configs/jobs/final_study/`. Only the high-illustratability
reconstruction job depends on the candidate ratings. The high-illustratability
dataset is a supplement, not a replacement for the random main sample.
Choose the 8+12 split or the single 20-condition extension. They cover the same
conditions and must not be combined as additional observations. Together with
the 16 Local Indirect conditions, either choice gives 36 conditions.

The commands use the unrestricted reference described in STUDY_DESIGN.
The complete four-style report supported retaining this reference. Source
profiles and bindings must match that style across the compared routes.

![Main and supplementary study jobs](diagrams/study_jobs.svg)

[Editable Mermaid source](diagrams/study_jobs.mmd). The arrows mark data or
baseline dependencies; independent jobs do not need to run in the illustrated
order.

`job start` validates, creates a snapshot and runs in the foreground. Save its
printed Job ID. Use [resume](RUNNING.md#monitor-and-resume), not another start,
for an interrupted job. `job plan` is an optional read-only overview: replace
`start` with `plan` and keep the same config/source arguments.

## Job IDs and source paths

List completed jobs:

```bash
sudo docker compose --env-file .env \
  -f compose.yaml -f compose.dgx.yaml -f compose.status.yaml \
  --profile runner --profile status run --rm runner \
  semantic-roundtrip job list --root runs --status completed
```

Choose the exact matching **Job ID**, not a child-run ID or full path. If missing,
run the source job first or copy its complete directory, including child runs,
from the other DGX into this host's `RUN_ROOT`. No source is chosen automatically.

## Main experiments

Direct Core, Local Indirect and Aqueduct Independent have no source-job
dependency on one another. Separate Spark hosts can run Local Indirect and
Aqueduct Independent concurrently, with one job per local model stack.
Aqueduct Completion follows both completed sources. The single Aqueduct
extension remains an alternative after Local Indirect completes.

### Direct core

```bash
sudo docker compose --env-file .env \
  -f compose.yaml -f compose.dgx.yaml -f compose.status.yaml \
  --profile runner --profile status run --rm runner \
  semantic-roundtrip job start \
  --config configs/jobs/final_study/direct_core.yaml
```

### Local indirect

```bash
sudo docker compose --env-file .env \
  -f compose.yaml -f compose.dgx.yaml -f compose.status.yaml \
  --profile runner --profile status run --rm runner \
  semantic-roundtrip job start \
  --config configs/jobs/final_study/indirect_local.yaml
```

### Aqueduct split across two Sparks

The independent job executes V4 prompt generation, local image generation and
verification, four local description models and D32/O120 title guessing. It
creates 360 images and 2,880 description-route predictions. The completion job
imports the existing prompts, images, descriptions and both verification stages
from the two exact sources, then executes 4,320 V4 title predictions. It creates
no new images. Models, settings, observations and upstream reuse are identical
to the single 20-condition extension.

After committing and pushing the verified changes yourself, update only an idle
host from its existing repository directory. Leave a host running Local
Indirect on its current runner until that job finishes:

```bash
git status --short
git pull --ff-only

sudo docker compose --env-file .env \
  -f compose.yaml -f compose.dgx.yaml -f compose.status.yaml \
  --profile runner --profile status build runner
```

Inspect any local changes before pulling. Load `.env` as described in
[shell setup](RUNNING.md#once-per-terminal-or-tmux-window). The existing model
services must already be healthy. The commands below use `--no-deps` to keep
those service containers, including any ComfyUI recovery mounts and offline
upgrade guards, in place. Do not run a blanket service recreation for this job
configuration update.

#### Part 1 — Independent V4 job

On the idle Spark, start the eight-condition job while Local Indirect may
continue on the other Spark:

```bash
sudo --preserve-env=AQUEDUCT_API_KEY docker compose --env-file .env \
  -f compose.yaml -f compose.dgx.yaml -f compose.status.yaml \
  --profile runner --profile status run --rm --no-deps -e AQUEDUCT_API_KEY runner \
  semantic-roundtrip job start \
  --config configs/jobs/final_study/aqueduct_v4_independent.yaml
```

Save the actual printed Job ID. Host assignment, completion and Job IDs must be
checked from the current execution; the input prompts below contain no verified
remote IDs.

#### Part 2 — Bring both completed sources onto the completion host

Wait for Local Indirect and Aqueduct Independent to complete, then choose an
idle host for Completion. Both full source job directories must be under that
host's `RUN_ROOT`, including databases, child runs, images, snapshots and
provenance. An analysis copy without images is insufficient for execution.

For each source absent from the destination host, enter its actual SSH host,
absolute source run root and Job ID. Run the input commands separately before
the copy block:

```bash
read -r -p "Source SSH host (user@host): " SOURCE_SSH
read -r -p "Absolute source RUN_ROOT: " SOURCE_RUN_ROOT
read -r -p "Completed source Job ID: " SOURCE_JOB_ID
```

From the destination host, copy the complete directory. This block refuses an
existing destination. The final checksum dry run should print no changed files:

```bash
(
  set -e
  [[ "$SOURCE_JOB_ID" =~ ^[[:alnum:]][[:alnum:]_-]*$ ]]
  [[ "$SOURCE_RUN_ROOT" = /* ]]
  test -d "${RUN_ROOT:?Load the destination .env first}"
  test ! -e "$RUN_ROOT/${SOURCE_JOB_ID:?Enter the source Job ID first}"
  rsync -a --checksum --protect-args \
    "${SOURCE_SSH:?Enter the source SSH host}:${SOURCE_RUN_ROOT}/${SOURCE_JOB_ID}" \
    "$RUN_ROOT/"
  rsync -a --checksum --dry-run --itemize-changes --protect-args \
    "${SOURCE_SSH}:${SOURCE_RUN_ROOT}/${SOURCE_JOB_ID}" "$RUN_ROOT/"
)
```

Keep the completed sources inactive during transfer. If copying or comparison
fails, resolve it before continuing. For a source already on this host, retain
its complete directory and verify its identity using
[the completed-job listing](#job-ids-and-source-paths).

#### Part 3 — Complete the twelve V4 guessing conditions

On the idle completion host, use the updated runner image and enter both exact
completed source Job IDs:

```bash
read -r -p "Completed final_indirect_local Job ID: " INDIRECT_JOB_ID
read -r -p "Completed final_aqueduct_v4_independent Job ID: " V4_INDEPENDENT_JOB_ID
```

Then start Completion with both explicit aliases:

```bash
sudo --preserve-env=AQUEDUCT_API_KEY docker compose --env-file .env \
  -f compose.yaml -f compose.dgx.yaml -f compose.status.yaml \
  --profile runner --profile status run --rm --no-deps -e AQUEDUCT_API_KEY runner \
  semantic-roundtrip job start \
  --config configs/jobs/final_study/aqueduct_v4_completion.yaml \
  --source-job "local_indirect=runs/${INDIRECT_JOB_ID:?Enter the Local Indirect Job ID first}" \
  --source-job "v4_independent=runs/${V4_INDEPENDENT_JOB_ID:?Enter the Independent V4 Job ID first}"
```

### Aqueduct single-job alternative

Needs the API key loaded from `.env` in [shell setup](RUNNING.md#once-per-terminal-or-tmux-window) and the completed Local Indirect
Job ID. Use this instead of the two split jobs:

```bash
read -r -p "Completed final_indirect_local Job ID: " INDIRECT_JOB_ID
```

Then start the extension:

```bash
sudo --preserve-env=AQUEDUCT_API_KEY docker compose --env-file .env \
  -f compose.yaml -f compose.dgx.yaml -f compose.status.yaml \
  --profile runner --profile status run --rm --no-deps -e AQUEDUCT_API_KEY runner \
  semantic-roundtrip job start \
  --config configs/jobs/final_study/aqueduct_v4_extension.yaml \
  --source-job "local_indirect=runs/${INDIRECT_JOB_ID:?Enter the Local Indirect Job ID first}"
```

## Four-style comparison and supplementary experiments

Direct Core is the unrestricted 4 x 4 condition. Photorealistic, Sketch and
Comic use separate complete 4 x 4 matrices on the same titles and four seed
combinations. Thinking imports the four unchanged Q25/G3 cells from Direct Core
and executes the twelve changed cells.

### Photorealistic

```bash
sudo docker compose --env-file .env \
  -f compose.yaml -f compose.dgx.yaml -f compose.status.yaml \
  --profile runner --profile status run --rm runner \
  semantic-roundtrip job start \
  --config configs/jobs/final_study/direct_photorealistic.yaml
```

### Sketch

```bash
sudo docker compose --env-file .env \
  -f compose.yaml -f compose.dgx.yaml -f compose.status.yaml \
  --profile runner --profile status run --rm runner \
  semantic-roundtrip job start \
  --config configs/jobs/final_study/direct_sketch.yaml
```

### Comic

```bash
sudo docker compose --env-file .env \
  -f compose.yaml -f compose.dgx.yaml -f compose.status.yaml \
  --profile runner --profile status run --rm runner \
  semantic-roundtrip job start \
  --config configs/jobs/final_study/direct_comic.yaml
```

### Thinking

First enter the completed Direct Job ID. Run the input command by itself and
answer the prompt before continuing:

```bash
read -r -p "Completed final_direct_core Job ID: " DIRECT_JOB_ID
```

Then start Thinking; it reuses the unchanged Q25/G3 cells:

```bash
sudo docker compose --env-file .env \
  -f compose.yaml -f compose.dgx.yaml -f compose.status.yaml \
  --profile runner --profile status run --rm runner \
  semantic-roundtrip job start \
  --config configs/jobs/final_study/direct_thinking.yaml \
  --source-job "direct_base=runs/${DIRECT_JOB_ID:?Enter the Direct Job ID first}"
```

### Illustratable dataset

This supplementary dataset does not replace the random main dataset. Its
900-candidate pool is already present. Four models rate each candidate once:
3,600 planned ratings, no image generation.

The completed source job and its model-free distribution analysis are included
in [the candidate-rating archive](artifacts/candidate_illustratability/README.md).
The sequence below reruns inference on the DGX; the archive needs no rerun to
inspect the ratings. Archived evidence is not bundled into the runner image.

For the shipped study inputs, both selected dataset YAMLs and selection CSVs
already exist; no rating rerun or reselection is necessary. To use these
datasets, continue with Step 4. Steps 1–3 reproduce rating inference and
selection. The stored rating job used by the distribution notebook is under
`artifacts/candidate_illustratability/20260902T162529Z_candidate-illustratability_a1cfe5f2/`; its source identifiers,
raw responses and reporting evidence are provided with the data.

#### Step 1 — Run the rating job

Skip only if you already have its completed job for this study.

```bash
sudo docker compose --env-file .env \
  -f compose.yaml -f compose.dgx.yaml -f compose.status.yaml \
  --profile runner --profile status run --rm runner \
  semantic-roundtrip job start \
  --config configs/jobs/final_study/candidate_illustratability.yaml
```

**Wait until all four rating runs are completed.** Save the printed Job ID.
Do not run the selector while ratings are still running.

#### Step 2 — Choose that completed job

```bash
sudo docker compose --env-file .env \
  -f compose.yaml -f compose.dgx.yaml -f compose.status.yaml \
  --profile runner --profile status run --rm runner \
  semantic-roundtrip job list --root runs --status completed
```

Find `candidate_illustratability`. If missing, finish step 1 or copy the completed
job from the other DGX. Do not invent a directory. Run this input command by itself
and paste the Job ID:

```bash
read -r -p "Completed candidate_illustratability Job ID: " RATING_JOB_ID
```

#### Step 3 — Select and save the datasets

Run inside Docker. The dataset mount saves outputs in your host checkout, so
removing the temporary container does not remove the generated files:

```bash
sudo docker compose --env-file .env \
  -f compose.yaml -f compose.dgx.yaml -f compose.status.yaml \
  --profile runner --profile status run --rm --no-deps \
  -v "$PWD/configs/datasets:/app/configs/datasets" \
  runner python scripts/datasets/select_illustratable.py \
  --job "runs/${RATING_JOB_ID:?Enter the completed Rating Job ID first}"
```

Expected files in `configs/datasets/`:

- `illustratable_titles_v1.yaml`: 90 final titles;
- `development_illustratable_titles_v1.yaml`: six separate development titles;
- corresponding `*_sources.csv` reports for both datasets.

Selection uses the four-model mean rating, not reconstruction accuracy. If it
fails, stop here. The rating artifacts are read, not modified.

Path distinction: `runs/JOB_ID` is inside the runner; the same job is at
`$RUN_ROOT/JOB_ID` on the DGX host.

#### Step 4 — Rebuild, then start

The runner image must contain the dataset YAMLs selected for this experiment:

```bash
sudo docker compose --env-file .env \
  -f compose.yaml -f compose.dgx.yaml -f compose.status.yaml \
  --profile runner --profile status build runner
```

After a successful build:

```bash
sudo docker compose --env-file .env \
  -f compose.yaml -f compose.dgx.yaml -f compose.status.yaml \
  --profile runner --profile status run --rm runner \
  semantic-roundtrip job start \
  --config configs/jobs/final_study/direct_illustratable.yaml
```

For another DGX, copy all four generated dataset/report files into its
`configs/datasets/` and rebuild its runner. Reuse this selection; do not rate
again to create a different set. Keep the rating job and generated files together.

### Prompt reconstruction and three-way comparison (SQ1)

SQ1 uses the unrestricted Direct Core source so that prompts, images and
descriptions belong to the same generation condition. The reference adds no
explicit style constraint. Its selection is explained in STUDY_DESIGN.
Different-style route inputs must not be combined.

On an idle model stack, enter the exact completed source Job ID and start SQ1:

```bash
read -r -p "Completed unrestricted Direct Core Job ID: " PROMPT_SOURCE_JOB_ID

sudo docker compose --env-file .env \
  -f compose.yaml -f compose.dgx.yaml -f compose.status.yaml \
  --profile runner --profile status run --rm runner \
  semantic-roundtrip job start \
  --config configs/jobs/final_study/direct_prompt_only.yaml \
  --source-job "direct_base=runs/${PROMPT_SOURCE_JOB_ID:?Enter the exact source Job ID first}"
```

All 16 cells import prompt/image checks and direct predictions. The four
diagonals also import descriptions and indirect predictions. Only 180 prompt
predictions per cell are new (2,880 total). RQ3's reused direct/indirect values
are not independent additional evidence. The whole matrix supplies the
prompt/direct comparison; the three-way comparison uses only the four matched
diagonals. Record the exact source and new Job IDs.

## Analysis and result preservation

On your Mac/analysis machine: Python 3.14 and `uv` must be available. Copy the
seven matching completed job directories for the split, or six for the single
extension, including child runs, from the DGXs,
and first produce the complete style export described below. Replace every
example path before executing:

```bash
export DIRECT_JOB=/absolute/path/to/direct-job
export INDIRECT_JOB=/absolute/path/to/local-indirect-job
unset AQUEDUCT_JOB
export AQUEDUCT_INDEPENDENT_JOB=/absolute/path/to/aqueduct-independent-job
export AQUEDUCT_COMPLETION_JOB=/absolute/path/to/aqueduct-completion-job
export THINKING_JOB=/absolute/path/to/thinking-job
export ILLUSTRATABLE_JOB=/absolute/path/to/illustratable-job
export PROMPT_BASELINE_JOB=/absolute/path/to/prompt-only-job
export STYLE_REPORT_DIR=/absolute/path/to/complete-style-export
export OUTPUT_DIR="$PWD/notebooks/results/final"

uv sync --frozen --extra analysis
uv run jupyter notebook notebooks/final_study.ipynb
```

Do not use reduced style or development jobs as final inputs. Restart the kernel
and use **Run All**. Figures appear inline; 300-dpi PNGs and vector PDFs go to
`OUTPUT_DIR`. Supporting tables and `manifest.json` are exported quietly.
All five other job paths, the complete Aqueduct input and `STYLE_REPORT_DIR`
are required. SQLite inputs are read without modification. For the single-job
alternative, replace the two Aqueduct variables before launching the notebook:

```bash
unset AQUEDUCT_INDEPENDENT_JOB AQUEDUCT_COMPLETION_JOB
export AQUEDUCT_JOB=/absolute/path/to/matching-aqueduct-extension-job
```

Supply exactly one alternative. A missing split half, simultaneous single/split
inputs, overlapping conditions or mismatched source jobs stop the analysis.

Before the final report, produce the sole complete four-style report. Set the unrestricted Direct Core job and
the three matching style jobs, then restart the kernel and use **Run All**:

```bash
export FREE_JOB=/absolute/path/to/direct-core-job
export PHOTOREALISTIC_JOB=/absolute/path/to/photorealistic-job
export COMIC_JOB=/absolute/path/to/comic-job
export SKETCH_JOB=/absolute/path/to/sketch-job
export OUTPUT_DIR="$PWD/notebooks/results/style"

uv run jupyter notebook notebooks/style_decision.ipynb
```

The final report validates the style export's method IDs and hashes, importing
only a compact overview and centrality summary. Detailed matrices and domain
analyses stay in that export. Overall bootstrap intervals retain domain strata;
prompt checks use origin Run/Prompt IDs (720 unique prompts per complete style).

Stored candidate ratings and the completed distribution report are provided in
`artifacts/candidate_illustratability/`, in the Job ID directory and `report/`.
The distribution notebook defaults to the supplied rating job and reproduces
the figure from stored responses without model calls. Its
[README](artifacts/candidate_illustratability/README.md) documents the inputs,
output files, checksums and commands.

### Manual-assessment analysis

The [assessment record](manual_evaluation/verifier_assessment.csv) contains
360 pairs with three explicit labels each. Its [README](manual_evaluation/README.md)
defines the labels, assessor, date and annotation exposure. Reproduce the counts
from the completed Core job's SQLite databases:

```bash
uv run python scripts/evaluate_verifier.py \
  --job /path/to/20260903T230744Z_final-direct-core_faa7afcb
```

The script defaults to the supplied CSV. `--labels <path>` selects another
copy of the same assessment. It checks source identities, fixed seeds and label
completeness, then prints image-policy counts and contextual prompt categories.
Agreement is `(both accept + both reject) / 360`, including missing or invalid
saved decisions in the denominator. It needs no image files or model calls,
writes no reports and leaves labels, decisions and reconstruction scores unchanged.

The completed output has 343/360 Strict and 355/360 Title-aware agreements.
The prompt contexts are 344 absent, eleven normal and five explicit uses.
These are descriptive audit results, not a new scoring policy. The separate
Sketch/Comic adherence checks remain outstanding. Their selection and rubric
are recorded in [STUDY_DESIGN.md](configs/jobs/final_study/STUDY_DESIGN.md#protocol-validation-and-stability).

Source-job identification and download availability are recorded in the
[assessment README](manual_evaluation/README.md).

### Executed HTML report

With the same variables set:

```bash
mkdir -p "$OUTPUT_DIR"
uv run jupyter nbconvert --to notebook --execute \
  notebooks/final_study.ipynb \
  --ExecutePreprocessor.timeout=1200 \
  --output final_study.executed.ipynb \
  --output-dir "$OUTPUT_DIR"

uv run jupyter nbconvert --to html \
  "$OUTPUT_DIR/final_study.executed.ipynb" \
  --output analysis --output-dir "$OUTPUT_DIR"
```

Preserve the ten reconstruction jobs for the split, or nine for the single
extension, plus the rating job, generated datasets/reports, executed
notebook/HTML, PNG/PDF figures, manual evaluation with its validation jobs, status
screenshots and code revision. Keep each result's source identifiers, raw
responses, frozen settings and provenance intact. Expose each Job/Run ID only
once in a website discovery root.

For custom experiments: [`configs/README.md`](configs/README.md). Scientific
settings: [`STUDY_DESIGN.md`](configs/jobs/final_study/STUDY_DESIGN.md). Model-free
quick start: [`README.md`](README.md).
