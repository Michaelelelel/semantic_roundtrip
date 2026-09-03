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

An optional `title_check_report: true` under `stages.prompt_generation` writes
`prompt_title_check.json` after prompt generation. It flags normalized literal
title occurrences without filtering, retrying or changing scores. The default
is false; existing run snapshots and the database schema stay compatible.
Normalization and matching are shared with analysis in
`src/semantic_roundtrip/evaluation.py`; exact rules and method IDs are in the
[study protocol](jobs/final_study/STUDY_DESIGN.md#outcomes-and-analysis).

Experiment schema 8 selects a dataset, seeds, backend aliases and the stages run
locally:

```yaml
schema_version: 8

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
  verification:
    backend: model
  title_guessing:
    direct:
      backend: model
```

Available local stages:

```text
illustratability_rating
prompt_generation
image_generation
verification
title_guessing.direct
image_description
title_guessing.from_description
```

At least one must run locally. Paths inside an experiment are relative to that
file. A root experiment defines `dataset`; a derived experiment receives its
dataset and upstream products through inheritance. Stage `parameters` are sent
to the adapter and should be explicit for a fixed study.

## Job

Job schema 4 lists experiments in execution order:

```yaml
schema_version: 4

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
      stages: [verification]
```

`continue_on_error: true` lets later independent entries run after one child has
terminal task failures. It does not hide those failures.

## Inheritance

An inherited stage includes all required predecessors:

| Requested stage | Materialized chain |
| --- | --- |
| `prompt_generation` | prompt |
| `image_generation` | prompt, image |
| `verification` | prompt, image, verification |
| `title_guessing_direct` | verification chain, direct prediction |
| `image_description` | verification chain, description |
| `title_guessing_from_description` | description chain, indirect prediction |
| `illustratability_rating` | rating only |

Use the flattened title-stage names only inside `inherit.stages`.

Exactly one source form is allowed:

- `from_entry`: an earlier entry in the same job;
- `from_run`: a specific completed standalone or child run;
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
      stages: [verification]
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

## Checklist

- Use stable, descriptive run and entry names.
- Keep paths relative to the YAML that contains them.
- Put secrets only in environment variables.
- Give every derived run all required upstream stages.
- Reuse only artifacts produced under the intended protocol.
- Optionally inspect source bindings, counts and model roles with `job plan`.
- Keep the generated run and job snapshots with the results.

DGX commands are in [`../RUNNING.md`](../RUNNING.md). The executable thesis
protocol is in
[`jobs/final_study/STUDY_DESIGN.md`](jobs/final_study/STUDY_DESIGN.md).
