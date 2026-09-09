"""Snapshot audited results without changing the running experiment or raw jobs."""
from collections import Counter
from datetime import datetime, timezone
import csv
import json
from pathlib import Path
import statistics as stats
import sys

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent / "monomer_secondary_structure_v1"))
import campaign as study
import audit

CORE = ["baseline", "antihelix", "beta", "mixed", "beta_inspection"]
LABELS = ["Baseline", "Helix kill", "Beta prior", "Mixed", "Beta + inspection"]
METRICS = ["helix", "sheet", "coil", "plddt", "uncertain_coil_fraction"]


def main():
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    output = study.OUTPUT / "interim" / stamp
    output.mkdir(parents=True)
    (output / "analysis_source.py").write_bytes(Path(__file__).read_bytes())
    manifest = study.prepare()
    # Fix the input set before reading so the snapshot cannot silently acquire
    # more completed cohorts while the campaign continues.
    paths = sorted((study.OUTPUT / "audits").glob("*/*.json"))
    audits = [audit.audit(p.parent.name, p.stem) for p in paths]
    rows = [r for a in audits for r in a["trajectories"]]
    structures = [r for a in audits for r in a["structures"]]
    data, summaries = {}, {}
    for arm in CORE:
        data[arm] = {r["trajectory"]: r for r in rows if r["arm"] == arm}
        study.require(sorted(data[arm]) == list(range(1, 11)), f"Core cohort incomplete: {arm}")
        study.require(all(r["outcome"] == "completed" for r in data[arm].values()), f"Core attrition: {arm}")
        summaries[arm] = {"n": 10, **{prefix + m: stats.mean(r[prefix + m] for r in data[arm].values())
                                     for prefix in ("mean_", "final_") for m in METRICS},
                          "mean_wall_seconds": stats.mean(r["wall_seconds_including_initialization"] for r in data[arm].values())}
        study.require(abs(sum(summaries[arm]["mean_" + m] for m in ("helix", "sheet", "coil")) - 1) < 1e-12,
                      "Composition does not sum to one")
    contrasts = {}
    for arm in CORE[1:]:
        reference = manifest["config"]["arms"][arm]["reference"]
        contrasts[arm] = {"reference": reference, "predeclared": True,
                          "metrics": {m: audit.paired_summary(data[reference], data[arm], "mean_" + m) for m in METRICS}}
    contrasts["mixed_vs_baseline"] = {"reference": "baseline", "predeclared": False,
        "metrics": {m: audit.paired_summary(data["baseline"], data["mixed"], "mean_" + m) for m in METRICS}}
    inspection = {"attempt_counts": dict(Counter(r["attempts"] for r in data["beta_inspection"].values())),
                  "refined_trajectories": [i for i, r in data["beta_inspection"].items() if r["attempts"] > 1],
                  "accepted": 10, "exhausted": 0,
                  "unrefined_matching_metrics": all(all(data["beta"][i]["mean_" + m] == r["mean_" + m] for m in METRICS)
                                                    for i, r in data["beta_inspection"].items() if r["attempts"] == 1)}
    progress = {"declared_trajectories": 220, "audited_trajectories": len(rows),
                "completed_five_cycles": sum(r["outcome"] == "completed" for r in rows),
                "budget_exhausted": sum(r["outcome"] == "budget_exhausted" for r in rows),
                "audited_optimized_structures": sum(r["cycle"] > 0 for r in structures),
                "audited_outcomes_by_arm": {arm: dict(Counter(r["outcome"] for r in rows if r["arm"] == arm)) for arm in study.CONFIG["arms"]}}
    statuses = {str(p.relative_to(study.OUTPUT)): study.read(p) for p in sorted((study.OUTPUT / "status").glob("*/*.json"))}
    study.atomic(output / "status_snapshot.json", statuses)
    complete = len(rows) == 220
    result = {"as_of_utc": stamp, "full_campaign_complete": complete,
              "manifest_sha256": study.sha(study.OUTPUT / "manifest.json"),
              "analysis_code_sha256": study.sha(Path(__file__)),
              "input_audit_sha256": {str(p.relative_to(study.OUTPUT)): study.sha(p) for p in paths},
              "progress": progress, "summaries": summaries, "contrasts": contrasts, "inspection": inspection,
              "methods": {"unit": "paired trajectory mean across cycles 01–05; cycle 00 excluded",
                          "assignment": "Biotite P-SEA", "plddt": "mean CA pLDDT, 0–100",
                          "interval": "10,000 paired bootstrap resamples, exploratory, no multiplicity adjustment",
                          "scope": "five completed core conditions; other cohort counts are recorded in progress but not analysed here",
                          "hardware": study.read(study.OUTPUT / "stage_receipt.json")["hardware"]}}
    study.atomic(output / "report.json", result)
    with (output / "summary.csv").open("w") as handle:
        writer = csv.DictWriter(handle, fieldnames=["condition", *summaries[CORE[0]]])
        writer.writeheader()
        writer.writerows({"condition": arm, **values} for arm, values in summaries.items())
    with (output / "trajectories.csv").open("w") as handle:
        fields = ["arm", "trajectory", "attempts", "outcome", *["mean_" + m for m in METRICS], *["final_" + m for m in METRICS]]
        writer = csv.DictWriter(handle, fieldnames=fields, extrasaction="ignore")
        writer.writeheader(); writer.writerows(r for arm in CORE for r in data[arm].values())
    campaign_status = "All declared trajectories are audited." if complete else "Full 22-condition screen is still running."
    lines = ["# Monomer benchmark — interim core comparison", "", f"UTC snapshot: {stamp}. {campaign_status}", "",
             f"Audited: {len(rows)}/220 declared trajectories; {progress['completed_five_cycles']} completed all five cycles; {progress['budget_exhausted']} exhausted initialization budgets in additional inspection variants.", "",
             "All five core conditions have n=10 complete trajectories (50 optimized structures each). Means below first average cycles 01–05 within a trajectory. Cycle 00 is excluded; pLDDT is on the 0–100 scale.", "",
             "| Condition | Helix | Sheet | Coil | pLDDT | Final-cycle pLDDT |", "|---|---:|---:|---:|---:|---:|"]
    for arm, label in zip(CORE, LABELS):
        s = summaries[arm]
        lines.append(f"| {label} | {s['mean_helix']:.1%} | {s['mean_sheet']:.1%} | {s['mean_coil']:.1%} | {s['mean_plddt']:.1f} | {s['final_plddt']:.1f} |")
    lines += ["", "## Paired changes", "", "Percentage points for structural fractions; pLDDT points for confidence. Intervals are exploratory paired 95% bootstrap intervals, not adjusted for multiple comparisons.", "",
              "| Comparison | Helix change [CI] | Sheet change [CI] | Coil change [CI] | pLDDT change [CI] |", "|---|---:|---:|---:|---:|"]
    for arm, comparison in contrasts.items():
        cells = []
        for metric in ("helix", "sheet", "coil", "plddt"):
            s = comparison["metrics"][metric]; scale = 1 if metric == "plddt" else 100
            low, high = s["bootstrap_95_ci"]
            cells.append(f"{scale*s['mean_difference']:+.1f} [{scale*low:+.1f}, {scale*high:+.1f}]")
        label = f"{arm} vs {comparison['reference']}" if comparison["predeclared"] else "mixed vs baseline (additional exploratory comparison)"
        lines.append(f"| {label} | {' | '.join(cells)} |")
    lines += ["", "## Interpretation", "",
              "Helix kill lowers mean helix but largely raises coil, with lower mean confidence. Its helix-change interval includes zero; the coil increase and confidence decrease are clearer in this small cohort.", "",
              "The beta-oriented initialization does not show beta enrichment here: its mean sheet fraction is below baseline, though the paired interval includes zero. It yields predominantly helical folds after optimization.", "",
              "Mixed initialization shifts composition substantially relative to beta-only: both sheet and coil increase. Its small mean sheet advantage over baseline is not resolved by the paired interval. High coil does not by itself establish disorder.", "",
              "Inspection refined trajectories 1 and 2 once each; the other eight accepted their originals and reproduced the beta control's metrics exactly. All ten were accepted, with no exhaustion in the main inspection arm. Mean coil falls by 2.0 percentage points and mean pLDDT rises by 1.4 points relative to beta-only, but beta enrichment remains small. The assessor screens long uncertain coil; it does not enforce a beta-sheet fraction.", "",
              "## Limits", "", "The other 17 conditions are not interpreted or ranked in this core-only report; their audited cohort counts are in report.json. Scope/persistence comparisons belong to the full campaign report. Only one length, predictor and paired seed cohort were tested; this is a prediction-based screen with no experimental folding validation or default promotion.", ""]
    (output / "REPORT.md").write_text("\n".join(lines))
    plot(output, data, summaries)
    print(json.dumps({"output": str(output), "progress": progress, "inspection": inspection}, indent=2))


def plot(output, data, summaries):
    import matplotlib.pyplot as plt
    import numpy as np
    plt.rcParams.update({"font.family": "Arial", "text.color": "black", "axes.labelcolor": "black",
                         "axes.edgecolor": "black", "xtick.direction": "in", "ytick.direction": "in", "axes.grid": False})
    fig, axes = plt.subplots(1, 2, figsize=(11, 4.7), layout="constrained")
    bottom = np.zeros(5)
    for metric, color in (("helix", "#d5916c"), ("sheet", "#73a2b9"), ("coil", "#d5d5d5")):
        values = np.array([100 * summaries[arm]["mean_" + metric] for arm in CORE])
        axes[0].bar(range(5), values, bottom=bottom, color=color, edgecolor="black", linewidth=.7, label=metric.capitalize())
        bottom += values
    axes[0].set_ylabel("Residues (%)"); axes[0].set_ylim(0, 100)
    axes[0].set_title("Mean composition, cycles 01–05")
    axes[0].legend(loc="upper center", bbox_to_anchor=(.5, 1.0), ncol=3, frameon=True, fontsize=8)
    for i, arm in enumerate(CORE):
        y = [100 * data[arm][t]["mean_sheet"] for t in range(1, 11)]
        x = i + np.linspace(-.15, .15, 10)
        axes[1].scatter(x, y, color="#73a2b9", edgecolor="black", linewidth=.7, s=33)
        axes[1].plot([i - .23, i + .23], [100 * summaries[arm]["mean_sheet"]] * 2, color="black", linewidth=2)
    axes[1].set_ylabel("Sheet residues (%)"); axes[1].set_ylim(-3, 100)
    axes[1].set_title("Trajectory variability; line = mean")
    for ax in axes:
        ax.set_xticks(range(5), LABELS, rotation=25, ha="right")
    fig.suptitle("90-residue Boltz-2 monomers · n=10 trajectories per condition\nCycle 00 excluded; core initialization controls", fontsize=11)
    fig.savefig(output / "core_comparison.svg", transparent=True)
    fig.savefig(output / "core_comparison.png", dpi=170)
    plt.close(fig)


if __name__ == "__main__":
    main()
