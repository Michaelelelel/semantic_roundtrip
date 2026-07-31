# Project Setup and Demo

## 1. One-time DGX setup

Create persistent directories outside the repository:

```bash
DATA_ROOT="$HOME/bachelorthesis/semantic_roundtrip-data"

mkdir -p \
  "$DATA_ROOT/models/text" \
  "$DATA_ROOT/models/image/checkpoints" \
  "$DATA_ROOT/models/vision" \
  "$DATA_ROOT/runs" \
  "$DATA_ROOT/runtime/comfyui/mnt" \
  "$DATA_ROOT/runtime/comfyui/base"
```

Create the local environment file:

```bash
cp .env.example .env
```

Enter your IDs and absolute directories:

```dotenv
HOST_UID=1002
HOST_GID=1002
MODEL_ROOT=/home/mhagmann/bachelorthesis/semantic_roundtrip-data/models
RUN_ROOT=/home/mhagmann/bachelorthesis/semantic_roundtrip-data/runs
RUNTIME_ROOT=/home/mhagmann/bachelorthesis/semantic_roundtrip-data/runtime
```

Download the currently configured models:

```bash
./chat_templates/download.sh
./models/text/download.sh "$DATA_ROOT/models"
./models/vision/download.sh "$DATA_ROOT/models"
./models/image/download.sh "$DATA_ROOT/models"
```

## 2. Build the runner

Rebuild after a `git pull` or code change:

```bash
sudo docker compose -f compose.yaml build runner
```

## 3. MOCK without MODELS

Run one mock experiment:

```bash
sudo docker compose -f compose.yaml run --rm runner \
  semantic-roundtrip run start \
  --config configs/experiments/mock.yaml
```

Run a mock job containing two experiments:

```bash
sudo docker compose -f compose.yaml run --rm runner \
  semantic-roundtrip job start \
  --config configs/jobs/mock.yaml
```

## 4. Start the DGX model services

```bash
sudo docker compose \
  -f compose.yaml \
  -f compose.dgx.yaml \
  up -d --wait \
  text_runtime vision_runtime image_runtime
```

## 5. Plan the DGX demo job

```bash
sudo docker compose \
  -f compose.yaml \
  -f compose.dgx.yaml \
  run --rm runner \
  semantic-roundtrip job plan \
  --config configs/jobs/dgx_serial_benchmark.yaml
```

## 6. Run the DGX demo job

```bash
sudo docker compose \
  -f compose.yaml \
  -f compose.dgx.yaml \
  run --rm runner \
  semantic-roundtrip job start \
  --config configs/jobs/dgx_serial_benchmark.yaml
```

```text
runs/20260725T120000Z_dgx-serial-benchmark_12345678
```

In terminal 2, store only the printed job ID:

```bash
JOB_ID=20260725T120000Z_dgx-serial-benchmark_12345678
```

Show the complete job and all child-run states:

```bash
sudo docker compose -f compose.yaml run --rm runner \
  semantic-roundtrip job status \
  --job "runs/$JOB_ID" \
  --watch 1
```

```bash
CHILD_RUN_ID=20260725T120001Z_imagine-matrix_abcdefgh
```

```bash
sudo docker compose -f compose.yaml run --rm runner \
  semantic-roundtrip run status \
  --run "runs/$JOB_ID/runs/$CHILD_RUN_ID" \
  --watch 1
```

## 7. Pause and resume

```bash
sudo docker compose -f compose.yaml run --rm runner \
  semantic-roundtrip job pause \
  --job "runs/$JOB_ID"
  
```

```bash
sudo docker compose -f compose.yaml run --rm runner \
  semantic-roundtrip job status \
  --job "runs/$JOB_ID"
```

```bash
sudo docker compose -f compose.yaml run --rm runner \
  semantic-roundtrip run status \
  --run "runs/$JOB_ID/runs/$CHILD_RUN_ID"
```

```bash
sudo docker compose \
  -f compose.yaml \
  -f compose.dgx.yaml \
  run --rm runner \
  semantic-roundtrip job resume \
  --job "runs/$JOB_ID"
```

```text
runs/<JOB_ID>/runs/<CHILD_RUN_ID>
```


```bash
sudo docker compose -f compose.yaml run --rm runner \
  semantic-roundtrip run pause \
  --run "runs/$JOB_ID/runs/$CHILD_RUN_ID"
```

## 8. Stop services

Run artifacts remain in `RUN_ROOT`.

```bash
sudo docker compose \
  -f compose.yaml \
  -f compose.dgx.yaml \
  down
```

## 9. GPU usage

```bash
GPU_LOG="/tmp/semantic-roundtrip-gpu-$$.log"

nvidia-smi dmon -s u -d 1 > "$GPU_LOG" &
GPU_PID=$!

sudo docker compose \
  -f compose.yaml \
  -f compose.dgx.yaml \
  run --rm runner \
  semantic-roundtrip job start \
  --config configs/jobs/dgx_serial_benchmark.yaml

kill "$GPU_PID"
wait "$GPU_PID" 2>/dev/null

python3 scripts/calculate_gpu_usage.py "$GPU_LOG"
```

## Copy results to the local computer

```bash
rsync -avz --progress \
  mhagmann@128.130.58.152:~/bachelorthesis/semantic_roundtrip-data/runs/ \
  /Users/michaelhagmann/uni/Bachelor/bachelor_runs_from_dgx/
```
