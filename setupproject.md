# Project setup and smoke tests

## 1. One-time DGX setup

From the repository root:

```bash
DATA_ROOT="$HOME/bachelorthesis/semantic_roundtrip-data"

mkdir -p \
  "$DATA_ROOT/models/text" \
  "$DATA_ROOT/models/multimodal" \
  "$DATA_ROOT/models/image/checkpoints" \
  "$DATA_ROOT/models/image/diffusion_models" \
  "$DATA_ROOT/models/image/text_encoders" \
  "$DATA_ROOT/models/image/vae" \
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
./models/text/download-mistral-7b-instruct-v0.1-q4_k_m.sh "$DATA_ROOT/models"
./models/vision/download-llava-v1.5-7b-q4_k.sh "$DATA_ROOT/models"
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

To run the initial engineering smoke for the legacy and intermediate Qwen3 stacks,
download their model bundle and execute both one-item checks as one sequential job.
This verifies integration only; it is not a scientific stack comparison:

```bash
./models/download-dgx-initial-stack-smoke.sh "$DATA_ROOT/models"

sudo docker compose \
  -f compose.yaml \
  -f compose.dgx.yaml \
  run --rm runner \
  semantic-roundtrip job start \
  --config configs/jobs/dgx_initial_stack_smoke.yaml
```

## 5. Test the complete model matrix

The complete S0-S4 bundle requires roughly 390 GB of final model storage. Keep at
least another 50 GB free while a large `.part` file is being downloaded. Check the
available space first:

```bash
df -h "$DATA_ROOT"
```

Stable Diffusion 3.5 Large is gated; accept its model licence on Hugging Face and
export a read token before downloading. The FLUX.2 dev FP8-mixed artifact is public,
but its non-commercial model licence still applies:

```bash
export HF_TOKEN=<your-hugging-face-read-token>
./models/download-dgx-final-matrix.sh "$DATA_ROOT/models"
```

Recreate the runtimes so llama.cpp reads the expanded model catalog and the shared
multimodal mount:

```bash
sudo docker compose \
  -f compose.yaml \
  -f compose.dgx.yaml \
  up -d --force-recreate --wait \
  text_runtime vision_runtime image_runtime
```

Plan and run one image through every complete stack first:

```bash
sudo docker compose -f compose.yaml -f compose.dgx.yaml run --rm runner \
  semantic-roundtrip job plan \
  --config configs/jobs/dgx_final_matrix_smoke.yaml

sudo docker compose -f compose.yaml -f compose.dgx.yaml run --rm runner \
  semantic-roundtrip job start \
  --config configs/jobs/dgx_final_matrix_smoke.yaml
```

Only after all required smoke entries work, start the shared six-title development
matrix. It contains S0-S4 plus the bounded S1 self/cross route comparison:

```bash
sudo docker compose -f compose.yaml -f compose.dgx.yaml run --rm runner \
  semantic-roundtrip job plan \
  --config configs/jobs/dgx_final_matrix_development.yaml

sudo docker compose -f compose.yaml -f compose.dgx.yaml run --rm runner \
  semantic-roundtrip job start \
  --config configs/jobs/dgx_final_matrix_development.yaml
```

The development job produces 144 images and 288 evaluation rows. Copy its printed
job ID, then analyze all child runs together:

```bash
JOB_ID=<development-job-id>

sudo docker compose -f compose.yaml run --rm runner \
  semantic-roundtrip job evaluate \
  --job "runs/$JOB_ID"
```

## 6. Inspect progress

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
  up -d --build --force-recreate --wait status_web
```

Rebuilding and recreating the website is required after a database-schema change so
the web container and the runner use the same installed project version.

On the DGX, open `http://127.0.0.1:$STATUS_PORT`. From another computer, use an
SSH tunnel to that localhost port.

## 7. Export finished results

Run the analysis only after the selected run or job has finished:

```bash
sudo docker compose -f compose.yaml run --rm runner \
  semantic-roundtrip run evaluate --run "runs/$RUN_ID"

sudo docker compose -f compose.yaml run --rm runner \
  semantic-roundtrip job evaluate --job "runs/$JOB_ID"
```

The CSV files, manifest, and figures are written to the selected directory's
`analysis/` folder. Add `--force` only when you intentionally want to replace it.

## 8. Test pause and resume

Start `configs/experiments/mock_pause.yaml` in one terminal. In a second terminal,
copy its ID from `run list`, then pause and resume it:

```bash
sudo docker compose -f compose.yaml run --rm runner \
  semantic-roundtrip run pause --run "runs/$RUN_ID"

sudo docker compose -f compose.yaml run --rm runner \
  semantic-roundtrip run resume --run "runs/$RUN_ID"
```

Use `configs/jobs/mock_pause.yaml` in the same way to test job-level pause and resume.

## 9. Stop everything

Run artifacts remain in `RUN_ROOT`.

```bash
sudo docker compose \
  -f compose.yaml \
  -f compose.dgx.yaml \
  -f compose.status.yaml \
  --profile status \
  down --remove-orphans
```

## 10. Copy results to the local computer

```bash
rsync -avz --progress \
  mhagmann@128.130.58.152:~/bachelorthesis/semantic_roundtrip-data/runs/ \
  /Users/michaelhagmann/uni/Bachelor/bachelor_runs_from_dgx/
```

The development matrix is not final thesis evidence. Review its raw outputs and
analysis before freezing separate pilot and final-title jobs.

S4 is intentionally a stretch stack. The full FLUX.2 BF16 workflow exceeded the
memory available on one 128 GB DGX Spark, so S4 uses the official FP8-mixed FLUX.2
dev artifact with its BF16 text encoder. Qualify it with the one-image smoke before
including it in a longer job. A failed S4 entry does not stop the other entries
because both matrix jobs use `continue_on_error: true`.
