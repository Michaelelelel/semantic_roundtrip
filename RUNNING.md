# Setup and operation

Shared installation and CLI instructions. Choose the experiment guide separately:

- [EXPERIMENTS.md](EXPERIMENTS.md): reproduce the main, four-style and
  supplementary thesis experiments.

DGX commands use Bash and run from the repository root. Analysis runs on your
Mac or another analysis machine. DGX jobs and dataset selection need no host `uv`.

- [Install once](#one-time-dgx-setup).
- [Load the environment and start services](#services-and-shell-setup).
- [Monitor, pause or resume](#monitor-and-resume).
- [Optional smokes and six-title previews](#optional-deployment-validation).

Run one model job at a time per DGX/shared runtime stack. Independent DGXs may
run in parallel. Read-only status commands may run alongside model jobs.
Do not restart services while a job is running.

## One-time DGX setup

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

## Services and shell setup

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

`RUN_ROOT` in `.env` selects the persistent host directory for jobs and the
website. If you deliberately override it in the shell, preserve that override
through every Compose command with `sudo --preserve-env=RUN_ROOT`; for hosted
commands use `sudo --preserve-env=RUN_ROOT,AQUEDUCT_API_KEY`. Otherwise `sudo`
may select a different run directory. Record the non-secret storage path with
the deployment; never print `.env` values or credentials.

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
`--force-recreate` alone does not rebuild them. Existing job snapshots remain unchanged.

For a **website-only update while a job is running**, copy the updated code and
run this in a second terminal. It rebuilds and recreates only `status_web`;
the runner and model services keep running. Then reload the browser.
This applies only to updates compatible with the active database/configuration
format. Do not deploy changes to a running job's pipeline, model services or
stored format.

```bash
sudo docker compose --env-file .env \
  -f compose.yaml -f compose.dgx.yaml -f compose.status.yaml \
  --profile status \
  up -d --build --no-deps --force-recreate --wait status_web
```

| Service | Purpose |
| --- | --- |
| `text_runtime` | llama.cpp for text-only stages |
| `vision_runtime` | llama.cpp with the matching image projector |
| `image_runtime` | ComfyUI and SD3.5 image generation |
| `status_web` | read-only job/run website |

Services start without preloading models. The runner loads/unloads models by
stage. Once services are healthy, continue with
[the thesis experiments](EXPERIMENTS.md).

The local llama.cpp routers and model workers use a 9,000-second transport
timeout, above the longest configured client timeout of 7,200 seconds. Backend
profiles retain their shorter request timeouts and token limits. Apply changes
to model-service startup options only while the shared stack is idle.

## Run storage and reproducibility

The application uses experiment/snapshot format 11, Run DB 12, Job
YAML/snapshot 5, Job DB 4 and manifest 6. The CLI, website and analysis require
these formats. Use the selected study revision consistently across hosts and
resume jobs with their frozen configurations and compatible software.

The runner's `runs/JOB_ID` refers to `$RUN_ROOT/JOB_ID` on the host. Copy a
completed job as a complete directory, including its child runs, databases,
images, profiles and provenance. Keep source identifiers and timestamps intact.
Expose each Job/Run ID only once in a website discovery root.

Analysis reads stored responses; it does not repeat model inference. Preserve
the input jobs, code revision, executed notebooks, result tables, figures and
manifests together. The experiment-specific prerequisites and common-style
confirmation are described in [EXPERIMENTS.md](EXPERIMENTS.md).

## Monitor and resume

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

For hosted resume, load `.env` as in [shell setup](#once-per-terminal-or-tmux-window), use
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

`View results` shows all configured reconstruction routes in one table,
including prompt-only runs. When a prompt has several images, its Prompt route
answer appears with each image but counts only once in Prompt accuracy.

## Optional deployment validation

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

Needs the API key loaded from `.env` in [shell setup](RUNNING.md#once-per-terminal-or-tmux-window).

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
the [job-list command](#monitor-and-resume), then enter it:

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
job. Find its Job ID with the [job-list command](#monitor-and-resume), then enter it:

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
[the illustratability instructions](EXPERIMENTS.md#illustratable-dataset). The selector already creates this six-title dataset; no second rating
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

For custom experiments, see [configs/README.md](configs/README.md).
