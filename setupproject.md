# Project setup and smoke tests

## 1. One-time DGX setup

From the repository root:

```bash
DATA_ROOT="$HOME/bachelorthesis/semantic_roundtrip-data"

mkdir -p \
  "$DATA_ROOT/models/text" \
  "$DATA_ROOT/models/image/checkpoints" \
  "$DATA_ROOT/models/vision" \
  "$DATA_ROOT/runs" \
  "$DATA_ROOT/runtime/comfyui/mnt" \
  "$DATA_ROOT/runtime/comfyui/base"

cp .env.example .env
```

Set your own values in `.env`:

```dotenv
HOST_UID=1002
HOST_GID=1002
MODEL_ROOT=/home/mhagmann/bachelorthesis/semantic_roundtrip-data/models
RUN_ROOT=/home/mhagmann/bachelorthesis/semantic_roundtrip-data/runs
RUNTIME_ROOT=/home/mhagmann/bachelorthesis/semantic_roundtrip-data/runtime
STATUS_PORT=18000
```

Download the currently configured baseline models and chat templates:

```bash
./chat_templates/download.sh
./models/text/download.sh "$DATA_ROOT/models"
./models/vision/download.sh "$DATA_ROOT/models"
./models/image/download-stable-diffusion-v1-5-fp16.sh "$DATA_ROOT/models"
```

## 2. Build the runner

Rebuild after pulling code changes:

```bash
sudo docker compose -f compose.yaml build runner
```

## 3. Test without models

Run the complete mock pipeline:

```bash
sudo docker compose -f compose.yaml run --rm runner \
  semantic-roundtrip run start \
  --config configs/experiments/mock.yaml
```

Test a job containing two mock runs:

```bash
sudo docker compose -f compose.yaml run --rm runner \
  semantic-roundtrip job plan \
  --config configs/jobs/mock.yaml

sudo docker compose -f compose.yaml run --rm runner \
  semantic-roundtrip job start \
  --config configs/jobs/mock.yaml
```

## 4. Test the real DGX pipeline

Start the three model runtimes:

```bash
sudo docker compose \
  -f compose.yaml \
  -f compose.dgx.yaml \
  up -d --wait \
  text_runtime vision_runtime image_runtime
```

Run the one-item DGX smoke test:

```bash
sudo docker compose \
  -f compose.yaml \
  -f compose.dgx.yaml \
  run --rm runner \
  semantic-roundtrip run start \
  --config configs/experiments/dgx_smoke.yaml
```

The smoke test exercises prompt generation, image generation, verification, image
description, and both title-reconstruction routes. It is not a scientific experiment.

## 5. Inspect progress

List runs or jobs when you do not know their IDs:

```bash
sudo docker compose -f compose.yaml run --rm runner \
  semantic-roundtrip run list

sudo docker compose -f compose.yaml run --rm runner \
  semantic-roundtrip job list
```

Copy a printed ID and inspect it:

```bash
RUN_ID=<run-id>
JOB_ID=<job-id>

sudo docker compose -f compose.yaml run --rm runner \
  semantic-roundtrip run status --run "runs/$RUN_ID" --watch 1

sudo docker compose -f compose.yaml run --rm runner \
  semantic-roundtrip job status --job "runs/$JOB_ID" --watch 1
```

Start the read-only status website:

```bash
sudo docker compose \
  -f compose.yaml \
  -f compose.status.yaml \
  --profile status \
  up -d --build --wait status_web
```

On the DGX, open `http://127.0.0.1:$STATUS_PORT`. From another computer, use an
SSH tunnel to that localhost port.

## 6. Export finished results

Run the analysis only after the selected run or job has finished:

```bash
sudo docker compose -f compose.yaml run --rm runner \
  semantic-roundtrip run evaluate --run "runs/$RUN_ID"

sudo docker compose -f compose.yaml run --rm runner \
  semantic-roundtrip job evaluate --job "runs/$JOB_ID"
```

The CSV files, manifest, and figures are written to the selected directory's
`analysis/` folder. Add `--force` only when you intentionally want to replace it.

## 7. Test pause and resume

Start `configs/experiments/mock_pause.yaml` in one terminal. In a second terminal,
copy its ID from `run list`, then pause and resume it:

```bash
sudo docker compose -f compose.yaml run --rm runner \
  semantic-roundtrip run pause --run "runs/$RUN_ID"

sudo docker compose -f compose.yaml run --rm runner \
  semantic-roundtrip run resume --run "runs/$RUN_ID"
```

Use `configs/jobs/mock_pause.yaml` in the same way to test job-level pause and resume.

## 8. Stop everything

Run artifacts remain in `RUN_ROOT`.

```bash
sudo docker compose \
  -f compose.yaml \
  -f compose.dgx.yaml \
  -f compose.status.yaml \
  --profile status \
  down --remove-orphans
```

## 9. Copy results to the local computer

```bash
rsync -avz --progress \
  mhagmann@128.130.58.152:~/bachelorthesis/semantic_roundtrip-data/runs/ \
  /Users/michaelhagmann/uni/Bachelor/bachelor_runs_from_dgx/
```

The repository intentionally contains no final DGX study job yet. Final stack
experiments and jobs are added only after every selected model has passed the smoke
test and the scientific settings have been reviewed.
