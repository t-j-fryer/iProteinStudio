#!/usr/bin/env python3
"""Generate transparent, publication-style SVG summaries for RFD3 validation."""

from __future__ import annotations

import argparse
import csv
from pathlib import Path

import matplotlib as mpl
import matplotlib.pyplot as plt
import numpy as np


ROOT = Path(__file__).resolve().parents[1]
WRITE_PNG = False
COLORS = {
    "acbx": "#2A6F97",
    "fluorescein": "#B44E75",
    "boltz": "#0072B2",
    "intellifold": "#D55E00",
    "neutral": "#4D5359",
    "light": "#C9CED3",
}


def read_csv(path: Path) -> list[dict[str, str]]:
    with path.open() as handle:
        return list(csv.DictReader(handle))


def style() -> None:
    mpl.rcParams.update({
        "font.family": "sans-serif",
        "font.sans-serif": ["Arial", "Helvetica", "DejaVu Sans"],
        "font.size": 10,
        "axes.labelsize": 11,
        "axes.titlesize": 11,
        "xtick.labelsize": 9.5,
        "ytick.labelsize": 9.5,
        "legend.fontsize": 9,
        "axes.linewidth": 0.9,
        "xtick.major.width": 0.9,
        "ytick.major.width": 0.9,
        "xtick.major.size": 4,
        "ytick.major.size": 4,
        "svg.fonttype": "none",
        "savefig.transparent": True,
    })


def clean_axis(ax) -> None:
    ax.grid(False)
    ax.spines["top"].set_visible(False)
    ax.spines["right"].set_visible(False)


def panel_label(ax, label: str) -> None:
    ax.text(-0.16, 1.08, label, transform=ax.transAxes, fontsize=13, fontweight="bold", va="top")


def save(fig, path: Path) -> None:
    fig.savefig(path, format="svg", transparent=True, bbox_inches="tight", pad_inches=0.05)
    if WRITE_PNG:
        fig.savefig(path.with_suffix(".png"), dpi=240, transparent=True, bbox_inches="tight", pad_inches=0.05)
    plt.close(fig)


def throughput_figure(output: Path) -> None:
    native = read_csv(ROOT / "benchmarks/rfd3_benchmark_summary.csv")
    native = [row for row in native if row["precision"] == "bf16"]
    process = read_csv(ROOT / "benchmarks/rfd3_process_parallel_summary.csv")
    fig, axes = plt.subplots(1, 3, figsize=(10.8, 3.35), constrained_layout=True)

    ax = axes[0]
    for target, label in [("acbx", "aCbx · 60 aa"), ("fluorescein", "Fluorescein · 80 aa")]:
        rows = sorted((r for r in native if r["target"] == target), key=lambda r: int(r["batch_size"]))
        x = [int(r["batch_size"]) for r in rows]
        y = [float(r["sec_per_design"]) for r in rows]
        ax.plot(x, y, "-o", color=COLORS[target], lw=2.0, ms=5.5, label=label)
        best = int(np.argmin(y))
        ax.scatter([x[best]], [y[best]], s=75, facecolors="white", edgecolors=COLORS[target], lw=1.8, zorder=4)
    ax.set_xscale("log", base=2)
    ax.set_xticks([1, 2, 4, 8, 16, 32], labels=["1", "2", "4", "8", "16", "32"])
    ax.set_xlabel("Native MLX batch size")
    ax.set_ylabel("Time per backbone (s)")
    ax.legend(frameon=False, loc="upper left", handlelength=1.7)
    clean_axis(ax)
    panel_label(ax, "a")

    ax = axes[1]
    for target, label in [("acbx", "aCbx"), ("fluorescein", "Fluorescein")]:
        rows = sorted(
            (r for r in native if r["target"] == target and r["peak_physical_footprint_gb"]),
            key=lambda r: int(r["batch_size"]),
        )
        ax.plot(
            [int(r["batch_size"]) for r in rows],
            [float(r["peak_physical_footprint_gb"]) for r in rows],
            "-o", color=COLORS[target], lw=2.0, ms=5.5, label=label,
        )
    ax.set_xscale("log", base=2)
    ax.set_xticks([1, 2, 4, 8, 16, 32], labels=["1", "2", "4", "8", "16", "32"])
    ax.set_xlabel("Native MLX batch size")
    ax.set_ylabel("Peak physical footprint (GB)")
    clean_axis(ax)
    panel_label(ax, "b")

    ax = axes[2]
    x = [int(r["active_processes"]) for r in process]
    y = [float(r["sec_per_design"]) for r in process]
    bars = ax.bar(x, y, width=0.62, color=["#AAB2B8", "#438E8B", "#AAB2B8"], edgecolor="none")
    for bar, row in zip(bars, process, strict=True):
        ax.text(
            bar.get_x() + bar.get_width() / 2,
            bar.get_height() + 0.18,
            f"{float(row['throughput_designs_per_min']):.1f}/min",
            ha="center", va="bottom", fontsize=8.5,
        )
    ax.set_xticks(x)
    ax.set_xlabel("Concurrent RFD3 processes\n(each uses native batch 8)")
    ax.set_ylabel("Time per backbone (s)")
    ax.set_ylim(0, max(y) * 1.18)
    clean_axis(ax)
    panel_label(ax, "c")
    save(fig, output / "figure1_rfd3_batching_and_parallelism.svg")


def predictor_figure(output: Path) -> None:
    fig, axes = plt.subplots(1, 2, figsize=(7.25, 3.35), constrained_layout=True, sharex=True, sharey=True)
    for ax, campaign, title, color, label in [
        (axes[0], "acbx_10", "aCbx protein target", COLORS["acbx"], "a"),
        (axes[1], "fluorescein_10", "Fluorescein", COLORS["fluorescein"], "b"),
    ]:
        rows = read_csv(ROOT / "campaigns" / campaign / "analysis/consensus_ranking.csv")
        x = np.array([float(r["boltz_iptm"]) for r in rows])
        y = np.array([float(r["intellifold_iptm"]) for r in rows])
        ax.plot([0.25, 0.95], [0.25, 0.95], color=COLORS["light"], lw=1.2, zorder=0)
        ax.scatter(x, y, s=48, color=color, edgecolor="white", linewidth=0.7, alpha=0.95)
        best = int(np.argmax(np.minimum(x, y)))
        ax.annotate(
            rows[best]["design"].replace("design_", "D"), (x[best], y[best]),
            xytext=(5, 6), textcoords="offset points", fontsize=8.5, color=COLORS["neutral"],
        )
        ax.set_title(title, loc="left", pad=8)
        ax.set_xlabel("Boltz iPTM")
        ax.set_xlim(0.25, 0.95)
        ax.set_ylim(0.25, 0.95)
        clean_axis(ax)
        panel_label(ax, label)
    axes[0].set_ylabel("IntelliFold iPTM")
    save(fig, output / "figure2_predictor_agreement.svg")


def structural_figure(output: Path) -> None:
    fig, axes = plt.subplots(1, 2, figsize=(7.25, 3.35), constrained_layout=True)
    for ax, campaign, title, label in [
        (axes[0], "acbx_10", "aCbx protein target", "a"),
        (axes[1], "fluorescein_10", "Fluorescein", "b"),
    ]:
        rows = read_csv(ROOT / "campaigns" / campaign / "analysis/design_metrics.csv")
        for predictor in ["boltz", "intellifold"]:
            subset = [r for r in rows if r["predictor_predictor"] == predictor]
            ax.scatter(
                [float(r["binder_ca_self_rmsd"]) for r in subset],
                [float(r["predictor_iptm"]) for r in subset],
                s=42, color=COLORS[predictor], edgecolor="white", linewidth=0.6,
                label="Boltz" if predictor == "boltz" else "IntelliFold", alpha=0.9,
            )
        ax.set_title(title, loc="left", pad=8)
        ax.set_xlabel("Binder self-consistency RMSD (Å)")
        clean_axis(ax)
        panel_label(ax, label)
    axes[0].set_ylabel("iPTM")
    axes[1].legend(frameon=False, loc="lower right")
    save(fig, output / "figure3_confidence_vs_self_consistency.svg")


def exposure_figure(output: Path) -> None:
    rows = read_csv(ROOT / "campaigns/fluorescein_10/analysis/design_metrics.csv")
    fig, axes = plt.subplots(1, 2, figsize=(7.25, 3.35), constrained_layout=True, sharey=True)
    rng = np.random.default_rng(11)
    for ax, predictor, title, label in [
        (axes[0], "boltz", "Boltz refolds", "a"),
        (axes[1], "intellifold", "IntelliFold refolds", "b"),
    ]:
        subset = [r for r in rows if r["predictor_predictor"] == predictor]
        core = np.array([float(r["core_rasa_mean"]) for r in subset])
        linker = np.array([float(r["linker_rasa_mean"]) for r in subset])
        for left, right in zip(core, linker, strict=True):
            ax.plot([0, 1], [left, right], color="#B8BDC2", lw=1.0, alpha=0.8, zorder=0)
        ax.scatter(rng.normal(0, 0.018, len(core)), core, s=38, color="#4D5359", edgecolor="white", lw=0.5)
        ax.scatter(rng.normal(1, 0.018, len(linker)), linker, s=42, color=COLORS["fluorescein"], edgecolor="white", lw=0.5)
        ax.plot([0, 1], [core.mean(), linker.mean()], color="#111111", lw=2.4)
        ax.scatter([0, 1], [core.mean(), linker.mean()], s=62, color="#111111", zorder=4)
        ax.text(0.5, max(core.mean(), linker.mean()) + 0.08, f"Δ = {linker.mean()-core.mean():+.2f}", ha="center", fontsize=9)
        ax.set_xticks([0, 1], ["Buried core\n25 atoms", "Linker\n6 atoms"])
        ax.set_title(title, loc="left", pad=8)
        ax.set_ylim(-0.03, 1.03)
        clean_axis(ax)
        panel_label(ax, label)
    axes[0].set_ylabel("Relative solvent-accessible area")
    save(fig, output / "figure4_fluorescein_atom_exposure.svg")


def main() -> None:
    global WRITE_PNG
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", type=Path, default=ROOT / "figures")
    parser.add_argument("--png-preview", action="store_true", help="Also write PNG previews for QA")
    args = parser.parse_args()
    WRITE_PNG = args.png_preview
    output = args.output.resolve()
    output.mkdir(parents=True, exist_ok=True)
    style()
    throughput_figure(output)
    predictor_figure(output)
    structural_figure(output)
    exposure_figure(output)
    print(f"Wrote 4 SVG figures to {output}")


if __name__ == "__main__":
    main()
