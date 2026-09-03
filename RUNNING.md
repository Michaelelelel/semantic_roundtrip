# Running Semantic Roundtrip

DGX commands use Bash and run from the repository root. Analysis runs on your
Mac or another analysis machine. DGX jobs and dataset selection need no host `uv`.

## Four-style pilot

These four independent jobs use **90 held-out titles (30 per domain)**, one
prompt seed (`1000`), one image seed (`8566257`) and only direct guessing.
PG and BI are identical within each of the four pairs: Q25/Q25, G3/G3, Q38/Q38,
G4/G4. Each job plans 360 images and direct predictions, not a full 4 x 4 matrix.
All non-style settings and the strict image verifier are shared.

The pilot dataset is already included. The existing main datasets and jobs are
unchanged. Copy the updated project to the DGX and rebuild the runner while the
runtime stack is idle; recreating a container without rebuilding does not copy
new configurations into its image:

```bash
sudo docker compose --env-file .env \
  -f compose.yaml -f compose.dgx.yaml -f compose.status.yaml \
  --profile runner --profile status build runner
```

Use the existing ready model services (see section 3). Run these jobs **one after
another on the same DGX**. Separate DGXs with independent services may run in
parallel. Save each printed job directory. No source-job binding or prior
rating job is needed for reconstruction, and `job plan` is optional.

### Free style

```bash
sudo docker compose --env-file .env \
  -f compose.yaml -f compose.dgx.yaml -f compose.status.yaml \
  --profile runner --profile status run --rm runner \
  semantic-roundtrip job start --config configs/jobs/style_pilot/free.yaml
```

### Sketch

```bash
sudo docker compose --env-file .env \
  -f compose.yaml -f compose.dgx.yaml -f compose.status.yaml \
  --profile runner --profile status run --rm runner \
  semantic-roundtrip job start --config configs/jobs/style_pilot/sketch.yaml
```

### Comic

```bash
sudo docker compose --env-file .env \
  -f compose.yaml -f compose.dgx.yaml -f compose.status.yaml \
  --profile runner --profile status run --rm runner \
  semantic-roundtrip job start --config configs/jobs/style_pilot/comic.yaml
```

### Photorealistic

```bash
sudo docker compose --env-file .env \
  -f compose.yaml -f compose.dgx.yaml -f compose.status.yaml \
  --profile runner --profile status run --rm runner \
  semantic-roundtrip job start --config configs/jobs/style_pilot/photorealistic.yaml
```

### Style and illustratability report

On the analysis machine, supply complete downloaded **job directories**, not
individual child runs or config files. Replace every example path. `RATING_JOB`
is the completed `candidate_illustratability` job with four models rating all
900 candidates; it is not the selected 90-title dataset. Indirect, Aqueduct and
Thinking jobs are not needed in this mode.

```bash
export ANALYSIS_MODE=style_pilot
export FREE_JOB="/absolute/path/to/free-job"
export SKETCH_JOB="/absolute/path/to/sketch-job"
export COMIC_JOB="/absolute/path/to/comic-job"
export PHOTOREALISTIC_JOB="/absolute/path/to/photorealistic-job"
export RATING_JOB="/absolute/path/to/candidate-illustratability-job"
export OUTPUT_DIR="$PWD/notebooks/results/style_pilot"

uv sync --frozen --extra analysis
uv run jupyter notebook notebooks/final_study.ipynb
```

Restart the kernel and run all cells. The same notebook exports strict and
normalized end-to-end accuracy with the same denominator, condition/domain
counts, prompt-title flags, and candidate-rating histograms. Missing predictions
and verifier failures do not disappear from the accuracy denominator. Store the
executed notebook and export it to HTML alongside the CSV/PNG/PDF outputs.
Leave unavailable job variables unset or empty; those sections are explicitly
reported as missing. The rating distribution can run on its own, and available
style jobs can be inspected before the remaining jobs finish. Compare all four
styles only once all four complete jobs are supplied.

The main figures are `style_pilot_accuracy_overall_domains` (strict and
normalized accuracy), `style_pilot_accuracy_diagonal_pairs_domains` (model-pair
breakdown), and `style_pilot_candidate_pool_distribution` (one panel per domain).
Each is saved as PNG and PDF under `OUTPUT_DIR`; CSVs and
`style_pilot_manifest.json` record counts, method versions and input provenance.
Use `ANALYSIS_MODE=full_study` (the default) for the existing full analysis with
its core job paths.

### Reproduce the pilot title selection

The shipped dataset needs no rebuild to start jobs. To reproduce it locally:

```bash
uv run python scripts/datasets/build_style_pilot.py
```

This reads the frozen candidate CSV, excludes the existing random and
high-illustratability final sets, shuffles by domain with seed `20260903` and
keeps one song per primary artist. It writes `style_pilot_titles_v1.yaml`, its
source CSV and JSON provenance manifest under `configs/datasets/`. No network
request, rating or reconstruction score is used. The held-out pool is not the
same population as the unrestricted candidate pool.

The pilot informs a subsequent style choice. It does not establish seed
robustness, mixed PG/BI interactions or a universally best style. Existing full
style supplement jobs are not automatically replaced by this pilot.

## 1. Start here

**Seven reconstruction jobs plus one preparatory rating job.** The random main
dataset (`final_titles_v1.yaml`, 90 titles, no length quotas) is already present.
Do not regenerate it on the DGX.

All job configs are in `configs/jobs/final_study/`:

| Job config | Required before starting |
| --- | --- |
| `direct_core.yaml` | services ready; main dataset already present |
| `indirect_local.yaml` | services ready; main dataset already present |
| `direct_sketch.yaml` | services ready; main dataset already present |
| `direct_comic.yaml` | services ready; main dataset already present |
| `direct_thinking.yaml` | exact completed `direct_core` job |
| `aqueduct_v4_extension.yaml` | exact completed `indirect_local` job and API key |
| `direct_illustratable.yaml` | rating job → dataset selection → runner rebuild |

Only the illustratability supplement needs the rating job; the other six do not.

- New DGX: [one-time setup](#2-one-time-dgx-setup).
- Existing DGX: [services and shell setup](#3-services-and-shell-setup).
- Ready to run: [study jobs](#4-run-the-study-jobs).
- Running already: [monitor or resume](#5-monitor-and-resume).
- Optional checks: [smokes and previews](#6-optional-deployment-validation).
- Completed jobs: [analysis and archive](#7-analyze-and-archive).

Run **one model job at a time per DGX/shared runtime stack**. Independent DGXs
can run in parallel; use the same study code/config revision on both. Do not
restart services while a job is running.

## 2. One-time DGX setup

Skip if the repository, `.env` and models are already present. Docker Compose
and NVIDIA container support must be installed on the host.

### Repository and storage

```bash
git clone https://github.com/Michaelelelel/semantic_roundtrip.git
cd semantic_roundtrip
cp .env.example .env

DATA_ROOT="$HOME/bachelorthesis/semantic_roundtrip-data"
mkdir -p \
  "$DATA_ROOT/models" \
  "$DATA_ROOT/runs" \
  "$DATA_ROOT/runtime/comfyui/mnt" \
  "$DATA_ROOT/runtime/comfyui/base"

id -u
id -g
```

Fill `.env` with your own IDs and absolute paths; replace these example values.
Keep an existing `.env`. Set the Aqueduct key for hosted jobs, otherwise leave it
empty. `.env` is ignored by Git; never commit credentials.

```dotenv
HOST_UID=1002
HOST_GID=1002
MODEL_ROOT=/home/user/bachelorthesis/semantic_roundtrip-data/models
RUN_ROOT=/home/user/bachelorthesis/semantic_roundtrip-data/runs
RUNTIME_ROOT=/home/user/bachelorthesis/semantic_roundtrip-data/runtime
STATUS_PORT=18000
AQUEDUCT_API_KEY=
```

### Model downloads

SD3.5 Large requires access to its
[Hugging Face repository](https://huggingface.co/stabilityai/stable-diffusion-3.5-large).
The scripts pin revisions, verify checksums and skip matching files. Install the
download helper only in your user directory:

```bash
python3 -m venv "$HOME/.venvs/hf-download"
"$HOME/.venvs/hf-download/bin/python" -m pip install --upgrade \
  pip huggingface_hub hf_xet

set -a
. ./.env
set +a
```

Read the token without putting it in shell history:

```bash
read -rsp "Hugging Face token: " HF_TOKEN
```

After entering the token:

```bash
export HF_TOKEN
HF_XET_HIGH_PERFORMANCE=1 \
  ./models/download-final-study.sh "$MODEL_ROOT"
unset HF_TOKEN
```

## 3. Services and shell setup

### Once per terminal or tmux window

Enter the repository directory. Load `.env` so hosted commands can forward the
Aqueduct key from this shell:

```bash
set -a
. ./.env
set +a
```

All Docker Compose commands are written out in full; no shell helpers are needed.
Hosted commands preserve the key through `sudo` and pass it with
`-e AQUEDUCT_API_KEY`. Using all three Compose files avoids the `status_web` orphan
warning; do not use `--remove-orphans`.

### Update, build and start

While the DGX is idle, use the intended study checkout. On a development branch,
update with `git pull --ff-only`; keep frozen runs on their selected commit/tag.
Inspect local changes rather than discarding them.

```bash
git status --short
git rev-parse HEAD

sudo docker compose --env-file .env \
  -f compose.yaml -f compose.dgx.yaml -f compose.status.yaml \
  --profile runner --profile status config --quiet

sudo docker compose --env-file .env \
  -f compose.yaml -f compose.dgx.yaml -f compose.status.yaml \
  --profile runner --profile status build runner status_web

sudo docker compose --env-file .env \
  -f compose.yaml -f compose.dgx.yaml -f compose.status.yaml \
  --profile runner --profile status up -d --force-recreate --wait \
  text_runtime vision_runtime image_runtime status_web

sudo docker compose --env-file .env \
  -f compose.yaml -f compose.dgx.yaml -f compose.status.yaml \
  --profile runner --profile status ps
```

Rebuild after code/config changes: files are copied into the images.
`--force-recreate` alone does not rebuild them. Old job snapshots remain unchanged.

| Service | Purpose |
| --- | --- |
| `text_runtime` | llama.cpp for text-only stages |
| `vision_runtime` | llama.cpp with the matching image projector |
| `image_runtime` | ComfyUI and SD3.5 image generation |
| `status_web` | read-only job/run website |

Services start without preloading models. The runner loads/unloads models by
stage. Once services are healthy, choose a job below.

## 4. Run the study jobs

`job start` validates, creates a new snapshot and runs in the foreground. Save
its printed **Job ID** for source bindings and analysis. Use `resume`, not a new
`start`, for an interrupted job. `job plan` is optional: replace `start` with
`plan` and keep the same config/source arguments to inspect work without running it.

### A. Start without a source job

Prerequisite: services ready. These jobs use the existing main dataset and can
run in any order. Choose one command; wait before starting another on the same DGX.

#### Direct core

```bash
sudo docker compose --env-file .env \
  -f compose.yaml -f compose.dgx.yaml -f compose.status.yaml \
  --profile runner --profile status run --rm runner \
  semantic-roundtrip job start \
  --config configs/jobs/final_study/direct_core.yaml
```

#### Local indirect

```bash
sudo docker compose --env-file .env \
  -f compose.yaml -f compose.dgx.yaml -f compose.status.yaml \
  --profile runner --profile status run --rm runner \
  semantic-roundtrip job start \
  --config configs/jobs/final_study/indirect_local.yaml
```

#### Sketch

```bash
sudo docker compose --env-file .env \
  -f compose.yaml -f compose.dgx.yaml -f compose.status.yaml \
  --profile runner --profile status run --rm runner \
  semantic-roundtrip job start \
  --config configs/jobs/final_study/direct_sketch.yaml
```

#### Comic

```bash
sudo docker compose --env-file .env \
  -f compose.yaml -f compose.dgx.yaml -f compose.status.yaml \
  --profile runner --profile status run --rm runner \
  semantic-roundtrip job start \
  --config configs/jobs/final_study/direct_comic.yaml
```

### B. Reuse a completed source job

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

#### Thinking

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

#### Aqueduct

Needs the API key loaded from `.env` in section 3 and the completed Local Indirect
Job ID:

```bash
read -r -p "Completed final_indirect_local Job ID: " INDIRECT_JOB_ID
```

Then start the extension:

```bash
sudo --preserve-env=AQUEDUCT_API_KEY docker compose --env-file .env \
  -f compose.yaml -f compose.dgx.yaml -f compose.status.yaml \
  --profile runner --profile status run --rm -e AQUEDUCT_API_KEY runner \
  semantic-roundtrip job start \
  --config configs/jobs/final_study/aqueduct_v4_extension.yaml \
  --source-job "local_indirect=runs/${INDIRECT_JOB_ID:?Enter the Local Indirect Job ID first}"
```

### C. Illustratability: create its dataset first

This supplementary dataset does not replace the random main dataset. Its
900-candidate pool is already present. Four models rate each candidate once:
3,600 planned ratings, no image generation.

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

The runner image must contain the newly generated YAMLs:

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

## 5. Monitor and resume

Use another terminal/tmux window from the repository root. Read-only status
commands may run alongside a model job.

`job list` and `run list` print compact summaries with full, copyable IDs.
Add `--status completed` to list only completed jobs or runs. Use `job status`
or `run status` for detailed progress and timestamps.

```bash
sudo docker compose --env-file .env \
  -f compose.yaml -f compose.dgx.yaml -f compose.status.yaml \
  --profile runner --profile status run --rm runner \
  semantic-roundtrip job list --root runs

sudo docker compose --env-file .env \
  -f compose.yaml -f compose.dgx.yaml -f compose.status.yaml \
  --profile runner --profile status run --rm runner \
  semantic-roundtrip run list --root runs

sudo docker compose --env-file .env \
  -f compose.yaml -f compose.dgx.yaml -f compose.status.yaml \
  --profile runner --profile status ps

sudo docker compose --env-file .env \
  -f compose.yaml -f compose.dgx.yaml -f compose.status.yaml \
  --profile runner --profile status logs --tail=100 --follow
```

Choose an existing Job ID:

```bash
read -r -p "Existing Job ID: " JOB_ID
```

Run only the operation you need:

```bash
sudo docker compose --env-file .env \
  -f compose.yaml -f compose.dgx.yaml -f compose.status.yaml \
  --profile runner --profile status run --rm runner \
  semantic-roundtrip job status \
  --job "runs/${JOB_ID:?Enter a Job ID first}" --watch 5

sudo docker compose --env-file .env \
  -f compose.yaml -f compose.dgx.yaml -f compose.status.yaml \
  --profile runner --profile status run --rm runner \
  semantic-roundtrip job pause \
  --job "runs/${JOB_ID:?Enter a Job ID first}"

sudo docker compose --env-file .env \
  -f compose.yaml -f compose.dgx.yaml -f compose.status.yaml \
  --profile runner --profile status run --rm runner \
  semantic-roundtrip job resume \
  --job "runs/${JOB_ID:?Enter a Job ID first}"
```

For hosted resume, load `.env` as in section 3, use
`sudo --preserve-env=AQUEDUCT_API_KEY` and put `-e AQUEDUCT_API_KEY` before `runner`.
Source bindings are already saved; do not select them again. Pause lets the current
request finish; `Ctrl+C` requests a safe interruption. Resume skips completed
child runs.
Individual terminal task failures remain recorded results.

Already in tmux? No setup needed. Otherwise use `tmux new -A -s study`. Detach with
`Ctrl+B`, then `D`; the job keeps running.

### Status website

On the DGX: `http://127.0.0.1:$STATUS_PORT`. From your Mac, open a tunnel in another
terminal; replace the example login/host and port with your DGX values:

```bash
ssh -N -L 8000:127.0.0.1:18000 user@dgx-host
```

Open `http://127.0.0.1:8000` locally. Use another local port for a second DGX.

## 6. Optional deployment validation

Smokes and previews check deployment with the fixed profiles. They are not final
study inputs and do not tune settings from reconstruction accuracy.

### Local smoke

```bash
sudo docker compose --env-file .env \
  -f compose.yaml -f compose.dgx.yaml -f compose.status.yaml \
  --profile runner --profile status run --rm runner \
  semantic-roundtrip job start \
  --config configs/jobs/final_study/smoke_local.yaml
```

### Aqueduct smoke

Needs the API key loaded from `.env` in section 3.

```bash
sudo --preserve-env=AQUEDUCT_API_KEY docker compose --env-file .env \
  -f compose.yaml -f compose.dgx.yaml -f compose.status.yaml \
  --profile runner --profile status run --rm -e AQUEDUCT_API_KEY runner \
  semantic-roundtrip job start \
  --config configs/jobs/final_study/smoke_aqueduct.yaml
```

### Direct preview

These previews use six titles. As with final jobs, run only one at a time per DGX.

```bash
sudo docker compose --env-file .env \
  -f compose.yaml -f compose.dgx.yaml -f compose.status.yaml \
  --profile runner --profile status run --rm runner \
  semantic-roundtrip job start \
  --config configs/jobs/final_study/development_direct_preview.yaml
```

### Local indirect preview

```bash
sudo docker compose --env-file .env \
  -f compose.yaml -f compose.dgx.yaml -f compose.status.yaml \
  --profile runner --profile status run --rm runner \
  semantic-roundtrip job start \
  --config configs/jobs/final_study/development_indirect_preview.yaml
```

### Sketch preview

```bash
sudo docker compose --env-file .env \
  -f compose.yaml -f compose.dgx.yaml -f compose.status.yaml \
  --profile runner --profile status run --rm runner \
  semantic-roundtrip job start \
  --config configs/jobs/final_study/development_direct_sketch_preview.yaml
```

### Comic preview

```bash
sudo docker compose --env-file .env \
  -f compose.yaml -f compose.dgx.yaml -f compose.status.yaml \
  --profile runner --profile status run --rm runner \
  semantic-roundtrip job start \
  --config configs/jobs/final_study/development_direct_comic_preview.yaml
```

### Thinking preview

Use the exact completed **Direct preview**, not a final job. Find its Job ID with
the job-list command in section 5, then enter it:

```bash
read -r -p "Completed development_direct_preview Job ID: " DIRECT_PREVIEW_JOB_ID
```

After entering the ID:

```bash
sudo docker compose --env-file .env \
  -f compose.yaml -f compose.dgx.yaml -f compose.status.yaml \
  --profile runner --profile status run --rm runner \
  semantic-roundtrip job start \
  --config configs/jobs/final_study/development_direct_thinking_preview.yaml \
  --source-job "direct_base=runs/${DIRECT_PREVIEW_JOB_ID:?Enter the Direct preview Job ID first}"
```

### Aqueduct preview

Needs the API key and the exact completed **Local Indirect preview**, not a final
job. Find its Job ID with the job-list command in section 5, then enter it:

```bash
read -r -p "Completed development_indirect_preview Job ID: " INDIRECT_PREVIEW_JOB_ID
```

After entering the ID:

```bash
sudo --preserve-env=AQUEDUCT_API_KEY docker compose --env-file .env \
  -f compose.yaml -f compose.dgx.yaml -f compose.status.yaml \
  --profile runner --profile status run --rm -e AQUEDUCT_API_KEY runner \
  semantic-roundtrip job start \
  --config configs/jobs/final_study/development_aqueduct_preview.yaml \
  --source-job "local_indirect=runs/${INDIRECT_PREVIEW_JOB_ID:?Enter the Local Indirect preview Job ID first}"
```

### Illustratability preview

Prerequisite: finish the rating job, dataset selection and runner rebuild from
section 4C. The selector already creates this six-title dataset; no second rating
job is needed.

```bash
sudo docker compose --env-file .env \
  -f compose.yaml -f compose.dgx.yaml -f compose.status.yaml \
  --profile runner --profile status run --rm runner \
  semantic-roundtrip job start \
  --config configs/jobs/final_study/development_direct_illustratable_preview.yaml
```

Manual verifier and style checks:
[`manual_evaluation/README.md`](manual_evaluation/README.md).

## 7. Analyze and archive

On your Mac/analysis machine: Python 3.14 and `uv` must be available. Copy the
seven matching completed job directories, including child runs, from the DGXs.
Run from the repository root and replace all seven example paths before executing:

```bash
export DIRECT_JOB=/absolute/path/to/direct-job
export INDIRECT_JOB=/absolute/path/to/local-indirect-job
export AQUEDUCT_JOB=/absolute/path/to/matching-aqueduct-job
export SKETCH_JOB=/absolute/path/to/sketch-job
export COMIC_JOB=/absolute/path/to/comic-job
export THINKING_JOB=/absolute/path/to/thinking-job
export ILLUSTRATABLE_JOB=/absolute/path/to/illustratable-job
export OUTPUT_DIR="$PWD/notebooks/results/final"

uv sync --frozen --extra analysis
uv run jupyter notebook notebooks/final_study.ipynb
```

For notebook validation, use matching previews instead; do not mix them with final
jobs. Restart the kernel and use **Run All**. Tables/figures appear inline; 300-dpi
PNGs and vector PDFs go to `OUTPUT_DIR`. SQLite inputs are read without modification.

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

Archive the seven final jobs, rating job, generated datasets/reports, executed
notebook/HTML, PNG/PDF figures, manual evaluation with its validation jobs, status
screenshots and code revision. Keep old runs unchanged.

For custom experiments: [`configs/README.md`](configs/README.md). Scientific
settings: [`STUDY_DESIGN.md`](configs/jobs/final_study/STUDY_DESIGN.md). Model-free
quick start: [`README.md`](README.md).
