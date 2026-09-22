# Configuration guide

An experiment combines dataset, backend and prompt profiles into one run.
A job executes several experiments and can reuse upstream stages.
Use [RUNNING](../RUNNING.md) for setup and [EXPERIMENTS](../EXPERIMENTS.md)
for the thesis jobs and scoring rules.

## Examples

- [Mock experiment](experiments/mock.yaml) and [complete real experiment](experiments/final_study/direct/direct_pg_q25_bi_q25.yaml)
- [Partial experiment](examples/direct_from_verification.yaml) and [in-job reuse](examples/job_with_inheritance.yaml)
- [Existing-run reuse](experiments/final_study/smoke/external_from_run.example.yaml)
- [Cross-job reuse](jobs/final_study/smoke_external_import.example.yaml)

## Dataset and backend profiles

Both use `schema_version: 1`. A dataset has a `dataset_id` and `items`
with `id`, `domain` and `title`. Item IDs must be unique. A [backend](backends/) selects
`adapter`, connection `settings` and `runtime`. Keep secrets in environment
variables. Stage request parameters belong in the experiment.

OpenAI-compatible backends optionally accept positive `settings.requests_per_minute`.
Aqueduct uses `25` starts per rolling 61-second window, including retries.
The counter is shared by endpoint and API-key environment-variable name within
one process only. Omitting the setting disables pacing.

## Experiment

Experiment `schema_version: 11` defines seeds, backend aliases and local `stages`.
A root experiment selects `dataset.profile`. A derived experiment inherits its
dataset and upstream products. At least one stage runs locally. Stage `parameters`
are sent to the adapter. The runner fixes stage order, not the YAML key order.

Stages include `illustratability_rating`, `prompt_generation`, `verification_prompt`,
`image_generation`, `verification_image`, `image_description` and `title_guessing`.
Under `title_guessing`, configure `direct`, `from_description` or `from_prompt`.
Routes are independently optional. Prompt-only needs no images or image seeds.

Model instructions use `prompt_profile` pointing to a [versioned YAML chat profile](../prompts/).
Profiles define `profile_id`, `version`, `output_format` and ordered `messages`.
Roles are `system`, `user` and `assistant`. Vision stages attach the image to their
single user message. Template variables are checked against stage inputs.

`verification_prompt` uses `policy: reference_title_absent` without a backend.
`verification_image` selects a backend and `policies.strict`, `policies.title_aware`
or both, each with its own `prompt_profile`. Checks affect scoring, not execution.

## Jobs and inheritance

Job `schema_version: 5` lists named `experiments` with `config` paths in execution
order. `job.continue_on_error: true` continues after terminal child-task failures.
An entry's `inherit.stages` copies these products and their required predecessors:

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

Use flattened title-stage names only inside `inherit.stages`. Import each needed
verification stage explicitly, as guessing inheritance does not include checks.
A stage cannot be both imported and local.

Exactly one source form is allowed:

- `from_entry`: an earlier entry in the same job.
- `from_run`: a specific standalone or child run.
- `from_job_entry`: `job` alias plus `entry` name from another job.

Declare cross-job aliases under `source_jobs`, then bind each on the CLI.
For example, with a completed local smoke job:

```bash
uv run semantic-roundtrip job start \
  --config configs/jobs/final_study/smoke_external_import.example.yaml \
  --source-job "local_smoke=runs/<COMPLETED_LOCAL_SMOKE_JOB_ID>"
```

Replace `start` with `plan` for a read-only overview with the same bindings.
CLI paths are relative to the working directory. YAML paths are relative to their file.
Selected source stages and dependencies must be terminal and inactive.
Imported successes and failures retain their provenance. Products are copied into
the child run, which no longer depends on the source. Keep snapshots with results.
Resume uses those saved settings rather than modified configuration files.

## Thesis dataset

Use the supplied [90-title dataset](datasets/final_titles_v1.yaml) and its
[item-level sources](datasets/final_titles_v1_sources.csv) for reproduction.
It selects 30 titles per domain from the first 300 eligible ranked entries using
seed `20260811`, without length quotas or an illustratability filter.
The [900-candidate pool](datasets/eligible_top300_v1.yaml) and its
[sources](datasets/eligible_top300_v1_sources.csv) support the separate rating supplement.

Songs and bands use [ListenBrainz all-time rankings](https://listenbrainz.readthedocs.io/en/latest/users/api/statistics.html)
with MusicBrainz metadata. Movies use [IMDb datasets](https://developer.imdb.com/non-commercial-datasets/), ranked by `numVotes`.
Eligibility requires Latin-script titles and release/formation by 2018, excludes
duplicates, development titles, adult movies and labelled song variants, and
limits the selected songs to one per primary artist. Bands must be `Group` entities.

The [dataset builder](../scripts/datasets/build_dataset.py) needs the original source
snapshot for byte-identical reproduction. New downloads can change the selection.
For comparison, set `--source-directory` and separate `--output`, `--report`,
`--candidate-output` and `--candidate-report` paths rather than overwriting V1.
Changes to sources, selection rules, seed or sample size require a new dataset version.
