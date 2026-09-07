"""Consistent scientific figures; intervals are supplied by the statistics layer."""

from pathlib import Path

import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
import seaborn as sns

from semantic_roundtrip.analysis.reporting import (
    DOMAINS,
    METRIC,
    QG,
    RATING_KEYS,
    STYLE_METRICS,
    TEXT,
    TITLE_KEYS,
    difference,
    effects,
)
from semantic_roundtrip.analysis.statistics import illustratability_spearman


def save_figure(fig, path, title):
    """Display inline and export a 300-dpi PNG plus vector PDF at the given stem."""
    path = Path(path)
    fig.suptitle(title, fontsize=14, fontweight="bold")
    fig.savefig(path.with_suffix(".png"), dpi=300, bbox_inches="tight")
    fig.savefig(path.with_suffix(".pdf"), bbox_inches="tight")
    plt.show()
    plt.close(fig)


def heatmap(ax, frame, models, title, baseline=None):
    values = (100 * frame.groupby(["pg", "bi"])[METRIC].mean().unstack()).reindex(
        index=models, columns=models
    )
    labels = [m.upper() + ("*" if m == "v4" else "") for m in models]
    if baseline is None:
        cmap = sns.color_palette("blend:#f7fbff,#6baed6", as_cmap=True)
    else:
        reference = (
            100 * baseline.groupby(["pg", "bi"])[METRIC].mean().unstack()
        ).reindex(index=models, columns=models)
        values = values - reference
        cmap = "vlag"
    ax.set_facecolor("#dddddd")
    sns.heatmap(
        values,
        ax=ax,
        annot=True,
        fmt=".1f" if baseline is None else "+.1f",
        vmin=0 if baseline is None else -100,
        vmax=100,
        cmap=cmap,
        cbar=False,
        square=True,
        linewidths=0.5,
        linecolor="white",
        xticklabels=labels,
        yticklabels=labels,
    )
    ax.set(xlabel="BI", ylabel="PG", title=title)
    return ax.collections[0]


def bb_heatmaps(frame, models, name, title):
    fig, axes = plt.subplots(2, 2, figsize=(9, 7), layout="constrained")
    for bb, ax in zip(QG, axes.flat):
        image = heatmap(ax, frame[frame.bb == bb], models, f"BB = {bb.upper()}")
    fig.colorbar(image, ax=list(axes.flat), label="End-to-end Strict Exact Match (%)")
    save_figure(fig, name, title)


def interval_plot(
    ax, table, xlabel="Difference (pp), paired 95% CI", zero=True, colors=None
):
    for position, row in enumerate(table.itertuples()):
        color = colors[position] if colors is not None else "#0072B2"
        if pd.isna(row.estimate):
            ax.text(0.5, position, "n/a", transform=ax.get_yaxis_transform())
            continue
        has_interval = pd.notna(row.ci95_low) and pd.notna(row.ci95_high)
        if has_interval:
            ax.hlines(position, row.ci95_low, row.ci95_high, color=color, linewidth=1.8)
            ax.vlines(
                [row.ci95_low, row.ci95_high],
                position - 0.045,
                position + 0.045,
                color=color,
                linewidth=1.5,
            )
        ax.plot(row.estimate, position, "o", color=color, markersize=6)
        value = f"{row.estimate:+.1f}" if zero else f"{row.estimate:.1f}"
        ax.annotate(
            value if has_interval else f"{value} (CI n/a)",
            (row.estimate, position),
            xytext=(0, 9),
            textcoords="offset points",
            ha="center",
            color=color,
            fontsize=9,
            fontweight="bold",
        )
    ax.set(
        yticks=range(len(table)),
        yticklabels=table.comparison.str.replace("−", "-", regex=False),
        xlabel=xlabel,
        ylim=(len(table) - 0.5, -0.6),
    )
    if zero:
        ax.axvline(0, color="#555555", linestyle="--", linewidth=1)
    ax.margins(x=0.12)
    ax.grid(axis="x", color="#D9D9D9", linewidth=0.8)
    ax.grid(axis="y", visible=False)
    sns.despine(ax=ax)


def correlation_label(row):
    rho = "n/a" if pd.isna(row.spearman_rho) else f"{row.spearman_rho:.2f}"
    interval = (
        "n/a"
        if pd.isna(row.ci95_low) or pd.isna(row.ci95_high)
        else f"[{row.ci95_low:.2f}, {row.ci95_high:.2f}]"
    )
    return f"ρ={rho}, 95% CI {interval}"


def rating_analysis(ratings, frame, name, title):
    ratings = ratings.reindex(columns=["entry_name", *TITLE_KEYS, "score"]).copy()
    ratings["pg"] = ratings.entry_name.astype("string").str.extract(
        "_pg_([^_]+)_", expand=False
    )
    outcomes = frame.groupby(RATING_KEYS, as_index=False)[METRIC].mean()
    models = [m for m in QG + TEXT if m in outcomes.pg.values]
    table = illustratability_spearman(ratings, outcomes).set_index("pg").reindex(models)
    table["titles"] = table.titles.astype("Int64").fillna(0)
    table["missing_ratings"] = outcomes.groupby("pg").size() - table.titles
    pairs = outcomes.merge(ratings[[*RATING_KEYS, "score"]], on=RATING_KEYS).dropna(
        subset=["score"]
    )
    pairs["accuracy_percent"] = 100 * pairs[METRIC]
    fig, axes = plt.subplots(
        1,
        len(models),
        figsize=(3.5 * len(models), 4),
        squeeze=False,
        layout="constrained",
    )
    for model, ax in zip(models, axes.flat):
        sns.scatterplot(
            data=pairs[pairs.pg == model],
            x="score",
            y="accuracy_percent",
            hue="domain",
            style="domain",
            hue_order=list(DOMAINS),
            style_order=list(DOMAINS),
            palette={domain: style[0] for domain, style in DOMAINS.items()},
            markers={domain: style[1] for domain, style in DOMAINS.items()},
            alpha=0.7,
            ax=ax,
            legend=model == models[0],
        )
        row = table.loc[model]
        ax.set(
            title=f"{model.upper()}\n{correlation_label(row)}\nn={int(row.titles)}",
            xlabel="Illustratability (0–100)",
            ylabel="Mean title accuracy (%)",
            xlim=(-2, 102),
            ylim=(-2, 102),
        )
    axes[0, 0].legend(fontsize=8, title="Domain")
    save_figure(fig, name, title)
    return (table.reset_index(), pairs)


def paired_style_analysis(positive, negative, label, reference_label, slug, output_dir):
    comparison = f"{label} - {reference_label}"
    fig, axes = plt.subplots(1, 3, figsize=(15, 4.8), layout="constrained")
    image = heatmap(axes[0], negative, QG, reference_label)
    heatmap(axes[1], positive, QG, label)
    delta = heatmap(axes[2], positive, QG, comparison, baseline=negative)
    fig.colorbar(image, ax=list(axes[:2]), label="End-to-end Strict Exact Match (%)")
    fig.colorbar(delta, ax=axes[2], label="Difference (pp)")
    save_figure(fig, output_dir / f"direct_{slug}_matrices", f"SQ2: {comparison}")
    reference_scores = negative.assign(
        condition_style=lambda f: "reference__" + f.condition.astype(str)
    )
    comparison_scores = positive.assign(
        condition_style=lambda f: "comparison__" + f.condition.astype(str)
    )
    combined = pd.concat([reference_scores, comparison_scores], ignore_index=True)
    contrasts = {
        f"Overall: {comparison}": difference(
            comparison_scores.condition_style.unique(),
            reference_scores.condition_style.unique(),
        )
    }
    for role in ["pg", "bi"]:
        for model in QG:
            contrasts[f"{role.upper()}={model.upper()}: {comparison}"] = difference(
                comparison_scores.loc[
                    comparison_scores[role] == model, "condition_style"
                ].unique(),
                reference_scores.loc[
                    reference_scores[role] == model, "condition_style"
                ].unique(),
            )
    table = effects(combined, contrasts, condition_column="condition_style")
    plotted = table[table.domain == "all"].copy()
    plotted["comparison"] = plotted.comparison.str.split(":").str[0]
    fig, ax = plt.subplots(figsize=(9, 6), layout="constrained")
    interval_plot(ax, plotted)
    save_figure(fig, output_dir / f"direct_{slug}_effects", f"SQ2: {comparison}")
    return table


def style_accuracy_panel(ax, frame, styles):
    offsets = np.linspace(-0.24, 0.24, len(STYLE_METRICS))
    for offset, (label, _, color, marker) in zip(
        offsets, STYLE_METRICS.values(), strict=True
    ):
        values = frame[frame.metric.eq(label)].set_index("style").reindex(styles)
        available = values.accuracy_percent.notna()
        if not available.any():
            continue
        values = values[available]
        positions = np.arange(len(styles))[available] + offset
        ax.errorbar(
            positions,
            values.accuracy_percent,
            yerr=np.vstack(
                [
                    values.accuracy_percent - values.ci95_low,
                    values.ci95_high - values.accuracy_percent,
                ]
            ),
            fmt=marker,
            color=color,
            capsize=2,
            markersize=5,
            label=label,
        )
    ax.set(
        xticks=range(len(styles)),
        xticklabels=list(styles),
        ylim=(0, 100),
        xlim=(-0.5, len(styles) - 0.5),
    )
    ax.tick_params(axis="x", rotation=30, labelsize=9)
