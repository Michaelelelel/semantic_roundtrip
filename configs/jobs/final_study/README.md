# Final study jobs

For the authoritative research questions, experiment-to-question mapping, and
planned thesis evidence, see `STUDY_DESIGN.md`.

The primary study is split into two independent jobs. They can run sequentially
on one DGX Spark or separately on two machines. Both jobs use the same dataset,
seeds, fixed verifier, and current anchor configuration.

## Primary jobs

- `spark_a_system_image.yaml` compares complete legacy, intermediate, and current
  systems, followed by the controlled image-model comparison.
- `spark_b_prompt_vision_route.yaml` compares prompt models, reconstruction
  models, and matched versus mixed Qwen/Gemma model families.

The current anchor runs once on Spark A. The final study configuration uses this
completed run as the reference for comparisons with the independent runs from
Spark B, so the expensive anchor experiment is not repeated.

Before either primary job, run `native_smoke.yaml`. It creates only six images
but loads every native-precision model family and image workflow used by the
primary matrix.

## Independent runs

Every experiment executes the complete configured pipeline and produces a
self-contained child run. The dataset, seeds, verifier, and all models outside
the compared stage remain fixed in the controlled comparisons; no outputs are
copied between runs.

## Optional job

`optional_extensions.yaml` is not part of the primary matrix. It preserves
additional expensive comparisons such as reasoning, GPT-OSS, and FLUX for use
only after the primary jobs have completed and their results have been reviewed.
These optional configurations still use the earlier Qwen3.6-based anchor and must
be reviewed before they are included in a separate study.
