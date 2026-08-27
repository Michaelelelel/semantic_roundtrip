# Final study design (`final_v1`)

This file is the portable source of truth for the executable study. Older
legacy/intermediate/current matrices are historical and must not be used for a
production run.

## Shared protocol

- Dataset: `final_titles_v1` with 30 songs, 30 movie titles, and 30 band names.
- Prompt seeds: `1000`, `1001`.
- Image seeds: `8566257`, `2875613`.
- Four observations per title and condition.
- Image generator: Stable Diffusion 3.5 Large BF16.
- Verifier: Qwen3-VL-8B-Instruct F16 with the deterministic `json_v3` prompt.
- One technical retry with identical settings; no retry because a title is wrong.
- Primary outcome: title-level end-to-end Strict Exact Match.
- Supporting evidence: Normalized Exact Match, verifier results, technical
  failures, and local/imported runtimes.
- Final study artifacts are not edited manually.

One expected observation scores one only when verification passes, a prediction
exists, and Strict Exact Match is true. Missing predictions, exhausted retries,
invalid responses, timeouts, and verifier rejections score zero and are also
reported separately as technical evidence.

## Model identifiers

| ID | Model | Precision | Roles |
| --- | --- | --- | --- |
| `Q25` | Qwen2.5-VL-32B-Instruct | F16 | PG, BB, direct BI |
| `G3` | Gemma 3 27B IT | F16 | PG, BB, direct BI |
| `Q38` | Qwen3.8-27B | BF16 | PG, BB, direct BI |
| `G4` | Gemma 4 31B IT | BF16 | PG, BB, direct BI |
| `D32` | DeepSeek-R1-Distill-Qwen-32B | F16 | PG, text BI |
| `O120` | GPT-OSS 120B | MXFP4 | PG, text BI |
| `V4` | Aqueduct `deepseek-v4-flash-284b` | hosted | optional PG, text BI |

PG is prompt generation, BG image generation, BB image description, and BI title
interpretation.

## RQ1: direct Qwen/Gemma comparison

**Question:** How does direct end-to-end title reconstruction vary across the
selected Qwen and Gemma release cohorts and their combinations in PG and BI?

The twelve unique PG/BI conditions are:

- `Q25 -> Q25, Q38, G3`
- `Q38 -> Q38, Q25, G4`
- `G3 -> G3, G4, Q25`
- `G4 -> G4, G3, Q38`

They form four overlapping 2 x 2 comparisons:

1. Qwen 2025 versus Qwen 2026.
2. Gemma 2025 versus Gemma 2026.
3. Qwen versus Gemma in the 2025 cohort.
4. Qwen versus Gemma in the 2026 cohort.

For every 2 x 2 comparison the analysis reports the four cell accuracies, the PG
contrast, the BI contrast, and matching versus mixed PG/BI. These are descriptive
effects for the selected deployed configurations, not universal family effects.

The four diagonal conditions `Q25/Q25`, `G3/G3`, `Q38/Q38`, and `G4/G4` also
execute the description route with `BB=BI`. The other eight execute only the
direct route.

Executable job: `direct_core.yaml`.

## RQ2: local description-route matrix

**Question:** How do the selection and combination of PG, BB, and BI relate to
title reconstruction on the description-mediated route?

Balanced `2 x 4 x 2` design:

- PG: `D32`, `O120`.
- BB: `Q25`, `G3`, `Q38`, `G4`.
- BI: `D32`, `O120`.
- BG: fixed SD3.5 Large.

The 16 conditions support:

- PG and BI marginal differences;
- marginal BB performance;
- PG x BI interaction and matching versus mixed PG/BI;
- whether matching versus mixed changes with BB;
- domain-specific and technical/runtime summaries.

The models differ in more than one property. Results are comparisons of concrete
deployed model configurations, not isolated age, size, architecture, or family
effects.

Executable job: `indirect_local.yaml`.

## RQ3: direct versus description-mediated route

**Question:** On the same generated images, how does direct image-to-title
reconstruction differ from reconstruction through an explicit description?

The four diagonal RQ1 conditions provide both routes. The analysis pairs routes
per image, reports the title-level accuracy difference and interval, and counts
the transitions both-correct, direct-only, description-only, and neither-correct.

## RQ4: domains

All primary results are also reported separately for songs, movie titles, and
band names. These are subgroup results for the fixed dataset, not universal
claims about each domain.

## Optional Aqueduct extension

If access and service stability permit, `V4` expands RQ2 to `3 x 4 x 3`. The 16
local cells stay unchanged and 20 new cells are added. The extension is reported
separately because V4 is larger and externally hosted.

Executable job: `aqueduct_v4_extension.yaml`. Its external source-job directory
must point to the completed local indirect job.

## Artifact reuse and scientific conditions

Each condition remains a self-contained run. To avoid regenerating unrelated
random artifacts in a controlled comparison, derived runs materialize completed
upstream stages from one source run into their own SQLite database and image
directory. They do not depend on the source afterward.

- RQ1: four PG roots generate four image sets (1,440 images); the other BI cells
  inherit through verification.
- RQ2: two PG roots generate two image sets (720 images); each PG/BB description
  set is generated once and reused by the second BI.
- Local study total: 28 scientific conditions and 2,160 generated images.

Imported tasks retain terminal failures and provenance. They never load a local
model and are excluded from local ETA. No content hash or automatic repair is
used. Final study artifacts are nevertheless left unedited by protocol.

## Analysis

Run databases are selected through `configs/studies/final_study.yaml`. The loader
reads SQLite read-only and the notebook
`../thesis/analysis/final_study.ipynb` computes the analysis directly in Pandas.
There is no required CSV intermediate.

The four repetitions are first averaged per title. Confidence intervals use
10,000 deterministic, paired resamples of complete titles, stratified by domain
and the dataset title-length group. Related conditions and both routes use the
same resampled titles.

Only PNG figures needed by the thesis are written. Raw responses, predictions,
errors, verifier results, and runtime evidence remain in the run databases.

## Freeze gates

1. The model-free mock job and notebook pass.
2. Every local model passes `smoke_local.yaml` on a DGX Spark.
3. External import remains usable after moving its source.
4. Aqueduct smoke is optional and does not block the local freeze.
5. The user reviews and commits; automation never commits these changes.
