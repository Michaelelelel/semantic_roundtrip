# Configuration guide

One experiment YAML creates one self-contained run. One job YAML executes
several experiments and may copy terminal upstream stages into later runs.

The layers are:

1. dataset profile;
2. backend profile;
3. experiment;
4. optional job and inheritance links.

Start with the checked-in mock and copy the closest example. `job start`
validates the resolved job before creating and executing it. `job plan` is an
optional read-only summary of expected work.

## Examples

- Root experiment: [`experiments/mock.yaml`](experiments/mock.yaml)
- Partial experiment: [`examples/direct_from_verification.yaml`](examples/direct_from_verification.yaml)
- In-job reuse: [`examples/job_with_inheritance.yaml`](examples/job_with_inheritance.yaml)
- Existing-run reuse:
  [`experiments/final_study/smoke/external_from_run.example.yaml`](experiments/final_study/smoke/external_from_run.example.yaml)
- Cross-job reuse:
  [`jobs/final_study/smoke_external_import.example.yaml`](jobs/final_study/smoke_external_import.example.yaml)
- Complete real experiment:
  [`experiments/final_study/direct/direct_pg_q25_bi_q25.yaml`](experiments/final_study/direct/direct_pg_q25_bi_q25.yaml)

```bash
uv run semantic-roundtrip job start \
  --config configs/examples/job_with_inheritance.yaml
```

## Dataset and backend profiles

Both use schema version 1. Dataset item IDs must be unique.

```yaml
schema_version: 1
dataset_id: my_titles_v1
items:
  - id: songs_imagine
    domain: songs
    title: Imagine
```

A backend selects an adapter, connection settings and runtime owner. Never put
secrets into YAML.

```yaml
schema_version: 1
adapter: mock
settings: {}
runtime:
  controller: none
  resource_group: cpu
```

Real profiles are below `backends/`. Copy the nearest profile when adding a
model; endpoint and runtime settings belong there, scientific request parameters
belong in the experiment.

## Experiment

Experiment schema 11 selects a dataset, seeds, backend aliases and locally run
stages. Prompt and image verification are independently optional. The prompt
check is deterministic and requires no backend; image checks select a backend
and either or both policies. The blind
strict policy rejects any meaningful readable writing; the title-aware policy
receives the reference title and rejects only writing that communicates that
title. Omit both verification stages for no checks, or omit one image policy to run only
the other. The final-study configs enable all three decisions. Checks affect
evaluation but do not stop later stages.

```yaml
schema_version: 11

run:
  name: my_direct_run
  output_directory: runs

dataset:
  profile: ../datasets/mock_titles_v1.yaml

experiment:
  prompt_seeds: [1000, 1001]
  image_seeds: [41, 42]
  retry_limit: 0

backends:
  model:
    profile: ../backends/mock.yaml

stages:
  prompt_generation:
    backend: model
    prompt_profile: prompts/prompt_generation/visual_single_v5.yaml
  image_generation:
    backend: model
  verification_prompt:
    policy: reference_title_absent
  verification_image:
    backend: model
    policies:
      strict:
        prompt_profile: prompts/verification/json_v3.yaml
      title_aware:
        prompt_profile: prompts/verification/title_aware_json_v1.yaml
  title_guessing:
    direct:
      backend: model
      prompt_profile: prompts/title_guessing/plain_v3.yaml
    from_prompt:
      backend: model
      prompt_profile: prompts/title_guessing/prompt_plain_v1.yaml
```

Every model instruction is a versioned YAML chat profile. A profile records its
identity, version, output format and ordered messages:

```yaml
profile_id: title_guessing_direct
version: 3
output_format: plain_text

messages:
  - role: user
    content: |
      Identify the exact title represented by this image.
      Domain: ${domain}
```

Messages may use the `system`, `user` and `assistant` roles. Vision stages
attach the image to their single user message. Profile variables are validated
against the inputs available to the configured stage. All prompt-bearing stage
fields are named `prompt_profile`; plain-text prompt files are not supported.

Available local stages:

```text
illustratability_rating
prompt_generation
verification_prompt
image_generation
verification_image
title_guessing.direct
image_description
title_guessing.from_description
title_guessing.from_prompt
```

At least one must run locally. Paths inside an experiment are relative to that
file. A root experiment defines `dataset`; a derived experiment receives its
dataset and upstream products through inheritance. Stage `parameters` are sent
to the adapter and should be explicit for a fixed study.

The listed execution order is fixed by the runner, not the YAML key order.
Prompt-only can configure `prompt_generation`, `verification_prompt` and
`title_guessing.from_prompt`, omitting images, image seeds and any verifier
backend. Its guesser receives only the stored prompt and domain. Image and
description routes remain independently optional.

## Job

Job schema 5 lists experiments in execution order:

```yaml
schema_version: 5

job:
  name: my_job
  output_directory: runs
  continue_on_error: false

experiments:
  - name: source
    config: ../experiments/mock.yaml
  - name: derived
    config: direct_from_verification.yaml
    inherit:
      from_entry: source
      stages: [verification_prompt, verification_image]
```

`continue_on_error: true` lets later independent entries run after one child has
terminal task failures. It does not hide those failures.

## Inheritance

An inherited stage includes all required predecessors:

| Requested stage | Materialized chain |
| --- | --- |
| `prompt_generation` | prompt |
| `image_generation` | prompt, image |
| `verification_prompt` | prompt, prompt verification |
| `verification_image` | prompt, image, image verification |
| `title_guessing_direct` | prompt, image, direct prediction |
| `image_description` | prompt, image, description |
| `title_guessing_from_description` | prompt, image, description, indirect prediction |
| `title_guessing_from_prompt` | prompt, prompt prediction |
| `illustratability_rating` | rating only |

Use the flattened title-stage names only inside `inherit.stages`.
Verification is an independent evaluation branch. Request each needed
verification stage explicitly beside reconstruction when retaining its checks;
guessing inheritance does not implicitly import verification. Prompt checks
can be imported without images. A stage cannot be both imported and local.

Exactly one source form is allowed:

- `from_entry`: an earlier entry in the same job;
- `from_run`: a specific standalone or child run with terminal selected work;
- `from_job_entry`: a named entry from another job.

Cross-job reuse declares an alias:

```yaml
source_jobs:
  local_source: {}

experiments:
  - name: imported
    config: ../experiments/derived.yaml
    inherit:
      from_job_entry:
        job: local_source
        entry: source_entry
      stages: [verification_prompt, verification_image]
```

Bind it explicitly when starting:

```bash
uv run semantic-roundtrip job start --config configs/jobs/my_job.yaml \
  --source-job local_source=runs/exact-source-job
```

To inspect this job without creating artifacts, replace `start` with `plan` and
keep the same `--source-job` binding.

CLI source paths are resolved from the current working directory; YAML paths
are resolved from their containing file.

The child copies data and files into its own run. It does not depend on the
source afterward. Imported successes and terminal failures keep their
provenance. The importer validates stage structure and expected rows; it does
not repair or silently regenerate mismatches.
Selected stages and dependencies must be terminal and inactive; unrelated work
may continue in a new-format source. Bundled snapshots preserve expected counts
and policies even when upstream failures produced no verification tasks.

Run DB 12 stores prompt predictions separately from image-linked predictions:
`prompt_predictions` has an ID, unique required `prompt_id`, title, raw response,
optional confidence and method, and origin Run/Prediction IDs. A run defines one
model assignment, so each prompt has at most one prediction per route.
Job DB remains 4 and manifest format remains 6. Old formats are accepted only
by the explicit one-time converter on completed copies, not normal execution.

## Checklist

- Use stable, descriptive run and entry names.
- Keep paths relative to the YAML that contains them.
- Put secrets only in environment variables.
- Give every derived run all required upstream stages.
- Reuse only artifacts produced under the intended protocol.
- Optionally inspect source bindings, counts and model roles with `job plan`.
- Keep the generated run and job snapshots with the results.

Shared DGX setup and operation are in [`../RUNNING.md`](../RUNNING.md).
Use [`../EXPERIMENTS.md`](../EXPERIMENTS.md) for the main, four-style and
supplementary experiment sequence. The executable thesis protocol is in
[`jobs/final_study/STUDY_DESIGN.md`](jobs/final_study/STUDY_DESIGN.md).
