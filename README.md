# Semantic Roundtrip

Semantic Roundtrip evaluates whether cultural titles (songs, movies, and band names) can be reconstructed after being translated into an image by AI models without human feedback.

![Pipeline and verification checks](diagrams/pipeline.svg)

The framework benchmarks both direct reconstruction (image to title) and description-mediated reconstruction (image to text description to title), enforcing automated verification checks to prevent textual title leakage.

## Quick start

Requirements: Python 3.12+ and [`uv`](https://docs.astral.sh/uv/).

```bash
uv sync --extra analysis --extra web
uv run semantic-roundtrip run start --config configs/experiments/mock.yaml
uv run semantic-roundtrip run list
```

Use `uv run semantic-roundtrip --help` for the full CLI reference.

## Documentation

- [`EXPERIMENTS.md`](EXPERIMENTS.md): step-by-step reproduction of the main, four-style, and supplementary thesis experiments.
- [`RUNNING.md`](RUNNING.md): shared DGX/cluster setup, model downloads, Docker services, and execution control.
- [`configs/README.md`](configs/README.md): configuration guide for datasets, experiments, and inherited jobs.
- [`configs/datasets/final_titles_v1.md`](configs/datasets/final_titles_v1.md): dataset construction rules and sources (ListenBrainz and IMDb).
- [`manual_evaluation/README.md`](manual_evaluation/README.md): manual audit protocol for prompt and image verification.
- [`artifacts/candidate_illustratability/`](artifacts/candidate_illustratability/README.md): 900-candidate rating distribution and reproduction.
- [`notebooks/`](notebooks/): Jupyter notebooks generating the thesis figures and tables (`final_study.ipynb`, `style_decision.ipynb`, `illustratability_distribution.ipynb`).

## Repository map

- `configs/`: datasets, backends, experiment configurations, and job definitions.
- `prompts/`: versioned YAML chat profiles for prompting, describing, and guessing.
- `workflows/`: pinned image-generation workflows.
- `src/semantic_roundtrip/`: pipeline engine, model adapters, verification checks, CLI, and web status interface.
- `models/`: reproducible model download scripts.
- `notebooks/`: analysis and plotting code for completed runs.
- `artifacts/`: published ratings and verification audit datasets.
- `runs/`: generated execution outputs and SQLite run databases.

## Thesis & Reproducibility

This repository contains the software and experimental configurations for the bachelor thesis *Semantic Roundtrip: End-to-End Evaluation of AI Drawing and Guessing* (TU Wien). 

All experiments use locked Python dependencies (`uv.lock`), pinned container images, fixed random seeds, and immutable run snapshots.
