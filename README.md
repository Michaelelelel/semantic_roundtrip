# Semantic Roundtrip

Semantic Roundtrip evaluates whether cultural titles (songs, movies, and band names) can be reconstructed after being translated into an image by AI models without human feedback.

![Pipeline and verification checks](diagrams/pipeline.svg)

The framework benchmarks both direct reconstruction (image to title) and description-mediated reconstruction (image to text description to title). Automated checks identify written-title leakage when scoring the results.

## Quick start

Requirements: Python 3.14 and [`uv`](https://docs.astral.sh/uv/).

```bash
uv sync --frozen --extra analysis --extra web
uv run semantic-roundtrip run start --config configs/experiments/mock.yaml
uv run semantic-roundtrip run list
```

Use `uv run semantic-roundtrip --help` for the full CLI reference.

## Documentation

- [`EXPERIMENTS.md`](EXPERIMENTS.md): step-by-step reproduction of the main, four-style, and supplementary thesis experiments.
- [`RUNNING.md`](RUNNING.md): shared DGX/cluster setup, model downloads, Docker services, and execution control.
- [`configs/README.md`](configs/README.md): configuration guide for datasets, experiments, and inherited jobs.
- [Datasets and sources](configs/README.md#thesis-dataset): supplied title sets and their origins.
- [`manual_evaluation/README.md`](manual_evaluation/README.md): manual audit protocol for prompt and image verification.
- [`artifacts/candidate_illustratability/`](artifacts/candidate_illustratability/): saved candidate ratings and their distribution plot.
- [`notebooks/`](notebooks/): study analysis and report generation (`final_study.ipynb`, `style_decision.ipynb`, `illustratability_distribution.ipynb`).

## Repository map

- `configs/`: datasets, backends, experiment configurations, and job definitions.
- `prompts/`: versioned YAML chat profiles for prompting, describing, and guessing.
- `workflows/`: pinned image-generation workflows.
- `src/semantic_roundtrip/`: pipeline engine, model adapters, verification checks, CLI, and web status interface.
- `models/`: reproducible model download scripts.
- `notebooks/`: analysis and plotting code for completed runs.
- `artifacts/`: saved candidate-rating job and distribution plot.
- `runs/`: generated execution outputs and SQLite run databases.

## Thesis & Reproducibility

This repository contains the software and experimental configurations for the bachelor thesis *From Titles to Images and Back: Evaluating AI Models in a Drawing-and-Guessing Task* (TU Wien).

Experiments use locked Python dependencies (`uv.lock`), pinned local container images, fixed random seeds and frozen run snapshots. Aqueduct manages its hosted model deployment.
