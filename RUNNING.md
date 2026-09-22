# Setup and operation

This guide covers host setup, model downloads, starting runtime services, and monitoring experiments on a GPU cluster (DGX) or local workstation.

For running the benchmark jobs and analysis, see [`EXPERIMENTS.md`](EXPERIMENTS.md).

Run these commands in Bash from the repository root. Local GPU jobs require Docker Compose and NVIDIA container support.
Run one model job at a time per shared runtime stack. Do not restart its services while a job is active.

## 1. Storage and environment setup

### Clone and directory structure

```bash
git clone https://github.com/Michaelelelel/semantic_roundtrip.git
cd semantic_roundtrip
test -e .env || cp .env.example .env

DATA_ROOT="$HOME/bachelorthesis/semantic_roundtrip-data"
mkdir -p \
  "$DATA_ROOT/models" \
  "$DATA_ROOT/runs" \
  "$DATA_ROOT/runtime/comfyui/mnt" \
  "$DATA_ROOT/runtime/comfyui/base"

id -u
id -g
```

### Environment configuration (`.env`)

Keep an existing `.env`. Never commit its credentials. Set your own host user IDs, storage paths and optional API keys:

```dotenv
HOST_UID=1002
HOST_GID=1002
MODEL_ROOT=/home/user/bachelorthesis/semantic_roundtrip-data/models
RUN_ROOT=/home/user/bachelorthesis/semantic_roundtrip-data/runs
RUNTIME_ROOT=/home/user/bachelorthesis/semantic_roundtrip-data/runtime
STATUS_PORT=18000
AQUEDUCT_API_KEY=
```

## 2. Model downloads

Stable Diffusion 3.5 Large requires access to its [Hugging Face repository](https://huggingface.co/stabilityai/stable-diffusion-3.5-large). The download helper downloads pinned model weights and verifies checksums:

```bash
python3 -m venv "$HOME/.venvs/hf-download"
"$HOME/.venvs/hf-download/bin/python" -m pip install --upgrade pip huggingface_hub hf_xet

set -a
. ./.env
set +a
```

Run the token prompt separately and enter the token before continuing:

```bash
read -rsp "Hugging Face token: " HF_TOKEN
```

Then download the models:

```bash
export HF_TOKEN
HF_XET_HIGH_PERFORMANCE=1 sh models/download-final-study.sh "$MODEL_ROOT"
unset HF_TOKEN
```

## 3. Build and start runtime services

Load environment variables once per terminal session:

```bash
set -a
. ./.env
set +a
```

Build and launch the Docker runtime containers:

```bash
sudo docker compose --env-file .env \
  -f compose.yaml -f compose.dgx.yaml -f compose.status.yaml \
  --profile runner --profile status build runner status_web

sudo docker compose --env-file .env \
  -f compose.yaml -f compose.dgx.yaml -f compose.status.yaml \
  --profile runner --profile status up -d --force-recreate --wait \
  text_runtime vision_runtime image_runtime status_web
```

### Runtime services

| Service | Technology | Role |
| :--- | :--- | :--- |
| `text_runtime` | llama.cpp server | Text-input stages (Qwen, Gemma, DeepSeek, GPT-OSS) |
| `vision_runtime` | llama.cpp vision server | Image-input stages (Qwen2.5-VL, Gemma 3, Qwen3.8, Gemma 4) |
| `image_runtime` | ComfyUI | Text-to-image synthesis (Stable Diffusion 3.5 Large) |
| `status_web` | FastAPI / HTML | Local monitoring web dashboard |

<a id="monitor-and-resume"></a>

## 4. Monitoring and job control

Run commands from another terminal or inside `tmux`:

### Listing and status

```bash
# List completed or running jobs
sudo docker compose --env-file .env \
  -f compose.yaml -f compose.dgx.yaml -f compose.status.yaml \
  --profile runner --profile status run --rm runner \
  semantic-roundtrip job list --root runs

# Check detailed status and watch live progress
sudo docker compose --env-file .env \
  -f compose.yaml -f compose.dgx.yaml -f compose.status.yaml \
  --profile runner --profile status run --rm runner \
  semantic-roundtrip job status --job "runs/<JOB_ID>" --watch 5

# View Docker service logs
sudo docker compose --env-file .env \
  -f compose.yaml -f compose.dgx.yaml -f compose.status.yaml \
  --profile runner --profile status logs --tail=100 --follow
```

### Pause and resume

Jobs can be safely paused (allowing the active request to finish) and resumed:

```bash
# Pause a running job
sudo docker compose --env-file .env \
  -f compose.yaml -f compose.dgx.yaml -f compose.status.yaml \
  --profile runner --profile status run --rm runner \
  semantic-roundtrip job pause --job "runs/<JOB_ID>"

# Resume an interrupted or paused job
sudo docker compose --env-file .env \
  -f compose.yaml -f compose.dgx.yaml -f compose.status.yaml \
  --profile runner --profile status run --rm runner \
  semantic-roundtrip job resume --job "runs/<JOB_ID>"
```

For hosted jobs, load `.env` as above and forward the API key:

```bash
sudo --preserve-env=AQUEDUCT_API_KEY docker compose --env-file .env \
  -f compose.yaml -f compose.dgx.yaml -f compose.status.yaml \
  --profile runner --profile status run --rm -e AQUEDUCT_API_KEY runner \
  semantic-roundtrip job resume --job "runs/<JOB_ID>"
```

Resume uses saved settings and source bindings, not edited YAML files. Completed work is skipped, while terminal failures remain recorded.
When copying execution or inheritance inputs, retain full job directories with child runs, images and snapshots. Metadata-only copies are insufficient.

### Status web dashboard

The web interface runs on the host at `http://127.0.0.1:$STATUS_PORT`. To access it remotely from your local machine, open an SSH tunnel:

```bash
ssh -N -L 8000:127.0.0.1:18000 user@dgx-host
```

Then open `http://127.0.0.1:8000` in your browser to view job status, prompts, images, predictions, and verification checks.

## 5. Deployment validation (Smoke tests)

These optional checks verify GPUs, model weights and Docker containers before large jobs. Their outputs are not final-study inputs and do not select settings.

### Local pipeline smoke test

Runs a fast end-to-end check across all local model runtimes:

```bash
sudo docker compose --env-file .env \
  -f compose.yaml -f compose.dgx.yaml -f compose.status.yaml \
  --profile runner --profile status run --rm runner \
  semantic-roundtrip job start \
  --config configs/jobs/final_study/smoke_local.yaml
```

### Hosted API smoke test

Verifies API connectivity for hosted text models (requires `AQUEDUCT_API_KEY`):

```bash
sudo --preserve-env=AQUEDUCT_API_KEY docker compose --env-file .env \
  -f compose.yaml -f compose.dgx.yaml -f compose.status.yaml \
  --profile runner --profile status run --rm -e AQUEDUCT_API_KEY runner \
  semantic-roundtrip job start \
  --config configs/jobs/final_study/smoke_aqueduct.yaml
```
