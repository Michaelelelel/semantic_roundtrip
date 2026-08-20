# Semantic Roundtrip

Semantic Roundtrip is an experiment pipeline for measuring whether a title
can be reconstructed after passing through text and image generation models.
It is developed for a bachelor's thesis and records the complete path from inputs
to results so model stacks can be compared reproducibly.

```text
title + domain
  -> visual prompt
  -> generated image
  -> image verification
  -> direct title prediction
  -> optional image description -> title prediction
  -> exact and normalized-exact evaluation
```

Every run stores its resolved configuration, prompt and workflow snapshots, raw
model responses, generated images, task state, errors, and evaluation results in
its run directory. Jobs execute multiple independent runs sequentially.

## Project structure

- `configs/`: datasets, backends, experiments, jobs, and deployment catalogs
- `prompts/`: versioned prompt profiles and templates
- `src/semantic_roundtrip/adapters/`: inference-service interfaces
- `src/semantic_roundtrip/runtime/`: model loading and unloading
- `src/semantic_roundtrip/pipeline/`: stage orchestration
- `src/semantic_roundtrip/persistence/`: SQLite run and job state
- `src/semantic_roundtrip/analysis/`: result extraction, metrics, CSV files, and plots
- `src/semantic_roundtrip/status/` and `web/`: read-only status views
- `models/` and `chat_templates/`: reproducible download scripts

## Local mock smoke test

The mock pipeline requires no model downloads or GPU:

```bash
python3.14 -m venv .venv
source .venv/bin/activate
pip install --constraint requirements.lock -e ".[analysis,web]"

semantic-roundtrip run start --config configs/experiments/mock.yaml
semantic-roundtrip run list
```

Use `semantic-roundtrip --help`, `semantic-roundtrip run --help`, or
`semantic-roundtrip job --help` for the available commands.

## DGX setup and experiments

See [setupproject.md](setupproject.md) for storage setup, model downloads, Docker
Compose commands, status monitoring, pause/resume, matrix execution, and result
export. Python dependencies are fixed in `requirements.lock`, container images are
pinned by digest, and model downloads use fixed revisions and SHA-256 checksums.
