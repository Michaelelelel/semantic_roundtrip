# Semantic Roundtrip

Semantic Roundtrip measures whether a title remains recognizable after models
translate it through an image.

```text
title + domain
  -> prompt generation (PG)
  -> image generation (BG)
  -> text verifier
  -> direct title interpretation (BI)
     or image description (BB) -> title interpretation (BI)
```

The pipeline stores resolved configs, prompt and workflow snapshots, raw model
responses, images, predictions, errors and timing evidence in each run. Jobs
execute multiple runs and can reuse completed upstream stages without changing
the source artifacts.

## Quick start

The model-free mock needs Python 3.14 and `uv`:

```bash
python3.14 -m venv .venv
source .venv/bin/activate
uv sync --extra analysis --extra web

uv run semantic-roundtrip run start \
  --config configs/experiments/mock.yaml
uv run semantic-roundtrip run list
```

Use `uv run semantic-roundtrip --help` for the CLI.

## Final study

For the four-style selection pilot (free, sketch, comic, photorealistic), use
the [pilot commands](RUNNING.md#four-style-pilot). These jobs use 30 held-out
titles per domain, one prompt/image seed pair and four same-model PG/BI pairs.
They are separate from the main and supplementary matrices below.

The study uses seven reconstruction jobs:

| Job | Design | Dependency |
| --- | --- | --- |
| `direct_core.yaml` | direct 4 x 4 PG/BI | none |
| `indirect_local.yaml` | local indirect 2 x 4 x 2 PG/BB/BI | none |
| `aqueduct_v4_extension.yaml` | completes indirect to 3 x 4 x 3 | completed `indirect_local` |
| `direct_sketch.yaml` | direct 4 x 4 with a fixed sketch instruction | none |
| `direct_comic.yaml` | direct 4 x 4 with a broad comic instruction | none |
| `direct_thinking.yaml` | direct native-thinking supplement | completed `direct_core` |
| `direct_illustratable.yaml` | direct 4 x 4 on selected illustratable titles | completed candidate ratings |

The separate `candidate_illustratability.yaml` rating job creates the prerequisite
for the last dataset. Aqueduct and Thinking must receive their exact matching
source jobs through `--source-job`; neither chooses a source automatically.
`job plan` is an optional read-only summary, not a required start step.

Smoke and development configurations are optional deployment checks. They are
not study inputs and their results are not combined with the seven jobs above.

Exact settings and analysis rules are recorded in
[`configs/jobs/final_study/STUDY_DESIGN.md`](configs/jobs/final_study/STUDY_DESIGN.md).

## Documentation

- [`RUNNING.md`](RUNNING.md): DGX setup, services, jobs, monitoring and analysis.
- [`configs/README.md`](configs/README.md): create experiments, derived runs and
  jobs.
- [`configs/jobs/final_study/STUDY_DESIGN.md`](configs/jobs/final_study/STUDY_DESIGN.md):
  concise executable study protocol.
- [`configs/datasets/final_titles_v1.md`](configs/datasets/final_titles_v1.md):
  dataset construction and sources.
- [`manual_evaluation/README.md`](manual_evaluation/README.md): manual verifier,
  sketch and comic checks.
- [`notebooks/final_study.ipynb`](notebooks/final_study.ipynb): study analysis
  and validation results.

Scientific motivation, related work, methodological argument and interpretation
belong in the bachelor thesis. Repository Markdown documents operation and the
versioned executable protocol.

## Repository map

- `configs/`: datasets, backends, experiments, jobs and deployment catalogs.
- `prompts/`: versioned prompt profiles and templates.
- `workflows/`: pinned image-generation workflows.
- `src/semantic_roundtrip/`: adapters, runtime control, pipeline, persistence,
  analysis and status website.
- `models/`: reproducible model-download scripts.
- `notebooks/`: read-only analysis of completed jobs.
- `runs/`: generated run artifacts; normally mounted outside the repository.

Python dependencies are locked in `uv.lock`. Container images, model revisions
and model checksums are pinned. Existing run snapshots remain historical facts;
editing a live config never changes an earlier run.
