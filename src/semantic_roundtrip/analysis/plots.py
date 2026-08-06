"""Small deterministic figure set generated from exported analysis rows."""

from dataclasses import dataclass
from pathlib import Path

import matplotlib

matplotlib.use("Agg")

from matplotlib import pyplot as plt  # noqa: E402
from matplotlib.figure import Figure  # noqa: E402

from semantic_roundtrip.analysis.models import PredictionRecord  # noqa: E402
from semantic_roundtrip.analysis.summaries import (  # noqa: E402
    PairedRouteDifference,
    PairedRouteSummary,
    StackDomainRouteSummary,
)


@dataclass(frozen=True, slots=True)
class PlotResult:
    generated: tuple[str, ...]
    omitted: dict[str, str]


def _label(entry: str | None, experiment: str, route: str | None = None) -> str:
    base = entry or experiment
    if route is not None:
        base = f"{base} · {route}"
    return base if len(base) <= 34 else f"{base[:31]}..."


def _save(figure: Figure, path: Path) -> None:
    figure.tight_layout()
    figure.savefig(
        path,
        dpi=160,
        bbox_inches="tight",
        metadata={"Software": "semantic-roundtrip"},
    )
    plt.close(figure)


def _stack_route_accuracy(
    summaries: tuple[StackDomainRouteSummary, ...],
    path: Path,
) -> bool:
    rows = [row for row in summaries if row.domain == "all"]
    if not rows:
        return False

    labels = [_label(row.job_entry, row.experiment_name, row.route) for row in rows]
    values = [row.mean_title_accuracy for row in rows]
    lower = [
        value - (row.ci95_low if row.ci95_low is not None else value)
        for row, value in zip(rows, values, strict=True)
    ]
    upper = [
        (row.ci95_high if row.ci95_high is not None else value) - value
        for row, value in zip(rows, values, strict=True)
    ]
    figure, axis = plt.subplots(figsize=(max(7, len(rows) * 1.15), 4.5))
    positions = list(range(len(rows)))
    axis.errorbar(
        positions,
        values,
        yerr=[lower, upper],
        fmt="o",
        capsize=4,
        color="#1f5d8f",
    )
    axis.set_xticks(positions, labels, rotation=25, ha="right")
    axis.set_ylim(-0.02, 1.02)
    axis.set_ylabel("Mean title-level exact accuracy")
    axis.set_title("Complete-stack accuracy by reconstruction route")
    axis.grid(axis="y", alpha=0.25)
    _save(figure, path)
    return True


def _domain_heatmap(
    summaries: tuple[StackDomainRouteSummary, ...],
    path: Path,
) -> bool:
    rows = [row for row in summaries if row.domain != "all"]
    if not rows:
        return False
    labels = list(
        dict.fromkeys(
            _label(row.job_entry, row.experiment_name, row.route) for row in rows
        )
    )
    domains = sorted({row.domain for row in rows})
    lookup = {
        (_label(row.job_entry, row.experiment_name, row.route), row.domain): (
            row.mean_title_accuracy
        )
        for row in rows
    }
    matrix = [
        [lookup.get((label, domain), float("nan")) for domain in domains]
        for label in labels
    ]

    figure, axis = plt.subplots(
        figsize=(max(6, len(domains) * 1.4), max(3.5, len(labels) * 0.6))
    )
    image = axis.imshow(matrix, vmin=0, vmax=1, cmap="Blues", aspect="auto")
    axis.set_xticks(range(len(domains)), domains)
    axis.set_yticks(range(len(labels)), labels)
    axis.set_title("Title-level exact accuracy by domain")
    for row_index, values in enumerate(matrix):
        for column_index, value in enumerate(values):
            if value == value:
                axis.text(
                    column_index,
                    row_index,
                    f"{value:.2f}",
                    ha="center",
                    va="center",
                    color="black" if value < 0.65 else "white",
                )
    figure.colorbar(image, ax=axis, label="Accuracy")
    _save(figure, path)
    return True


def _direct_vs_description(
    differences: tuple[PairedRouteDifference, ...],
    summaries: tuple[PairedRouteSummary, ...],
    path: Path,
) -> bool:
    overall = [row for row in summaries if row.domain == "all"]
    if not overall:
        return False

    values_by_run: dict[str, list[float]] = {}
    for row in differences:
        values_by_run.setdefault(row.run_id, []).append(
            row.difference_description_minus_direct
        )

    figure, axis = plt.subplots(figsize=(max(6, len(overall) * 1.5), 4.5))
    labels: list[str] = []
    for position, summary in enumerate(overall):
        labels.append(_label(summary.job_entry, summary.experiment_name))
        values = values_by_run.get(summary.run_id, [])
        axis.scatter([position] * len(values), values, alpha=0.65, color="#1f5d8f")
        mean = summary.mean_difference_description_minus_direct
        low = summary.ci95_low if summary.ci95_low is not None else mean
        high = summary.ci95_high if summary.ci95_high is not None else mean
        axis.errorbar(
            [position],
            [mean],
            yerr=[[mean - low], [high - mean]],
            fmt="D",
            capsize=4,
            color="#b42318",
            label="Mean and 95% interval" if position == 0 else None,
        )
    axis.axhline(0, color="black", linewidth=1)
    axis.set_xticks(range(len(overall)), labels, rotation=20, ha="right")
    axis.set_ylabel("Description accuracy − direct accuracy")
    axis.set_title("Paired route differences with title-bootstrap intervals")
    axis.grid(axis="y", alpha=0.25)
    axis.legend()
    _save(figure, path)
    return True


def _confidence_diagnostic(
    records: tuple[PredictionRecord, ...],
    path: Path,
) -> bool:
    grouped: dict[tuple[str, str, str, str], list[float]] = {}
    for record in records:
        if (
            record.confidence is None
            or record.exact_match is None
            or record.verification_passed is not True
        ):
            continue
        correctness = "correct" if record.exact_match else "incorrect"
        confidence_type = record.confidence_type or "unspecified"
        grouped.setdefault(
            (
                record.prediction_model,
                record.route,
                confidence_type,
                correctness,
            ),
            [],
        ).append(record.confidence)
    if not grouped:
        return False

    ordered = sorted(grouped.items())
    labels = [
        (
            f"{model if len(model) <= 25 else model[:22] + '...'}\n"
            f"{route} · {confidence_type}\n{correctness}"
        )
        for (model, route, confidence_type, correctness), _ in ordered
    ]
    values = [values for _, values in ordered]
    figure, axis = plt.subplots(figsize=(max(7, len(values) * 1.2), 4.5))
    axis.boxplot(values, tick_labels=labels, showmeans=True)
    axis.set_ylabel("Token-derived confidence")
    axis.set_title("Confidence by prediction model and route")
    axis.tick_params(axis="x", rotation=20)
    axis.grid(axis="y", alpha=0.25)
    _save(figure, path)
    return True


def create_figures(
    output_directory: Path,
    *,
    records: tuple[PredictionRecord, ...],
    summaries: tuple[StackDomainRouteSummary, ...],
    differences: tuple[PairedRouteDifference, ...],
    route_summaries: tuple[PairedRouteSummary, ...],
) -> PlotResult:
    """Create each applicable thesis figure and record omitted ones."""
    output_directory.mkdir()
    specifications = (
        (
            "stack_route_accuracy.png",
            lambda path: _stack_route_accuracy(summaries, path),
            "No stack-route summary rows were available.",
        ),
        (
            "domain_heatmap.png",
            lambda path: _domain_heatmap(summaries, path),
            "No domain-specific summary rows were available.",
        ),
        (
            "direct_vs_description.png",
            lambda path: _direct_vs_description(
                differences,
                route_summaries,
                path,
            ),
            "Both routes were not available for any title.",
        ),
        (
            "confidence_diagnostic.png",
            lambda path: _confidence_diagnostic(records, path),
            "No verifier-passed predictions contained confidence values.",
        ),
    )
    generated: list[str] = []
    omitted: dict[str, str] = {}
    for filename, create, reason in specifications:
        if create(output_directory / filename):
            generated.append(filename)
        else:
            omitted[filename] = reason
    return PlotResult(generated=tuple(generated), omitted=omitted)
