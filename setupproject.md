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

## 4. Start the DGX runtimes

Start the three model runtimes:

```bash
sudo docker compose \
  -f compose.yaml \
  -f compose.dgx.yaml \
  up -d --wait \
  text_runtime vision_runtime image_runtime
```

## 5. Test the final-study models

The complete final-study bundle requires roughly 390 GB of model storage. Keep at
least another 50 GB free while a large `.part` file is being downloaded. Check
the available space first:

```bash
df -h "$DATA_ROOT"
```

Stable Diffusion 3.5 Large is gated; accept its model licence on Hugging Face and
export a read token before downloading:

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

Plan and run the small native-precision smoke job first. It creates six images
and loads every model family used by the two primary jobs:

```bash
sudo docker compose -f compose.yaml -f compose.dgx.yaml run --rm runner \
  semantic-roundtrip job plan \
  --config configs/jobs/final_study/native_smoke.yaml

sudo docker compose -f compose.yaml -f compose.dgx.yaml run --rm runner \
  semantic-roundtrip job start \
  --config configs/jobs/final_study/native_smoke.yaml
```

Only after all smoke entries work, start one primary job on each DGX Spark.

Spark A:

```bash
sudo docker compose -f compose.yaml -f compose.dgx.yaml run --rm runner \
  semantic-roundtrip job plan \
  --config configs/jobs/final_study/spark_a_system_image.yaml

sudo docker compose -f compose.yaml -f compose.dgx.yaml run --rm runner \
  semantic-roundtrip job start \
  --config configs/jobs/final_study/spark_a_system_image.yaml
```

Spark B:

```bash
sudo docker compose -f compose.yaml -f compose.dgx.yaml run --rm runner \
  semantic-roundtrip job plan \
  --config configs/jobs/final_study/spark_b_prompt_vision_route.yaml

sudo docker compose -f compose.yaml -f compose.dgx.yaml run --rm runner \
  semantic-roundtrip job start \
  --config configs/jobs/final_study/spark_b_prompt_vision_route.yaml
```

Every experiment executes a complete independent run. Scientific comparisons
are selected separately in a `study.yaml` file; job membership does not define
what is compared.

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

## 7. Analyze selected completed runs

Create one study directory below `RUN_ROOT`, copy the example, and replace its run
placeholders. Paths in `study.yaml` are relative to the study directory and can
point to child runs from different jobs.

```bash
mkdir -p "$RUN_ROOT/final-study"
cp configs/studies/final_study.example.yaml \
  "$RUN_ROOT/final-study/study.yaml"

${EDITOR:-nano} "$RUN_ROOT/final-study/study.yaml"

sudo docker compose -f compose.yaml run --rm runner \
  semantic-roundtrip study analyze --study runs/final-study
```

The command reads completed run databases without modifying them. Tables, figures,
the study snapshot, and the manifest are written to `final-study/results/`. Add
`--force` only when you intentionally want to replace those results.

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
