#!/usr/bin/env python3
"""Create publication-style SVG summaries from audited validation tables."""

from __future__ import annotations

import argparse
import csv
import os
from pathlib import Path

os.environ.setdefault("MPLCONFIGDIR", "/tmp/iproteinstudio-validation-matplotlib")
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt


def style() -> None:
    plt.rcParams.update({
        "font.family": "Arial",
        "font.size": 8,
        "axes.edgecolor": "black",
        "axes.labelcolor": "black",
        "axes.linewidth": 0.8,
        "xtick.color": "black",
        "ytick.color": "black",
        "xtick.direction": "in",
        "ytick.direction": "in",
        "svg.fonttype": "none",
    })


def load(path: Path) -> list[dict[str, str]]:
    with path.open(newline="") as handle:
        return list(csv.DictReader(handle))


def speed_figure(rows: list[dict[str, str]], output: Path) -> None:
    rows = [row for row in rows if row["wall_seconds"]]
    if not rows:
        return
    engines = list(dict.fromkeys(row["engine"] for row in rows))
    arms = list(dict.fromkeys(row["arm"] for row in rows))
    width = 0.78 / max(1, len(arms))
    fig, ax = plt.subplots(figsize=(7.2, 3.2))
    for arm_index, arm in enumerate(arms):
        values = []
        for engine in engines:
            match = next((row for row in rows if row["engine"] == engine and row["arm"] == arm), None)
            values.append(float(match["wall_seconds"]) / 60 if match else 0)
        positions = [index - 0.39 + width / 2 + arm_index * width for index in range(len(engines))]
        ax.bar(positions, values, width=width, label=arm.replace("_", " "),
               edgecolor="black", linewidth=0.7)
    ax.set_ylabel("Campaign wall time (min)")
    ax.set_xticks(range(len(engines)), [item.replace("_", "\n") for item in engines])
    ax.tick_params(top=False, right=False)
    ax.spines["top"].set_visible(False)
    ax.spines["right"].set_visible(False)
    ax.grid(False)
    ax.legend(frameon=False, fontsize=7)
    fig.tight_layout()
    fig.savefig(output, transparent=True)
    plt.close(fig)


def secondary_figure(rows: list[dict[str, str]], output: Path) -> None:
    if not rows:
        return
    labels = [f"{row['engine']}\n{row['arm']}" for row in rows]
    helix = [100 * float(row["helix_fraction"]) for row in rows]
    sheet = [100 * float(row["sheet_fraction"]) for row in rows]
    coil = [100 * float(row["coil_fraction"]) for row in rows]
    fig, ax = plt.subplots(figsize=(7.2, 3.4))
    positions = range(len(rows))
    ax.bar(positions, helix, label="Helix", edgecolor="black", linewidth=0.7)
    ax.bar(positions, sheet, bottom=helix, label="Sheet", edgecolor="black", linewidth=0.7)
    bottoms = [h + s for h, s in zip(helix, sheet)]
    ax.bar(positions, coil, bottom=bottoms, label="Coil", edgecolor="black", linewidth=0.7)
    ax.set_ylabel("Binder residues (%)")
    ax.set_ylim(0, 100)
    ax.set_xticks(list(positions), labels, rotation=35, ha="right")
    ax.tick_params(top=False, right=False)
    ax.spines["top"].set_visible(False)
    ax.spines["right"].set_visible(False)
    ax.grid(False)
    ax.legend(frameon=False, ncol=3, fontsize=7)
    fig.tight_layout()
    fig.savefig(output, transparent=True)
    plt.close(fig)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--analysis", type=Path, required=True)
    args = parser.parse_args()
    analysis = args.analysis.resolve()
    style()
    speed = analysis / "campaign_summary.csv"
    if speed.is_file():
        speed_figure(load(speed), analysis / "campaign_wall_time.svg")
    secondary = analysis / "secondary_structure_summary.csv"
    if secondary.is_file():
        secondary_figure(load(secondary), analysis / "secondary_structure.svg")
    caption = analysis / "FIGURE_CAPTIONS.md"
    caption.write_text(
        "# Validation figure captions\n\n"
        "**Campaign wall time.** End-to-end wall time for complete iterative-design "
        "campaigns. Each bar is one 12-trajectory campaign with cycle 00 plus five "
        "design cycles; cycle 00 is not counted as a design. Scheduler contrasts "
        "within an engine use identical seeds, sample counts and cached target MSA.\n\n"
        "**Designed-binder secondary structure.** Biotite P-SEA assignments for binder "
        "chain A from cycles 01–05 only, pooled as explicitly tabulated residues. Bars show residue "
        "fractions and are descriptive; trajectory-level replicate statistics must be "
        "reported separately before inferential claims.\n"
    )


if __name__ == "__main__":
    main()
