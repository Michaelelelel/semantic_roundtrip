# Reproduce the thesis experiments

This guide specifies the pipeline roles, evaluated models, experimental matrix, and reproduction commands for the *Semantic Roundtrip* benchmark.

Use Bash from the repository root after completing [setup](RUNNING.md).
Replace example paths and Job IDs with the exact completed sources.
The thesis explains the scientific rationale. Exact settings are stored in
the versioned [configurations](configs/README.md) and each job's snapshots.

## Pipeline roles

- **Prompt Generation (PG):** Model converts source title and domain into a visual prompt.
- **Image Generation (IG):** Stable Diffusion 3.5 Large renders the scene from the visual prompt.
- **Image Description (ID):** Multimodal model produces an explicit textual description of the generated image.
- **Title Guessing (TG):** Model attempts to reconstruct the exact original title from the image (direct route), the description (description route), or the prompt alone (prompt route).

## Models

| Model label | Architecture / Checkpoint | Deployment | Evaluated roles |
| :--- | :--- | :--- | :--- |
| **Q25** | Qwen2.5-VL-32B-Instruct (F16) | Local (DGX) | PG, ID, TG |
| **G3** | Gemma 3 27B IT (F16) | Local (DGX) | PG, ID, TG |
| **Q38** | Qwen3.8-27B (BF16) | Local (DGX) | PG, ID, TG, Verifier |
| **G4** | Gemma 4 31B IT (BF16) | Local (DGX) | PG, ID, TG |
| **D32** | DeepSeek-R1-Distill-Qwen-32B (F16) | Local (DGX) | PG, TG (Text-only) |
| **O120** | GPT-OSS 120B (MXFP4) | Local (DGX) | PG, TG (Text-only) |
| **V4** | DeepSeek-V4-Flash 284B | Hosted API | PG, TG (Text-only) |
| **IG** | Stable Diffusion 3.5 Large (BF16) | Local (DGX) | Image Generation |

## Experimental design and verification

The main study evaluates 90 popular titles (30 songs, 30 movies, 30 bands) sampled from ListenBrainz and IMDb. Image-dependent conditions use 2 prompt seeds (`1000`, `1001`) crossed with 2 image seeds (`8566257`, `2875613`), producing 4 observations per title (360 per matrix cell). Prompt-only reconstruction uses 2 observations per title (180 per cell).

Reconstruction is evaluated under automated verification gates:

- **Prompt check:** Deterministic check for the normalized reference-title expression in the prompt.
- **Title-aware image check (Primary):** Multimodal verifier (Q38) checks whether the complete reference title is legibly written in the image.
- **Blind-strict image check (Alternative):** Verifier rejects any meaningful readable text.
- **Scoring:** Strict Exact Match requires the prompt check and, for image-dependent routes, the title-aware image check to pass. Prompt-only reconstruction has no image gate. Missing predictions, failed or missing checks and terminal technical failures count as zero in the full planned denominator.

Checks affect scoring, not whether later stages execute. Normalized Exact Match
and blind-strict results are reported separately on the same stored answers.

## Study jobs and research questions

| Group | Job config | Design / research question | Prerequisite |
| --- | --- | --- | --- |
| Main | `direct_core.yaml` | 4 x 4 direct; four paired indirect baselines (RQ1, RQ3, SQ4) | services ready |
| Main | `indirect_local.yaml` | 2 x 4 x 2 local indirect (RQ2, SQ4) | services ready |
| Main, split part 1 | `aqueduct_v4_independent.yaml` | 12 additions: V4 PG x 4 ID x D32/O120/V4 TG (RQ2, SQ4) | idle local model stack; API key |
| Main, split part 2 | `aqueduct_v4_completion.yaml` | 8 additions: D32/O120 PG x 4 ID x V4 TG (RQ2, SQ4) | exact completed local-indirect job; API key; no local GPU |
| Main, single-job alternative | `aqueduct_v4_extension.yaml` | the same 20 additions completing 3 x 4 x 3 (RQ2, SQ4) | exact completed local-indirect job; API key |
| Exploratory follow-up | `aqueduct_v4_384k_{d32,o120,v4}.yaml` | V4 TG at 384K on the same 12 description conditions | completed source descriptions and checks; one API key per runner; no local GPU |
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
Choose the 12+8 split or the single 20-condition extension. They cover the same
conditions and must not be combined as additional observations. Together with
the 16 Local Indirect conditions, either choice gives 36 conditions.

The commands use the unrestricted generation condition as the baseline.
The complete four-style report supported retaining this reference. Source
profiles and bindings must match that style across the compared routes.

![Main and supplementary study jobs](diagrams/study_jobs.svg)

[Editable Mermaid source](diagrams/study_jobs.mmd). The arrows mark data or
baseline dependencies; independent jobs do not need to run in the illustrated
order.

`job start` validates, creates a snapshot and runs in the foreground. Save its
printed Job ID. Use [resume](RUNNING.md#pause-and-resume), not another start,
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

### 1. Direct core (4x4)

Executes the 16 direct multimodal Qwen and Gemma model assignments (RQ1), the paired indirect baselines (RQ3), and domain contrasts (SQ4).

```bash
sudo docker compose --env-file .env \
  -f compose.yaml -f compose.dgx.yaml -f compose.status.yaml \
  --profile runner --profile status run --rm runner \
  semantic-roundtrip job start \
  --config configs/jobs/final_study/direct_core.yaml
```

### 2. Local indirect (2x4x2)

Uses D32 and O120 for prompt generation and title guessing, with the four Qwen/Gemma models providing image descriptions (RQ2).

```bash
sudo docker compose --env-file .env \
  -f compose.yaml -f compose.dgx.yaml -f compose.status.yaml \
  --profile runner --profile status run --rm runner \
  semantic-roundtrip job start \
  --config configs/jobs/final_study/indirect_local.yaml
```

### 3. Aqueduct extension (API text models)

Completes the 3x4x3 description-route matrix by adding hosted DeepSeek V4 through Aqueduct. D32 and O120 remain local models.
Load `AQUEDUCT_API_KEY` from `.env` as shown in [setup](RUNNING.md#3-build-and-start-runtime-services).

**Option A — Single combined job (20 conditions):**
Requires completed `indirect_local` as a source for existing images and descriptions.

```bash
sudo --preserve-env=AQUEDUCT_API_KEY docker compose --env-file .env \
  -f compose.yaml -f compose.dgx.yaml -f compose.status.yaml \
  --profile runner --profile status run --rm --no-deps -e AQUEDUCT_API_KEY runner \
  semantic-roundtrip job start \
  --config configs/jobs/final_study/aqueduct_v4_extension.yaml \
  --source-job "local_indirect=runs/<COMPLETED_LOCAL_INDIRECT_JOB_ID>"
```

**Option B — Split execution (Independent + Completion):**

- *Part 1 (Independent, 12 conditions):* V4 prompt generation, local image generation/verification, and D32/O120/V4 guessing:

```bash
sudo --preserve-env=AQUEDUCT_API_KEY docker compose --env-file .env \
  -f compose.yaml -f compose.dgx.yaml -f compose.status.yaml \
  --profile runner --profile status run --rm --no-deps -e AQUEDUCT_API_KEY runner \
  semantic-roundtrip job start \
  --config configs/jobs/final_study/aqueduct_v4_independent.yaml
```

- *Part 2 (Completion, 8 conditions, CPU-only):* V4 title guessing on descriptions from `indirect_local`:

```bash
sudo --preserve-env=AQUEDUCT_API_KEY docker compose --env-file .env \
  -f compose.yaml --profile runner \
  run --rm --no-deps -e AQUEDUCT_API_KEY runner \
  semantic-roundtrip job start \
  --config configs/jobs/final_study/aqueduct_v4_completion.yaml \
  --source-job "local_indirect=runs/<COMPLETED_LOCAL_INDIRECT_JOB_ID>"
```

The split jobs can run independently once Local Indirect is complete.
Completion needs its full source directory, including images, but no GPU service.
Concurrent processes must respect their available API-key quotas. The backend
limiter is shared within one process, not between runners.

### 4. V4 title-guessing follow-up (384K output)

Three API-only jobs repeat V4 title guessing on the same descriptions, with
1,440 predictions each. Only `max_tokens` changes to 393216 (384 x 1024).
Other request settings, including high effort and the 3,600-second timeout,
stay unchanged. Keep these results separate from the original 32,000-token
matrix and its notebook inputs.

| Job config | Source alias | Source job |
| --- | --- | --- |
| `aqueduct_v4_384k_d32.yaml` | `completion` | `aqueduct_v4_completion` |
| `aqueduct_v4_384k_o120.yaml` | `completion` | `aqueduct_v4_completion` |
| `aqueduct_v4_384k_v4.yaml` | `independent` | `aqueduct_v4_independent` |

Rebuild the runner after updating configs. Load the key as in [setup](RUNNING.md).
Example for D32, replacing the config and source binding for the other groups:

```bash
sudo --preserve-env=AQUEDUCT_API_KEY docker compose --env-file .env \
  -f compose.yaml --profile runner \
  run --rm --no-deps -e AQUEDUCT_API_KEY runner \
  semantic-roundtrip job start \
  --config configs/jobs/final_study/aqueduct_v4_384k_d32.yaml \
  --source-job "completion=runs/<AQUEDUCT_COMPLETION_JOB_ID>"
```

Use one available key per concurrent process, including any original job still
running. Source descriptions, checks and their dependencies must be terminal
and inactive. Full source directories, including images, are required.
Aqueduct's support for the requested output limit is not yet verified.

## Visual style and supplementary experiments

Direct Core serves as the unrestricted style baseline. Photorealistic, Sketch, and Comic evaluate the same 4x4 matrix under explicit style constraints (SQ2).

### Photorealistic (4x4)

```bash
sudo docker compose --env-file .env \
  -f compose.yaml -f compose.dgx.yaml -f compose.status.yaml \
  --profile runner --profile status run --rm runner \
  semantic-roundtrip job start \
  --config configs/jobs/final_study/direct_photorealistic.yaml
```

### Sketch (4x4)

```bash
sudo docker compose --env-file .env \
  -f compose.yaml -f compose.dgx.yaml -f compose.status.yaml \
  --profile runner --profile status run --rm runner \
  semantic-roundtrip job start \
  --config configs/jobs/final_study/direct_sketch.yaml
```

### Comic (4x4)

```bash
sudo docker compose --env-file .env \
  -f compose.yaml -f compose.dgx.yaml -f compose.status.yaml \
  --profile runner --profile status run --rm runner \
  semantic-roundtrip job start \
  --config configs/jobs/final_study/direct_comic.yaml
```

### Native thinking comparison (SQ3)

Evaluates reasoning modes (Q38 with low reasoning effort, G4 native thinking). Reuses unchanged Q25/G3 cells from Direct Core:

```bash
sudo docker compose --env-file .env \
  -f compose.yaml -f compose.dgx.yaml -f compose.status.yaml \
  --profile runner --profile status run --rm runner \
  semantic-roundtrip job start \
  --config configs/jobs/final_study/direct_thinking.yaml \
  --source-job "direct_base=runs/<COMPLETED_DIRECT_CORE_JOB_ID>"
```

<a id="illustratable-dataset"></a>

### High-illustratability dataset (SQ5)

Evaluates direct reconstruction on 90 titles selected by model-based illustratability ratings.
Use the supplied dataset to reproduce the thesis. The optional steps below
regenerate it from ratings and require a runner rebuild before reconstruction.

1. **(Optional) Re-run candidate ratings (900 titles):**

```bash
sudo docker compose --env-file .env \
  -f compose.yaml -f compose.dgx.yaml -f compose.status.yaml \
  --profile runner --profile status run --rm runner \
  semantic-roundtrip job start \
  --config configs/jobs/final_study/candidate_illustratability.yaml
```

2. **(Optional) Generate dataset from completed ratings:**

```bash
sudo docker compose --env-file .env \
  -f compose.yaml -f compose.dgx.yaml -f compose.status.yaml \
  --profile runner --profile status run --rm --no-deps \
  -v "$PWD/configs/datasets:/app/configs/datasets" \
  runner python scripts/datasets/select_illustratable.py \
  --job "runs/<COMPLETED_RATING_JOB_ID>"

sudo docker compose --env-file .env \
  -f compose.yaml -f compose.dgx.yaml -f compose.status.yaml \
  --profile runner --profile status build runner
```

3. **Run 4x4 high-illustratability reconstruction:**

```bash
sudo docker compose --env-file .env \
  -f compose.yaml -f compose.dgx.yaml -f compose.status.yaml \
  --profile runner --profile status run --rm runner \
  semantic-roundtrip job start \
  --config configs/jobs/final_study/direct_illustratable.yaml
```

### Prompt-only reconstruction (SQ1)

Evaluates title guessing directly from the generated visual prompt without an image. Reuses prompts and checks from Direct Core:

```bash
sudo docker compose --env-file .env \
  -f compose.yaml -f compose.dgx.yaml -f compose.status.yaml \
  --profile runner --profile status run --rm runner \
  semantic-roundtrip job start \
  --config configs/jobs/final_study/direct_prompt_only.yaml \
  --source-job "direct_base=runs/<COMPLETED_DIRECT_CORE_JOB_ID>"
```

## Analysis and report generation

Analysis reads completed job artifacts without making model calls. Use Python
3.14 and install the analysis dependencies before opening either notebook:

```bash
uv sync --frozen --extra analysis
```

Set the paths, open each notebook in a fresh kernel and run all cells.
Use matching source jobs. For the main and style analyses, keep executed
notebooks, tables, figures and manifests with the source archives.

For a partial main analysis, run setup and only the sections whose inputs are
available. The notebook lists their dependencies. Use a separate output directory.
The final technical tables and full-report export require all sections.

### 1. Style comparison analysis

Generates the four-style comparison figures and metrics:

```bash
export FREE_JOB=/path/to/direct-core-job
export PHOTOREALISTIC_JOB=/path/to/photorealistic-job
export COMIC_JOB=/path/to/comic-job
export SKETCH_JOB=/path/to/sketch-job
export OUTPUT_DIR="$PWD/notebooks/results/style"

uv run jupyter notebook notebooks/style_decision.ipynb
```

### 2. Main thesis analysis

Generates all primary (RQ1–RQ3) and secondary (SQ1–SQ5) figures and tables:

Choose exactly one Aqueduct input mode. For the two split jobs:

```bash
unset AQUEDUCT_JOB
export AQUEDUCT_INDEPENDENT_JOB=/path/to/aqueduct-independent-job
export AQUEDUCT_COMPLETION_JOB=/path/to/aqueduct-completion-job
```

For the single extension instead:

```bash
unset AQUEDUCT_INDEPENDENT_JOB AQUEDUCT_COMPLETION_JOB
export AQUEDUCT_JOB=/path/to/aqueduct-extension-job
```

Then set the remaining inputs. `STYLE_REPORT_DIR` must contain the completed
style report from the preceding step:

```bash
export DIRECT_JOB=/path/to/direct-core-job
export INDIRECT_JOB=/path/to/local-indirect-job
export THINKING_JOB=/path/to/thinking-job
export ILLUSTRATABLE_JOB=/path/to/illustratable-job
export PROMPT_BASELINE_JOB=/path/to/prompt-only-job
export STYLE_REPORT_DIR="$PWD/notebooks/results/style"
export OUTPUT_DIR="$PWD/notebooks/results/final"

uv run jupyter notebook notebooks/final_study.ipynb
```

Retain the full style report and any separately executed follow-up reports.
The final notebook's compact style summary is not a replacement for them.

### 3. Manual verifier assessment

Evaluates the 360-item manual audit against its original Core job
`20260903T230744Z_final-direct-core_faa7afcb`. These labels do not apply to a
newly generated Core job. Use the matching archived source:

```bash
uv run python scripts/evaluate_verifier.py \
  --job /path/to/20260903T230744Z_final-direct-core_faa7afcb
```

### 4. Candidate-rating distribution

The [included rating job](artifacts/candidate_illustratability/20260902T162529Z_candidate-illustratability_a1cfe5f2/)
contains all 3,600 ratings for 900 candidates. Its stored format was converted
after execution without changing model outputs. The notebook uses this job by
default and saves one PDF. The [saved distribution](artifacts/candidate_illustratability/report/candidate_pool_distribution.pdf)
can be viewed without running it.

```bash
unset RATING_JOB
export OUTPUT_DIR="$PWD/notebooks/results/illustratability_distribution"
uv run jupyter notebook notebooks/illustratability_distribution.ipynb
```
