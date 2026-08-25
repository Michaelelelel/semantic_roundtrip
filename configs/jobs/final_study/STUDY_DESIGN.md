# Final study: research questions and experiment mapping

This document is the source of truth for the primary bachelor-thesis study. It
describes which experiment answers each research question and how the resulting
runs are analyzed. Older planning notes are historical where they conflict with
this file or the current YAML configurations.

## Shared study protocol

- Dataset: 30 songs, 30 movie titles, and 30 band names.
- Repetitions: two prompt seeds and two image seeds, producing four images per
  title and condition (360 images per condition).
- Primary metric: title-level end-to-end Strict Exact Match accuracy.
- Supporting results: normalized Exact Match, verifier outcomes, technical
  failures, and stage/model-loading runtimes.
- Independent analysis unit: title. The four seed repetitions are averaged
  within each title before conditions are summarized.
- Uncertainty: 95% intervals are calculated by resampling titles. The overall
  interval preserves the number of titles in each domain.
- Fixed verifier: Qwen2.5-VL 7B F16 in every primary condition.
- LLaVA 1.5 uses separately pinned F16 language-model and projector GGUF files
  derived from the same upstream checkpoint. The projector package is selected
  for compatibility with the current llama.cpp runtime.
- Main inference mode: no model reasoning. Reasoning experiments are outside the
  frozen primary-study scope.
- Execution: every condition is a complete independent run. No prompts, images,
  database rows, or other artifacts are copied from another run.

The same dataset, seeds, prompts, stage parameters, and unchanged model profiles
are used wherever a controlled comparison permits it. Independent execution does
not guarantee byte-identical artifacts. Component comparisons therefore estimate
the performance difference between controlled pipeline conditions; they are not
claims about a deterministic causal effect on one fixed set of images.

## RQ1: Complete model systems

**Question:** How does strict end-to-end title-reconstruction accuracy differ
between selected legacy, intermediate, and current locally hosted model systems?

| Condition | Prompt model | Image model | Reconstruction model |
| --- | --- | --- | --- |
| `system_legacy` | Mistral 7B F16 | Stable Diffusion 1.5 | LLaVA 1.5 7B F16 |
| `system_intermediate` | Mistral Small 24B F16 | SDXL Base 1.0 | Qwen2.5-VL 7B F16 |
| `anchor_current` | Qwen3.8 27B BF16 | Qwen-Image 2512 BF16 | Gemma 4 31B BF16 |

- Produced by: `spark_a_system_image.yaml`
- Study group: `complete_systems`
- Analysis kind: `accuracy`, direct route
- Thesis result: one absolute-accuracy figure for the three systems, overall and
  by domain. Differences describe complete systems and must not be attributed to
  one individual stage.

## RQ2: Sensitivity to replacing one model stage

**Question:** How does strict title-reconstruction accuracy change when one model
stage around the current anchor is replaced while the remaining configuration is
held fixed?

### RQ2a: Prompt model

Conditions: `prompt_mistral7`, `prompt_mistral24`, `prompt_qwen30`,
`prompt_gemma4_gemma_reconstruction`, and `anchor_current`.

- Compared models: Mistral 7B, Mistral Small 24B, Qwen3 30B-A3B, Gemma 4 31B,
  and Qwen3.8 27B.
- Produced by: Spark B; the anchor is produced once by Spark A.
- Study group: `prompt_models`
- Analysis kind: `paired`, direct route, reference `anchor_current`

### RQ2b: Image model

Conditions: `image_sd15`, `image_sdxl`, `image_sd35`, and `anchor_current`.

- Compared models: Stable Diffusion 1.5, SDXL Base 1.0, Stable Diffusion 3.5
  Large, and Qwen-Image 2512.
- Produced by: `spark_a_system_image.yaml`
- Study group: `image_models`
- Analysis kind: `paired`, direct route, reference `anchor_current`

### RQ2c: Reconstruction model

Conditions: `reconstruction_llava`, `reconstruction_qwen25`,
`reconstruction_qwen38`, and `anchor_current`.

- Compared models: LLaVA 1.5 7B, Qwen2.5-VL 7B, Qwen3.8 27B, and Gemma 4 31B.
- Produced by: Spark B; the anchor is produced once by Spark A.
- Study group: `reconstruction_models`
- Analysis kind: `paired`, direct route, reference `anchor_current`

For every `paired` group, the plotted value is condition accuracy minus anchor
accuracy in percentage points. Positive values favor the condition; negative
values favor the anchor.

## RQ3: Direct versus description-mediated reconstruction

**Question:** For the same generated images and the same multimodal model, how
does direct image-to-title reconstruction differ from
image-to-description-to-title reconstruction?

Two panels answer this question:

- `complete_system_routes`: `system_legacy`, `system_intermediate`, and
  `anchor_current`;
- `reconstruction_routes`: `reconstruction_llava`, `reconstruction_qwen25`,
  `reconstruction_qwen38`, and `anchor_current`.

Both use analysis kind `routes`. Within each condition, the plotted value is
description-route accuracy minus direct-route accuracy. Both routes receive the
same image, and the same multimodal model performs the direct prediction, image
description, and description-based prediction.

## RQ4: Domain differences

**Question:** How do reconstruction results differ between songs, movie titles,
and band names?

No additional experiment is required. Every primary group reports an overall
result and separate results for the three domains. Domain findings are subgroup
results for this selected dataset and should be interpreted together with their
uncertainty intervals.

## Focused secondary comparison: model-family matching

**Question:** Does reconstruction accuracy differ when prompt generation and
title reconstruction use matching Qwen or Gemma model families rather than a
mixed pair?

The four configured combinations are:

| Prompt family | Reconstruction family | Condition |
| --- | --- | --- |
| Qwen | Gemma | `anchor_current` |
| Qwen | Qwen | `reconstruction_qwen38` |
| Gemma | Gemma | `prompt_gemma4_gemma_reconstruction` |
| Gemma | Qwen | `family_gemma_prompt_qwen_reconstruction` |

The study groups `qwen_family_match` and `gemma_family_match` provide two focused
paired comparisons. This is supporting evidence, not a complete factorial causal
analysis of every possible model-family interaction.

## Engineering smoke test

`native_smoke.yaml` loads and calls every native-precision model family and image
workflow required by the primary study using one image per condition. It is an
engineering gate only and is not included in the thesis accuracy analysis.

## Jobs and analysis

1. Run `native_smoke.yaml` and require zero failed tasks.
2. Run `spark_a_system_image.yaml` and
   `spark_b_prompt_vision_route.yaml`, sequentially or on independent machines.
3. Copy `configs/studies/final_study.example.yaml` into a study directory and
   replace its run placeholders with the completed child-run paths.
4. Run `semantic-roundtrip study analyze --study <study-directory>`.

The analysis reads the selected SQLite databases without modifying them. The YAML
study groups define which conditions may be compared; job membership does not.

## Thesis result structure

1. Technical validity: completion, verifier, failure, and runtime evidence.
2. RQ1: absolute comparison of complete systems.
3. RQ2: prompt-, image-, and reconstruction-model differences from the anchor.
4. RQ3: direct versus description-mediated reconstruction.
5. RQ4: compact domain comparison across the main results.
6. Focused model-family comparison, clearly separated from the primary results.
7. Discussion of semantic information loss, limitations, runtime, and the fact
   that independent controlled runs do not reuse byte-identical artifacts.
