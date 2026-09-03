# Semantic Roundtrip

Semantic Roundtrip measures whether a title remains recognizable after models
translate it through an image.

![Pipeline and verification checks](diagrams/pipeline.svg)

[Editable Mermaid source](diagrams/pipeline.mmd). Every current run persists
three verification decisions: a deterministic prompt-title check, a blind image
check for any readable meaningful text, and a title-aware image check for the
reference title only. They affect evaluation but never prevent image generation
or reconstruction.

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

## Choose an experiment workflow

- [Reproduce the thesis experiments](EXPERIMENTS.md): main jobs, the complete
  four-style comparison, supplementary jobs and analysis.

`job plan` is an optional read-only overview, not a required start step.
Smokes and six-title previews are optional deployment checks, not final results.

## Documentation

- [`RUNNING.md`](RUNNING.md): shared DGX setup, model downloads, services,
  monitoring, resume and optional deployment checks.
- [`configs/README.md`](configs/README.md): create experiments, derived runs and
  jobs.
- [`configs/jobs/final_study/STUDY_DESIGN.md`](configs/jobs/final_study/STUDY_DESIGN.md):
  concise executable study protocol.
- [`configs/datasets/final_titles_v1.md`](configs/datasets/final_titles_v1.md):
  dataset construction and sources.
- [`manual_evaluation/README.md`](manual_evaluation/README.md): manual verifier,
  sketch and comic checks.
- [`notebooks/final_study.ipynb`](notebooks/final_study.ipynb): thesis figures (RQ1–RQ4, SQ1–SQ3).
- [`notebooks/style_decision.ipynb`](notebooks/style_decision.ipynb): complete four-style 4 x 4 comparison.
- [`notebooks/illustratability_distribution.ipynb`](notebooks/illustratability_distribution.ipynb): 900-candidate rating distribution.
- [`artifacts/candidate_illustratability/`](artifacts/candidate_illustratability/README.md):
  completed 900-title ratings, distribution and model-free reproduction.

Scientific motivation, related work, methodological argument and interpretation
belong in the bachelor thesis. Repository Markdown documents operation and the
versioned executable protocol.

## Repository map

- `configs/`: datasets, backends, experiments, jobs and deployment catalogs.
- `prompts/`: versioned YAML chat profiles with explicit message roles.
- `workflows/`: pinned image-generation workflows.
- `src/semantic_roundtrip/`: adapters, runtime control, pipeline, persistence,
  analysis and status website.
- `models/`: reproducible model-download scripts.
- `notebooks/`: read-only analysis of completed jobs.
- `artifacts/`: published evidence with source jobs and reproduction instructions.
- `runs/`: generated run artifacts; normally mounted outside the repository.

Python dependencies are locked in `uv.lock`. Container images, model revisions
and model checksums are pinned. Existing run snapshots remain historical facts;
editing a live config never changes an earlier run.
