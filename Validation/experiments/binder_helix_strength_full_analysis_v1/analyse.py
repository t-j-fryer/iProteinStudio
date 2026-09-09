#!/usr/bin/env python3
"""Recheck frozen v7 binding results and export the complete figure package."""
from __future__ import annotations

import base64
import csv
from datetime import datetime, timezone
import hashlib
import importlib.util
import json
from pathlib import Path
import random
import statistics
import sys
import warnings
import zipfile

import numpy as np
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.backends.backend_pdf import PdfPages
from matplotlib.lines import Line2D
from matplotlib.patches import Patch


ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0,str(ROOT/'Validation/experiments/helix_strength_full_analysis_v1'))
import campaign_timing
STUDY = ROOT / "Validation/output/binder_helix_strength_all_engines_v7"
OUT = STUDY / "analysis/full_analysis_v1"
EXPERIMENT = ROOT / "Validation/experiments/binder_helix_strength_all_engines_v7"
ENGINES = [
    "boltz", "intellifold_flash", "intellifold_full", "protenix_v2",
    "protenix_mini", "protenix_constraint", "openfold3",
]
LABELS = [
    "Boltz-2", "IntelliFold Flash", "IntelliFold full", "Protenix v2",
    "Protenix Mini", "Protenix Constraint", "OpenFold3",
]
SUFFIX = ["0", "1"]
STRENGTH = ["0", "1"]
CORE_METRICS = ["helix", "sheet", "coil", "plddt", "iptm"]
ALL_METRICS = CORE_METRICS + ["ipsae_min", "complex_plddt"]
STRUCTURE_COLORS = ["#476DA3", "#28A59D", "#CDD4DD"]
COLORS = ["#657386", "#087F83"]
HIT_THRESHOLD = 0.7
_bootstrap_rng = random.Random(907026)
BOOT = np.array([_bootstrap_rng.choices(range(10), k=10) for _ in range(10000)])
CACHE: dict[tuple[str, int, int], str] = {}


def read(path):
    return json.loads(Path(path).read_text())


def sha(path):
    digest = hashlib.sha256()
    with Path(path).open("rb") as handle:
        for block in iter(lambda: handle.read(8 * 1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def check(condition, message):
    if not condition:
        raise RuntimeError(message)


def write_json(path, value):
    Path(path).write_text(json.dumps(value, indent=2, sort_keys=True, allow_nan=False) + "\n")


def bounds(values):
    values = np.asarray(values, dtype=float)
    check(values.shape == (10,), "Bootstrap unit must be ten trajectories")
    draws = np.sort(values[BOOT].mean(axis=1))
    return [float(draws[249]), float(draws[9749])]


def ci(values):
    values = np.asarray(values, dtype=float)
    return [float(np.mean(values)), *bounds(values)]


def paired(left, right, metric):
    differences = [
        right[index]["mean_" + metric] - left[index]["mean_" + metric]
        for index in sorted(left.keys() & right.keys())
        if right[index].get("mean_" + metric) is not None
        and left[index].get("mean_" + metric) is not None
    ]
    if not differences:
        return {"n_pairs": 0, "mean_difference": None, "bootstrap_95_ci": None}
    rng = random.Random(907026)
    draws = sorted(statistics.mean(rng.choices(differences, k=len(differences))) for _ in range(10000))
    return {
        "n_pairs": len(differences),
        "mean_difference": statistics.mean(differences),
        "bootstrap_95_ci": [draws[249], draws[9749]],
    }


def load_frozen_audit():
    sys.path.insert(0, str(EXPERIMENT))
    spec = importlib.util.spec_from_file_location("frozen_binding_audit", EXPERIMENT / "audit.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def load_frozen_geometry():
    path = STUDY / "source/scripts/validate_prediction_geometry.py"
    spec = importlib.util.spec_from_file_location("frozen_binding_geometry", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def load():
    manifest = read(STUDY / "manifest.json")
    manifest_digest = sha(STUDY / "manifest.json")
    stage = read(STUDY / "stage_receipt.json")
    check(sha(STUDY / "stage_receipt.json") == manifest["stage_receipt_sha256"], "Stage identity changed")
    for name, checksum in manifest["experiment_code"].items():
        check(sha(EXPERIMENT / name) == checksum, "Frozen experiment changed: " + name)
    for name, record in stage["files"].items():
        check(sha(STUDY / "source" / name) == record["after_sha256"], "Frozen source changed: " + name)

    frozen_audit = load_frozen_audit()
    geometry = load_frozen_geometry()
    target_sequence = manifest["target"]["sequence"]
    rows, trajectories, audit_checksums = [], [], {}
    raw_path_checks = fallback_lines = 0
    for engine in ENGINES:
        for suffix in SUFFIX:
            arm = engine + "_h" + suffix
            for phase in ("pilot", "remaining"):
                path = STUDY / "audits" / phase / (arm + ".json")
                audit = read(path)
                check(audit["manifest_sha256"] == manifest_digest, "Wrong manifest in audit " + arm)
                check(audit["operational_passed"], "Unfinished audit " + arm)
                audit_checksums[str(path.relative_to(STUDY))] = sha(path)
                for relative, checksum in audit["raw_sha256"].items():
                    raw = STUDY / relative
                    state = raw.stat()
                    key = (str(raw.resolve()), state.st_size, state.st_mtime_ns)
                    if key not in CACHE:
                        CACHE[key] = sha(raw)
                        check(raw.stat().st_mtime_ns == state.st_mtime_ns, "File changed during verification")
                    check(CACHE[key] == checksum, "Raw output changed: " + relative)
                    raw_path_checks += 1
                for row in audit["structures"]:
                    structure = STUDY / row["structure"]
                    with warnings.catch_warnings():
                        warnings.simplefilter("ignore", UserWarning)
                        actual = frozen_audit.evaluate(structure, row["sequence"], target_sequence)
                    check(actual["psea"] == row["psea"], "P-SEA replay changed: " + row["structure"])
                    for metric in ALL_METRICS:
                        expected, observed = row[metric], actual[metric]
                        if expected is None or observed is None:
                            check(expected is None and observed is None, "Optional metric availability changed")
                        else:
                            check(abs(expected - observed) < 1e-9, "Metric replay changed: " + metric)
                    check(actual["target_observed_sequence"] == row["target_observed_sequence"] == target_sequence,
                          "Target-chain identity changed")
                    diagnostics = geometry.inspect_geometry(structure)
                    check(not diagnostics["errors"], "Unusable coordinates: " + row["structure"])
                    check(diagnostics["violations"] == row["geometry_violations"], "Geometry replay changed")
                    check(len(row["sequence"]) == len(row["psea"]) == 90, "Binder length differs")
                    check(abs(sum(row[m] for m in ("helix", "sheet", "coil")) - 1) < 1e-9,
                          "Secondary-structure fractions do not sum to one")
                rows.extend(audit["structures"])
                trajectories.extend(audit["trajectories"])
                fallback_lines += len(audit["svd_fallback_log_lines"])
            print("Verified", arm, flush=True)

    check(len(rows) == 840 and len(trajectories) == 140, "Study cardinality differs")
    check(len({(r["arm"], r["trajectory"], r["cycle"]) for r in rows}) == 840,
          "Duplicate structure identities")
    for trajectory in trajectories:
        selected = sorted(
            [r for r in rows if r["arm"] == trajectory["arm"] and r["trajectory"] == trajectory["trajectory"]],
            key=lambda row: row["cycle"],
        )
        check(trajectory["outcome"] == "completed" and [r["cycle"] for r in selected] == list(range(6)),
              "Trajectory incomplete")
        for metric in ALL_METRICS:
            available = [r[metric] for r in selected[1:] if r[metric] is not None]
            expected = statistics.mean(available) if available else None
            observed = trajectory["mean_" + metric]
            check((expected is None and observed is None) or
                  (expected is not None and observed is not None and abs(expected - observed) < 1e-9),
                  "Trajectory mean differs: " + metric)

    integrity = {
        "manifest_sha256": manifest_digest,
        "stage_receipt_sha256": sha(STUDY / "stage_receipt.json"),
        "audit_sha256": audit_checksums,
        "raw_path_checks": raw_path_checks,
        "unique_file_checks": len(CACHE),
        "reassessed_structures": len(rows),
        "completed_trajectories": len(trajectories),
        "optimization_cycles": 700,
        "svd_fallback_log_lines": fallback_lines,
        "target": manifest["target"],
        "hardware": stage["hardware"],
        "analysis_script_sha256": sha(Path(__file__)),
        "verified_at": datetime.now(timezone.utc).isoformat(),
        "scope": "All completed v7 outputs; superseded v4-v6 attempts excluded. Frozen code and outputs were replayed.",
    }
    return rows, trajectories, integrity


def style():
    plt.rcParams.update({
        "font.family": "Arial", "font.size": 10, "axes.titlesize": 11,
        "axes.titleweight": "bold", "axes.labelsize": 10, "axes.labelcolor": "black",
        "text.color": "black", "axes.edgecolor": "black", "xtick.color": "black",
        "ytick.color": "black", "xtick.direction": "in", "ytick.direction": "in",
        "axes.grid": False, "axes.spines.top": False, "axes.spines.right": False,
        "svg.fonttype": "none", "pdf.fonttype": 42, "savefig.facecolor": "white",
    })


def title(fig, number, headline, subtitle):
    fig.text(.04, .98, number, fontsize=10, fontweight="bold", va="top", color="black")
    fig.text(.04, .955, headline, fontsize=20, fontweight="bold", va="top")
    fig.text(.04, .902, subtitle, fontsize=10, va="top")


def footer(fig, text):
    fig.text(.04, .025, text, fontsize=9, va="bottom", linespacing=1.5)


def save(fig, name, pdf):
    fig.savefig(OUT / (name + ".svg"), transparent=True)
    fig.savefig(OUT / (name + ".png"), dpi=220)
    fig.savefig(OUT / (name + ".pdf"))
    pdf.savefig(fig)
    plt.close(fig)


def figures(rows, trajectories, timing):
    style()
    data = {
        (engine, suffix): sorted(
            [t for t in trajectories if t["arm"] == engine + "_h" + suffix],
            key=lambda row: row["trajectory"],
        )
        for engine in ENGINES for suffix in SUFFIX
    }

    def values(engine, suffix, metric, prefix="mean_"):
        return np.array([t[prefix + metric] for t in data[engine, suffix] if t[prefix + metric] is not None])

    paired_data = {
        (engine, suffix): {t["trajectory"]: t for t in data[engine, suffix]}
        for engine in ENGINES for suffix in SUFFIX
    }
    contrasts = {
        engine + ":0->1": {
            metric: paired(paired_data[engine, "0"], paired_data[engine, "1"], metric)
            for metric in ALL_METRICS
        }
        for engine in ENGINES
    }
    write_json(OUT / "paired_contrasts.json", contrasts)

    with PdfPages(OUT / "FIGURES.pdf") as pdf:
        fig = plt.figure(figsize=(17, 12))
        grid = fig.add_gridspec(1, 4, left=.17, right=.97, bottom=.15, top=.82,
                                width_ratios=[1.45, 1, 1, 1], wspace=.25)
        structure_ax, confidence_ax, binding_ax, time_ax = [fig.add_subplot(grid[0, index]) for index in range(4)]
        title(fig, "01 / COMPLETE BENCHMARK", "Initialization control changes predicted binder structure",
              "ACBX-conditioned 90-aa binders  •  seven engines  •  strengths 0 and 1  •  all 140 trajectories completed")
        ticks, ticklabels = [], []
        for engine_index, engine in enumerate(ENGINES):
            center = engine_index * 3 + .5
            structure_ax.text(-.10, center, LABELS[engine_index], transform=structure_ax.get_yaxis_transform(),
                              ha="right", va="center", fontweight="bold", fontsize=10)
            for strength_index, suffix in enumerate(SUFFIX):
                y = engine_index * 3 + strength_index
                means = [values(engine, suffix, metric).mean() * 100 for metric in ("helix", "sheet", "coil")]
                start = 0
                for value, color in zip(means, STRUCTURE_COLORS):
                    structure_ax.barh(y, value, left=start, height=.72, color=color,
                                      edgecolor="black", linewidth=.55)
                    if value >= 10:
                        structure_ax.text(start + value / 2, y, f"{value:.0f}", ha="center", va="center", fontsize=9)
                    start += value
                for axis, metric in ((confidence_ax, "plddt"), (binding_ax, "iptm")):
                    sample = values(engine, suffix, metric)
                    jitter = np.linspace(-.19, .19, 10)
                    axis.scatter(sample, y + jitter, s=14, color=COLORS[strength_index], alpha=.45, zorder=2)
                    mean, low, high = ci(sample)
                    axis.plot([low, high], [y, y], color="black", lw=1.25, zorder=3)
                    axis.scatter([mean], [y], marker="D", s=25, facecolor="white", edgecolor="black", zorder=4)
                seconds = timing['arms'][engine+'_h'+suffix]['seconds_per_design']
                time_ax.barh(y, seconds, height=.72, color=COLORS[strength_index], edgecolor='black', linewidth=.55)
                time_ax.annotate(f'{seconds:.1f}', (seconds,y), xytext=(4,0), textcoords='offset points', va='center', fontsize=9)
                ticks.append(y)
                ticklabels.append(STRENGTH[strength_index])
        for axis in (structure_ax, confidence_ax, binding_ax, time_ax):
            axis.set_ylim(20, -1)
        structure_ax.set_xlim(0, 100); structure_ax.set_xticks([0, 25, 50, 75, 100])
        confidence_ax.set_xlim(0, 100); confidence_ax.set_xticks([0, 25, 50, 75, 100])
        binding_ax.set_xlim(0, 1); binding_ax.set_xticks([0, .25, .5, .75, 1])
        binding_ax.axvline(HIT_THRESHOLD, color="#A1443A", linestyle="--", linewidth=1)
        structure_ax.set_yticks(ticks, ticklabels)
        confidence_ax.set_yticks([]); binding_ax.set_yticks([]); time_ax.set_yticks([])
        time_ax.set_xlim(0, max(v['seconds_per_design'] for v in timing['arms'].values())*1.25)
        time_ax.set_title('Time per design', loc='left', pad=16)
        time_ax.set_xlabel('Seconds / optimized design')
        structure_ax.set_title("Secondary structure", loc="left", pad=16)
        confidence_ax.set_title("Binder confidence", loc="left", pad=16)
        binding_ax.set_title("Interface confidence", loc="left", pad=16)
        structure_ax.set_xlabel("Binder residues (%)")
        confidence_ax.set_xlabel("Mean binder Cα pLDDT")
        binding_ax.set_xlabel("Mean iPTM")
        fig.legend(handles=[Patch(facecolor=color, edgecolor="black", label=label)
                            for color, label in zip(STRUCTURE_COLORS, ["Helix", "Sheet", "Coil"])],
                   loc="upper left", bbox_to_anchor=(.17, .872), ncol=3, frameon=False)
        footer(fig, "Bars and diamonds: means of ten trajectory means over cycles 01–05; cycle00 excluded. Dots: individual trajectories; black intervals: 95% bootstrap CIs.\n"
                    "The dashed iPTM line is the predeclared 0.7 hit threshold; predictor scores are not experimental binding evidence.\nTime: summed recorded phase spans / 50 optimized outputs per condition (10 trajectories × 5 cycles), including initialization and MPNN.\nOverlapping timers counted once; one aggregate from pilot + remaining phases, no timing CI. Apple M4 Max, 64 GB.\nNative settings and confidence scales differ by engine; descriptive costs, not a controlled speed or accuracy ranking.")
        save(fig, "01_overview", pdf)

        fig, axes = plt.subplots(1, 5, figsize=(15, 7.3), sharey=True)
        fig.subplots_adjust(left=.16, right=.985, top=.77, bottom=.21, wspace=.30)
        title(fig, "02 / PAIRED EFFECTS", "What changes when strength increases from 0 to 1?",
              "Matched trajectory indices within each engine  •  cycles 01–05  •  n=10 pairs")
        for metric, axis in zip(CORE_METRICS, axes):
            scale = 100 if metric in ("helix", "sheet", "coil") else 1
            axis.axvline(0, color="#8F959C", lw=.9, zorder=0)
            for engine_index, engine in enumerate(ENGINES):
                result = contrasts[engine + ":0->1"][metric]
                mean = result["mean_difference"] * scale
                low, high = np.array(result["bootstrap_95_ci"]) * scale
                axis.plot([low, high], [engine_index, engine_index], color=COLORS[1], lw=1.8)
                axis.scatter([mean], [engine_index], s=34, color=COLORS[1], edgecolor="black", linewidth=.5, zorder=3)
            axis.set_title({"helix": "Helix", "sheet": "Sheet", "coil": "Coil",
                            "plddt": "Binder confidence", "iptm": "Interface confidence"}[metric], loc="left", pad=14)
            axis.set_xlabel("Δ percentage points" if metric in ("helix", "sheet", "coil")
                            else ("Δ pLDDT" if metric == "plddt" else "Δ iPTM"))
            axis.set_ylim(6.6, -.6)
        axes[0].set_yticks(range(7), LABELS)
        axes[0].set_xlim(-55, 30); axes[1].set_xlim(-30, 55); axes[2].set_xlim(-35, 50)
        axes[3].set_xlim(-32, 18); axes[4].set_xlim(-.25, .25)
        footer(fig, "Points: mean paired differences in trajectory means. Lines: 95% paired bootstrap CIs; n=10 pairs per engine.\n"
                    "10,000 resamples, seed 907026. Intervals are exploratory and unadjusted for multiple comparisons. iPTM is a predictor score, not measured binding.")
        save(fig, "02_paired_effects", pdf)

        fig, axes = plt.subplots(7, 4, figsize=(13, 15), sharex=True)
        fig.subplots_adjust(left=.17, right=.97, top=.84, bottom=.08, hspace=.38, wspace=.23)
        title(fig, "03 / OPTIMIZATION DYNAMICS", "The initialization signal persists through cycling",
              "Same ten trajectories at every cycle  •  initialization-only sequence bias  •  ordinary SolubleMPNN thereafter")
        for engine_index, engine in enumerate(ENGINES):
            for metric_index, metric in enumerate(("helix", "sheet", "plddt", "iptm")):
                axis = axes[engine_index, metric_index]
                scale = 100 if metric in ("helix", "sheet") else 1
                axis.axvspan(-.2, .35, facecolor="#E9EDF1", zorder=0)
                for strength_index, suffix in enumerate(SUFFIX):
                    cycle_values = []
                    for cycle in range(6):
                        sample = sorted([r for r in rows if r["arm"] == engine + "_h" + suffix and r["cycle"] == cycle],
                                        key=lambda row: row["trajectory"])
                        cycle_values.append(ci([r[metric] * scale for r in sample]))
                    summary = np.array(cycle_values)
                    axis.plot(range(6), summary[:, 0], color=COLORS[strength_index], marker="o", ms=3, lw=1.6)
                    axis.fill_between(range(6), summary[:, 1], summary[:, 2], color=COLORS[strength_index], alpha=.09, lw=0)
                if metric in ("helix", "sheet", "plddt"):
                    axis.set_ylim(0, 100); axis.set_yticks([0, 50, 100])
                else:
                    axis.set_ylim(0, 1); axis.set_yticks([0, .5, 1]); axis.axhline(HIT_THRESHOLD, color="#A1443A", ls="--", lw=.8)
                axis.set_xlim(-.2, 5.2); axis.set_xticks(range(6))
                if engine_index == 0:
                    axis.set_title({"helix": "Helix (%)", "sheet": "Sheet (%)", "plddt": "Binder pLDDT",
                                    "iptm": "iPTM"}[metric], loc="left", pad=12)
                if metric_index == 0:
                    axis.set_ylabel(LABELS[engine_index], rotation=0, ha="right", va="center", labelpad=18, fontweight="bold")
                if engine_index == 6:
                    axis.set_xlabel("Cycle (0 = initialization)")
        fig.legend(handles=[Line2D([], [], color=COLORS[index], marker="o", label=f"Strength {STRENGTH[index]}")
                            for index in range(2)], loc="upper left", bbox_to_anchor=(.17, .875), ncol=2, frameon=False)
        footer(fig, "Means and pointwise 95% bootstrap CIs across n=10 trajectories per condition. Cycle00 is shaded and shown only as initialization.\n"
                    "Cycles are repeated observations, not independent replicates. Ribbon intervals are exploratory and unadjusted.")
        save(fig, "03_cycle_dynamics", pdf)

        fig, axes = plt.subplots(2, 4, figsize=(13, 8.5), sharex=True, sharey=True)
        fig.subplots_adjust(left=.07, right=.97, top=.80, bottom=.14, hspace=.40, wspace=.18)
        title(fig, "04 / FINAL-CYCLE OUTCOMES", "Predicted structure and interface confidence at cycle 05",
              "Every point is one completed trajectory  •  final binder helicity versus final iPTM")
        for engine_index, engine in enumerate(ENGINES):
            axis = axes.flat[engine_index]
            for strength_index, suffix in enumerate(SUFFIX):
                x = values(engine, suffix, "helix", "final_") * 100
                y = values(engine, suffix, "iptm", "final_")
                axis.scatter(x, y, s=29, color=COLORS[strength_index], alpha=.65, edgecolor="black", linewidth=.35)
                axis.scatter([x.mean()], [y.mean()], s=90, color=COLORS[strength_index], marker="D",
                             edgecolor="black", linewidth=1.1)
            axis.axhline(HIT_THRESHOLD, color="#A1443A", linestyle="--", linewidth=.9)
            axis.set_title(LABELS[engine_index], loc="left")
            axis.set_xlim(-3, 103); axis.set_ylim(0, 1.03)
            axis.set_xticks([0, 25, 50, 75, 100]); axis.set_yticks([0, .25, .5, .75, 1])
            if engine_index // 4 == 1:
                axis.set_xlabel("Final helix residues (%)")
            if engine_index % 4 == 0:
                axis.set_ylabel("Final iPTM")
        axes.flat[-1].axis("off")
        axes.flat[-1].legend(handles=[Line2D([], [], linestyle="", marker="o", color=COLORS[index],
                                                   label=f"Strength {STRENGTH[index]}") for index in range(2)] +
                                            [Line2D([], [], linestyle="", marker="D", markerfacecolor="white",
                                                    markeredgecolor="black", label="Condition mean")],
                                 loc="center", frameon=False, labelspacing=1.4)
        footer(fig, "n=10 trajectories per strength per engine. The dashed line is the predeclared iPTM ≥0.7 computational-hit threshold.\n"
                    "This final-cycle endpoint is separate from the primary five-cycle mean. iPTM does not establish experimental binding.")
        save(fig, "04_final_outcomes", pdf)

        flagged = sorted({(r["arm"], r["trajectory"]) for r in rows if r["geometry_violation_count"]})
        fig, (left, right) = plt.subplots(1, 2, figsize=(12, max(6.8, len(flagged) * .34)),
                                         gridspec_kw={"width_ratios": [1.45, 1]})
        fig.subplots_adjust(left=.30, right=.96, top=.77, bottom=.18, wspace=.28)
        title(fig, "05 / GEOMETRY DIAGNOSTICS", "Recorded continuity warnings across the campaign",
              "All 840 predicted structures rechecked  •  warnings retained  •  no geometry-based exclusions")
        matrix = np.array([[next(r["geometry_violation_count"] for r in rows
                                      if (r["arm"], r["trajectory"]) == key and r["cycle"] == cycle)
                            for cycle in range(6)] for key in flagged])
        from matplotlib.colors import BoundaryNorm, ListedColormap
        maximum = max(1, int(matrix.max()))
        palette = plt.get_cmap("YlOrBr", maximum + 1)
        left.imshow(matrix, cmap=palette, norm=BoundaryNorm(np.arange(-.5, maximum + 1.5), maximum + 1), aspect="auto")
        for row_index in range(len(flagged)):
            for cycle in range(6):
                left.text(cycle, row_index, str(matrix[row_index, cycle]), ha="center", va="center", fontsize=9)
        left.set_xticks(range(6)); left.set_xlabel("Cycle (0 = initialization)")
        labels = []
        for arm, trajectory in flagged:
            engine, suffix = arm.rsplit("_h", 1)
            labels.append(f"{LABELS[ENGINES.index(engine)]} · strength {suffix}\nTrajectory {trajectory:02d}")
        left.set_yticks(range(len(flagged)), labels); left.set_title("Every trajectory with ≥1 warning", loc="left", pad=15)
        structures_flagged = sum(bool(r["geometry_violation_count"]) for r in rows)
        final_flagged = sum(bool(r["geometry_violation_count"]) and r["cycle"] == 5 for r in rows)
        total_warnings = sum(r["geometry_violation_count"] for r in rows)
        right.axis("off")
        right.text(.05, .87, f"{structures_flagged} / 840", fontsize=28, fontweight="bold", transform=right.transAxes)
        right.text(.05, .75, "structures with ≥1 continuity warning", fontsize=11, transform=right.transAxes)
        right.text(.05, .52, f"{final_flagged} / 140", fontsize=28, fontweight="bold", transform=right.transAxes)
        right.text(.05, .40, "final structures with ≥1 warning", fontsize=11, transform=right.transAxes)
        right.text(.05, .20, f"{total_warnings} total flagged distances", fontsize=13, fontweight="bold", transform=right.transAxes)
        footer(fig, "Cells count atom-pair distance warnings for the affected trajectories; unlisted trajectories had none.\n"
                    "Thresholds: C–N >2.2 Å and Cα–Cα >4.5 Å. This limited continuity screen is not comprehensive stereochemical validation.")
        save(fig, "05_geometry_recovery", pdf)
    return contrasts


def fmt(value, digits=3):
    return "—" if value is None else f"{value:.{digits}f}"


def report(rows, trajectories, integrity, contrasts, timing):
    target = integrity["target"]
    geometry_structures = sum(bool(row["geometry_violation_count"]) for row in rows)
    geometry_trajectories = len({(row["arm"], row["trajectory"]) for row in rows if row["geometry_violation_count"]})
    final_geometry = sum(row["geometry_violation_count"] for row in rows if row["cycle"] == 5)
    final_hits = sum(trajectory["final_is_hit"] for trajectory in trajectories)
    helix_effects = {engine: contrasts[engine + ":0->1"]["helix"] for engine in ENGINES}
    significant = [LABELS[ENGINES.index(engine)] for engine, result in helix_effects.items()
                   if result["bootstrap_95_ci"][1] < 0]
    strongest = min(ENGINES, key=lambda engine: helix_effects[engine]["mean_difference"])
    lines = [
        "# Initialization-only helix control in target-conditioned binder design",
        "",
        f"**All 140 trajectories completed all five optimization cycles.** All 840 predicted complexes "
        f"(including 140 cycle00 initializations) were reassessed from coordinates; 700 optimization cycles enter "
        f"the primary endpoint. The target is `{target['name']}` ({target['length']} aa), with the exact supplied "
        f"{target['msa_format']} MSA SHA-256 `{target['msa_sha256']}`.",
        "",
        "## Main findings",
        "",
        f"- Strength 1 reduced mean binder helicity in every engine. The exploratory paired 95% interval excludes "
        f"zero for {len(significant)} of seven engines ({', '.join(significant)}).",
        f"- The largest mean helicity shift was {LABELS[ENGINES.index(strongest)]}: "
        f"{helix_effects[strongest]['mean_difference'] * 100:.1f} percentage points "
        f"[{helix_effects[strongest]['bootstrap_95_ci'][0] * 100:.1f}, "
        f"{helix_effects[strongest]['bootstrap_95_ci'][1] * 100:.1f}].",
        "- Every engine's paired mean-iPTM interval spans zero. This sample therefore does not establish a reliable "
        "directional effect of helix-kill strength on predicted interface confidence.",
        f"- There were {final_hits} cycle05 computational hits at the predeclared iPTM ≥{HIT_THRESHOLD:.1f} threshold "
        "across all conditions. Hit counts are descriptive and do not constitute experimental binding evidence.",
        f"- Geometry screening flagged {geometry_structures} structures in {geometry_trajectories} trajectories. "
        f"Cycle05 retained {final_geometry} flagged distances; all warnings remain included in endpoints.",
        "",
        "## Primary endpoint: mean across cycles 01–05",
        "",
        "Each row averages ten trajectory means. Cycle00 is excluded. H/S/C are Biotite P-SEA assignments on the "
        "binder chain; coil assignment does not establish disorder.",
        "",
        "| Engine | Strength | n | Helix % | Sheet % | Coil % | Binder pLDDT | iPTM | ipSAE(min) | Final hits |",
        "|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|",
    ]
    for engine, label in zip(ENGINES, LABELS):
        for suffix, strength in zip(SUFFIX, STRENGTH):
            selected = [t for t in trajectories if t["arm"] == engine + "_h" + suffix]
            mean = lambda metric: statistics.mean(t["mean_" + metric] for t in selected
                                                   if t["mean_" + metric] is not None) if any(
                                                       t["mean_" + metric] is not None for t in selected) else None
            lines.append(f"| {label} | {strength} | 10 | {mean('helix') * 100:.1f} | {mean('sheet') * 100:.1f} | "
                         f"{mean('coil') * 100:.1f} | {mean('plddt'):.1f} | {fmt(mean('iptm'))} | "
                         f"{fmt(mean('ipsae_min'))} | {sum(t['final_is_hit'] for t in selected)} |")
    lines += [
        "", "## Final-cycle endpoint", "",
        "| Engine | Strength | Helix % | Sheet % | Coil % | Binder pLDDT | iPTM | ipSAE(min) |",
        "|---|---:|---:|---:|---:|---:|---:|---:|",
    ]
    for engine, label in zip(ENGINES, LABELS):
        for suffix, strength in zip(SUFFIX, STRENGTH):
            selected = [t for t in trajectories if t["arm"] == engine + "_h" + suffix]
            mean = lambda metric: statistics.mean(t["final_" + metric] for t in selected
                                                   if t["final_" + metric] is not None) if any(
                                                       t["final_" + metric] is not None for t in selected) else None
            lines.append(f"| {label} | {strength} | {mean('helix') * 100:.1f} | {mean('sheet') * 100:.1f} | "
                         f"{mean('coil') * 100:.1f} | {mean('plddt'):.1f} | {fmt(mean('iptm'))} | "
                         f"{fmt(mean('ipsae_min'))} |")
    lines += [
        "", "## Interpretation", "",
        "This completed campaign supports initialization-only helix-kill as a way to shift predicted binder-chain "
        "secondary structure while keeping subsequent SolubleMPNN optimization unchanged. It does not show improved "
        "binding: mean iPTM effects are uncertain in every engine, and neither predictor confidence nor a thresholded "
        "computational hit is experimental evidence.",
        "", "## Pairing, uncertainty and limits", "",
        "Ten paired trajectory indices per engine; primary units are trajectory means over cycles 01–05. Cycles and "
        "residues are not independent replicates. Paired intervals use 10,000 bootstrap resamples with seed 907026. "
        "They are exploratory and unadjusted for multiplicity; intervals crossing zero are not proof of no effect.",
        "",
        "Common design: 90-aa binders against the frozen ACBX target, 50% masked initialization, SolubleMPNN, exact "
        "query-matched target MSA, one predictor sample, prediction seed 42, paired initialization/MPNN seeds, and five "
        "optimization cycles. Engine/checkpoint fingerprints, hardware and scheduler evidence are preserved in the "
        "stage receipt. Predictor confidence scales are not assumed calibrated across engines. No runtime default is promoted.",
        "",
        "No geometry-based exclusions were made. The recorded C–N/Cα–Cα screen is limited and zero warnings would "
        "not imply comprehensive stereochemical correctness. No experimental binding, folding, stability, specificity, "
        "toxicity or biological-function tests were performed.",
        "", "## Files", "",
        "Open **GALLERY.html** for a standalone visual report. **FIGURES.pdf** combines five figure pages. Every figure "
        "is also supplied as editable SVG, PDF and 220-dpi PNG. `summary.csv`, `structures.csv`, `trajectories.csv`, "
        "`geometry_events.csv` and `paired_contrasts.json` contain the numerical analysis. `integrity.json` records "
        "raw-output verification and frozen source identities.",
    ]
    lines += campaign_timing.report_section(timing)
    (OUT / "REPORT.md").write_text("\n".join(lines) + "\n")

    captions = [
        ("01_overview", "Complete benchmark", "Primary endpoint across cycles 01–05: structure, binder confidence and iPTM. Time bars are recorded phase spans divided by 50 optimized outputs, including initialization; overlapping timers count once. Descriptive costs on Apple M4 Max, not a controlled speed comparison."),
        ("02_paired_effects", "Paired strength effects", "Strength 1 minus strength 0 with paired 95% bootstrap intervals."),
        ("03_cycle_dynamics", "Dynamics through optimization", "Cycle00 is initialization and excluded from primary endpoints."),
        ("04_final_outcomes", "Final-cycle distribution", "Every final structure; diamonds are condition means."),
        ("05_geometry_recovery", "Geometry diagnostics", "Every affected trajectory is shown; warnings were retained."),
    ]
    cards = []
    for name, heading, caption in captions:
        encoded = base64.b64encode((OUT / (name + ".svg")).read_bytes()).decode()
        cards.append(f'<section><h2>{heading}</h2><p>{caption}</p><img alt="{heading}" src="data:image/svg+xml;base64,{encoded}"></section>')
    html = f'''<!doctype html><html lang="en"><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>Binding helix control — complete benchmark</title><style>body{{margin:0;background:#eef1f4;color:#111;font:16px/1.65 Arial,sans-serif}}main{{max-width:1200px;margin:48px auto;padding:0 24px}}header{{padding:30px 0}}h1{{font-size:42px;line-height:1.15;max-width:900px}}h2{{font-size:25px}}small{{letter-spacing:.12em}}section{{background:white;margin:32px 0;padding:28px;border:1px solid #d8dee5;border-radius:12px}}img{{display:block;width:100%;height:auto}}p{{max-width:950px}}.stats{{display:flex;gap:30px;flex-wrap:wrap}}.stats b{{font-size:30px;display:block}}.note{{border-left:4px solid #087f83;padding-left:20px}}</style><main><header><small>IPROTEINSTUDIO / COMPLETE BENCHMARK / 08 SEPTEMBER 2026</small><h1>Secondary-structure control in ACBX-conditioned binder design.</h1><p>Seven prediction engines. Two helix-kill strengths. Ordinary SolubleMPNN optimization after initialization.</p><div class="stats"><div><b>140 / 140</b>completed trajectories</div><div><b>700</b>optimization cycles</div><div><b>{final_hits}</b>final iPTM hits</div></div><p class="note">Strength 1 reduces mean predicted binder helicity in every engine, but its effect on predicted interface confidence is uncertain in every engine. These are computational outcomes with n=10 paired trajectories per engine, not experimental binding results.</p></header>''' + "".join(cards) + '''<footer><p>All 840 structures reassessed from coordinates and all audited raw paths rehashed. Cycle00 is excluded from the primary endpoint. Paired bootstrap intervals use 10,000 resamples and are unadjusted for multiplicity. Full numerical tables and caveats are in REPORT.md.</p></footer></main></html>'''
    (OUT / "GALLERY.html").write_text(html)


def write_csv(name, records):
    fields = sorted(set().union(*(record.keys() for record in records)))
    with (OUT / name).open("w", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields)
        writer.writeheader()
        writer.writerows({key: json.dumps(value) if isinstance(value, (list, dict)) else value
                          for key, value in record.items()} for record in records)


def main():
    OUT.mkdir(parents=True, exist_ok=True)
    rows, trajectories, integrity = load()
    timing = campaign_timing.summarize(STUDY, ENGINES, SUFFIX)
    campaign_timing.export(OUT, timing)
    integrity['timing_helper_sha256'] = sha(Path(campaign_timing.__file__))
    integrity['timing_source_sha256'] = timing['source_sha256']
    write_json(OUT / "integrity.json", integrity)
    write_csv("structures.csv", rows)
    write_csv("trajectories.csv", trajectories)
    write_csv("geometry_events.csv", [row for row in rows if row["geometry_violation_count"]])
    summary = []
    for engine, label in zip(ENGINES, LABELS):
        for suffix, strength in zip(SUFFIX, STRENGTH):
            selected = [t for t in trajectories if t["arm"] == engine + "_h" + suffix]
            record = {"engine": label, "engine_id": engine, "strength": strength, "n": 10,
                      "seconds_per_design": timing["arms"][engine+"_h"+suffix]["seconds_per_design"],
                      "final_hits": sum(t["final_is_hit"] for t in selected)}
            for prefix in ("mean_", "final_"):
                for metric in ALL_METRICS:
                    available = [t[prefix + metric] for t in selected if t[prefix + metric] is not None]
                    record[prefix + metric] = statistics.mean(available) if available else None
            summary.append(record)
    write_csv("summary.csv", summary)
    contrasts = figures(rows, trajectories, timing)
    report(rows, trajectories, integrity, contrasts, timing)
    excluded = {"artifact_sha256.json", "helix_control_complete.zip"}
    write_json(OUT / "artifact_sha256.json", {path.name: sha(path) for path in OUT.iterdir()
                                               if path.is_file() and path.name not in excluded})
    with zipfile.ZipFile(OUT / "helix_control_complete.zip", "w", zipfile.ZIP_DEFLATED) as archive:
        for path in OUT.iterdir():
            if path.is_file() and path.suffix != ".zip":
                archive.write(path, path.name)
    print(json.dumps({"complete": True, "output": str(OUT), "trajectories": 140,
                      "optimized_cycles": 700}), flush=True)


if __name__ == "__main__":
    main()
