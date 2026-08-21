"""Small figure set driven directly by the declared study groups."""

from dataclasses import dataclass
from pathlib import Path

import matplotlib

matplotlib.use("Agg")

from matplotlib import pyplot as plt  # noqa: E402
from matplotlib.figure import Figure  # noqa: E402
from matplotlib.ticker import FuncFormatter, PercentFormatter  # noqa: E402

from semantic_roundtrip.analysis.config import StudyGroup  # noqa: E402
from semantic_roundtrip.analysis.models import (  # noqa: E402
    ComparisonSummary,
    ConditionSummary,
)


@dataclass(frozen=True, slots=True)
class PlotResult:
    generated: tuple[str, ...]
    omitted: dict[str, str]


def _save(figure: Figure, output_directory: Path, group_id: str) -> str:
    figure.tight_layout()
    png_name = f"{group_id}.png"
    figure.savefig(
        output_directory / png_name,
        dpi=300,
        bbox_inches="tight",
        metadata={"Creator": "semantic-roundtrip"},
    )
    plt.close(figure)
    return png_name


def _percentage_point_label(value: float, _position: float) -> str:
    if abs(value) < 1e-12:
        return "0 pp"
    return f"{value * 100:+.0f} pp"


def _condition_label(condition_id: str, labels: dict[str, str]) -> str:
    return labels.get(condition_id, condition_id)


def _accuracy_figure(
    *,
    group_id: str,
    group: StudyGroup,
    summaries: tuple[ConditionSummary, ...],
    labels: dict[str, str],
) -> Figure | None:
    rows = [
        row
        for row in summaries
        if row.condition_id in group.conditions and row.route == group.route
    ]
    if not rows:
        return None

    lookup = {(row.condition_id, row.domain): row for row in rows}
    domains = ["all", *sorted({row.domain for row in rows if row.domain != "all"})]
    figure, axis = plt.subplots(figsize=(max(7, len(group.conditions) * 1.5), 4.8))
    center_positions = list(range(len(group.conditions)))
    width = 0.16
    colors = ["#111827", "#2563eb", "#059669", "#d97706"]
    offsets = [
        (index - (len(domains) - 1) / 2) * width for index in range(len(domains))
    ]

    for domain_index, domain in enumerate(domains):
        x_values: list[float] = []
        y_values: list[float] = []
        lower: list[float] = []
        upper: list[float] = []
        for position, condition_id in zip(
            center_positions,
            group.conditions,
            strict=True,
        ):
            row = lookup.get((condition_id, domain))
            if row is None:
                continue
            value = row.end_to_end_strict_accuracy
            low = row.ci95_low if row.ci95_low is not None else value
            high = row.ci95_high if row.ci95_high is not None else value
            x_values.append(position + offsets[domain_index])
            y_values.append(value)
            lower.append(max(0.0, value - low))
            upper.append(max(0.0, high - value))
        axis.errorbar(
            x_values,
            y_values,
            yerr=[lower, upper],
            fmt="o",
            capsize=3,
            color=colors[domain_index % len(colors)],
            label="overall" if domain == "all" else domain,
        )

    axis.set_xticks(
        center_positions,
        [_condition_label(value, labels) for value in group.conditions],
        rotation=20,
        ha="right",
    )
    axis.set_ylim(-0.02, 1.02)
    axis.set_ylabel("End-to-end strict exact accuracy")
    axis.yaxis.set_major_formatter(PercentFormatter(xmax=1.0, decimals=0))
    axis.set_title(group_id.replace("_", " ").title())
    axis.grid(axis="y", alpha=0.25)
    axis.legend(title="Domain")
    return figure


def _comparison_figure(
    *,
    group_id: str,
    group: StudyGroup,
    comparisons: tuple[ComparisonSummary, ...],
    labels: dict[str, str],
) -> Figure | None:
    rows = [
        row
        for row in comparisons
        if row.group_id == group_id
    ]
    if not rows:
        return None

    condition_ids = [
        condition_id
        for condition_id in group.conditions
        if group.kind == "routes" or condition_id != group.reference
    ]
    domains = ["all", *sorted({row.domain for row in rows if row.domain != "all"})]
    lookup = {(row.condition_id, row.domain): row for row in rows}
    positions = list(range(len(condition_ids)))
    width = 0.16
    colors = ["#111827", "#2563eb", "#059669", "#d97706"]
    offsets = [
        (index - (len(domains) - 1) / 2) * width for index in range(len(domains))
    ]
    figure, axis = plt.subplots(figsize=(max(7, len(condition_ids) * 1.6), 4.8))

    for domain_index, domain in enumerate(domains):
        x_values: list[float] = []
        y_values: list[float] = []
        lower: list[float] = []
        upper: list[float] = []
        for position, condition_id in zip(positions, condition_ids, strict=True):
            row = lookup.get((condition_id, domain))
            if row is None:
                continue
            value = row.difference
            low = row.ci95_low if row.ci95_low is not None else value
            high = row.ci95_high if row.ci95_high is not None else value
            x_values.append(position + offsets[domain_index])
            y_values.append(value)
            lower.append(max(0.0, value - low))
            upper.append(max(0.0, high - value))
        axis.errorbar(
            x_values,
            y_values,
            yerr=[lower, upper],
            fmt="o",
            capsize=3,
            color=colors[domain_index % len(colors)],
            label="overall" if domain == "all" else domain,
        )

    axis.axhline(0, color="black", linewidth=1)
    axis.yaxis.set_major_formatter(FuncFormatter(_percentage_point_label))
    axis.set_xticks(
        positions,
        [_condition_label(condition_id, labels) for condition_id in condition_ids],
        rotation=20,
        ha="right",
    )
    if group.kind == "routes":
        axis.set_ylabel("Difference in end-to-end strict exact accuracy")
        explanation = (
            "Description - direct; positive = description better, "
            "negative = direct better"
        )
    else:
        reference = _condition_label(rows[0].reference_condition_id, labels)
        axis.set_ylabel("Difference in end-to-end strict exact accuracy")
        explanation = (
            f"Condition - {reference}; positive = condition better, "
            f"negative = {reference} better"
        )
    axis.set_title(
        f"{group_id.replace('_', ' ').title()}\n{explanation}",
    )
    axis.grid(axis="y", alpha=0.25)
    axis.legend(title="Domain")
    return figure


def create_figures(
    output_directory: Path,
    *,
    groups: dict[str, StudyGroup],
    labels: dict[str, str],
    summaries: tuple[ConditionSummary, ...],
    comparisons: tuple[ComparisonSummary, ...],
) -> PlotResult:
    """Create one high-resolution PNG for every applicable study group."""
    output_directory.mkdir()
    generated: list[str] = []
    omitted: dict[str, str] = {}
    for group_id, group in groups.items():
        if group.kind == "accuracy":
            figure = _accuracy_figure(
                group_id=group_id,
                group=group,
                summaries=summaries,
                labels=labels,
            )
        else:
            figure = _comparison_figure(
                group_id=group_id,
                group=group,
                comparisons=comparisons,
                labels=labels,
            )

        if figure is None:
            omitted[group_id] = "The selected runs do not contain the required rows."
            continue
        generated.append(_save(figure, output_directory, group_id))

    return PlotResult(generated=tuple(generated), omitted=omitted)
