"""Full or explicitly partial analysis, retaining failed declared trajectories."""
import argparse
from collections import Counter
from datetime import datetime, timezone
import csv
import json
from pathlib import Path
import statistics as stats

import recover as recovery
c, a = recovery.c, recovery.a


def analyze(full=False):
    c.prepare()
    paths = sorted((c.OUTPUT / "audits").glob("*/*.json"))
    audits = [recovery.verify_audit(c.read(p)) for p in paths]
    supplement = recovery.RECOVERY / "geometry_failure_audit.json"
    c.require(supplement.exists(), "Diagnosed failed cohort requires its supplemental audit")
    audits.append(recovery.verify_audit(c.read(supplement)))
    paths.append(supplement)
    rows = [r for d in audits for r in d["trajectories"]]
    identities = [(r["arm"], r["trajectory"]) for r in rows]
    c.require(len(identities) == len(set(identities)), "Duplicate trajectories")
    counts = Counter(r["outcome"] for r in rows)
    complete = len(rows) == 220
    if full:
        c.require(complete, "Full report requested before all 220 trajectories have outcomes")
    summaries, data, contrasts, baseline_contrasts = {}, {}, {}, {}
    for arm in c.CONFIG["arms"]:
        arm_rows = [r for r in rows if r["arm"] == arm]
        if len(arm_rows) != 10:
            continue
        c.require(sorted(r["trajectory"] for r in arm_rows) == list(range(1, 11)), "Cohort seed identities differ")
        data[arm] = {r["trajectory"]: r for r in arm_rows if r["outcome"] == "completed"}
        summaries[arm] = {"declared_n": 10, "completed_n": len(data[arm]),
                          "outcomes": dict(Counter(r["outcome"] for r in arm_rows)),
                          "mean_attempts": stats.mean(r["attempts"] for r in arm_rows),
                          **{prefix + metric: stats.mean(r[prefix + metric] for r in data[arm].values()) if data[arm] else None
                             for prefix in ("mean_", "final_") for metric in a.METRICS}}
    for arm, d in data.items():
        ref = c.CONFIG["arms"][arm]["reference"]
        if ref in data:
            contrasts[arm] = {"reference": ref,
                              "metrics": {m: a.paired_summary(data[ref], d, "mean_" + m) for m in a.METRICS}}
        if arm != "baseline":
            baseline_contrasts[arm] = {m: a.paired_summary(data["baseline"], d, "mean_" + m) for m in a.METRICS}
    # Independently reconcile summary denominators with the residue assignments.
    for d in audits:
        for t in d["trajectories"]:
            if t["outcome"] != "completed":
                continue
            cycle_rows = [r for r in d["structures"] if r["trajectory"] == t["trajectory"] and r["cycle"] > 0]
            c.require(sorted(r["cycle"] for r in cycle_rows) == list(range(1, 6)), "Optimized cardinality differs")
            for metric, code in (("helix", "a"), ("sheet", "b"), ("coil", "c")):
                value = stats.mean(r["psea"].count(code) / 90 for r in cycle_rows)
                c.require(abs(value - t["mean_" + metric]) < 1e-12, "Composition aggregation differs")
            c.require(abs(stats.mean(stats.mean(r["per_residue_confidence"]) for r in cycle_rows) - t["mean_plddt"]) < 1e-10,
                      "Confidence aggregation differs")
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    output = recovery.RECOVERY / "reports" / stamp
    output.mkdir(parents=True)
    for p in recovery.HERE.glob("*.py"):
        (output / p.name).write_bytes(p.read_bytes())
    status = {str(p.relative_to(c.OUTPUT)): c.read(p) for p in (c.OUTPUT / "status").glob("*/*.json")}
    c.atomic(output / "status_snapshot.json", status)
    result = {"as_of_utc": stamp, "complete": complete, "declared_trajectories": 220,
              "audited_trajectories": len(rows), "outcomes": dict(counts),
              "optimized_structures": 5 * counts["completed"], "complete_cohorts": list(summaries),
              "pending_cohorts": [n for n in c.CONFIG["arms"] if n not in summaries],
              "summaries": summaries, "predeclared_contrasts": contrasts,
              "additional_exploratory_baseline_contrasts": baseline_contrasts,
              "manifest_sha256": c.sha(c.OUTPUT / "manifest.json"),
              "input_audit_sha256": {str(p.relative_to(c.OUTPUT)): c.sha(p) for p in paths},
              "geometry_rejection": audits[-1]["rejection"],
              "methods": "Mean cycles 01–05 within each completed trajectory, then equal trajectory weights; Biotite P-SEA; CA pLDDT 0–100; 10,000 paired bootstrap resamples; no multiplicity adjustment.",
              "limits": ["Conditional structural summaries exclude failed trajectories but explicitly report their n and failure category.",
                         "Cycle 00 and rejected geometry never enter optimization endpoints.",
                         "Only one length/predictor/seed cohort. Coil is not a disorder diagnosis. No experimental folding validation or default promotion."]}
    c.atomic(output / "report.json", result)
    fields = ["arm", "completed_n", "declared_n", "mean_helix", "mean_sheet", "mean_coil", "mean_plddt", "final_plddt", "mean_attempts"]
    with (output / "summary.csv").open("w") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields, extrasaction="ignore")
        writer.writeheader(); writer.writerows({"arm": arm, **s} for arm, s in summaries.items())
    label = "Full campaign" if complete else "Partial campaign: remaining conditions unfinished"
    lines = [f"# Monomer secondary-structure analysis — {label}", "", f"Snapshot UTC: {stamp}", "",
             f"Audited {len(rows)}/220 declared trajectories: {dict(counts)}. Optimized structures: {result['optimized_structures']}.", "",
             result["methods"], "", "All listed conditions have ten declared outcomes; composition/confidence are conditional on completing five cycles.", "",
             "| Condition | Completed / declared | Helix | Sheet | Coil | pLDDT | Final pLDDT |", "|---|---:|---:|---:|---:|---:|---:|"]
    for arm, s in summaries.items():
        values = [f"{100*s['mean_'+m]:.1f}%" if s['mean_'+m] is not None else "—" for m in ("helix", "sheet", "coil")]
        confidence = [f"{s[k]:.1f}" if s[k] is not None else "—" for k in ("mean_plddt", "final_plddt")]
        lines.append(f"| {arm} | {s['completed_n']}/10 | {' | '.join(values + confidence)} |")
    lines += ["", "## Paired changes versus declared reference", "",
              "Fractions expressed as percentage-point changes; brackets show exploratory paired 95% bootstrap intervals.", "",
              "| Condition vs reference | n pairs | Δ helix | Δ sheet | Δ coil | Δ pLDDT |", "|---|---:|---:|---:|---:|---:|"]
    for arm, contrast in contrasts.items():
        cells = []
        for metric in ("helix", "sheet", "coil", "plddt"):
            d = contrast["metrics"][metric]; scale = 1 if metric == "plddt" else 100
            if not d["n_pairs"]:
                cells.append("—"); continue
            low, high = d["bootstrap_95_ci"]
            cells.append(f"{scale*d['mean_difference']:+.1f} [{scale*low:+.1f}, {scale*high:+.1f}]")
        lines.append(f"| {arm} vs {contrast['reference']} | {contrast['metrics']['sheet']['n_pairs']} | {' | '.join(cells)} |")
    lines += ["", "## Failure and completion accounting", "",
              "Sample-then-mask global trajectory 2 was rejected at cycle 00: A:87–88 C–N distance 2.29 Å exceeds the existing 2.2 Å limit. It remains a geometry failure; no retry, replacement, threshold relaxation or normal optimization was performed. Its eight completed companions passed a separate structural audit, giving 9/10 completed trajectories including the pilot.", "",
              "Initialization exhaustion is retained separately from geometry rejection. The original controller stopped at this technical failure. A recorded continuation runs the untouched remaining conditions through their original public Studio plans and audit gates.", "",
              "Pending full cohorts: " + (", ".join(result["pending_cohorts"]) or "none"), "", *result["limits"], ""]
    (output / "REPORT.md").write_text("\n".join(lines))
    plot(output, summaries)
    c.atomic(recovery.RECOVERY / "latest_report.json", {"path": str(output), "complete": complete, "report_sha256": c.sha(output / "report.json")})
    print(json.dumps({"output": str(output), "complete": complete, "audited": len(rows), "outcomes": dict(counts)}))
    return result


def plot(output, summaries):
    import matplotlib.pyplot as plt
    import numpy as np
    plt.rcParams.update({"font.family": "Arial", "text.color": "black", "axes.labelcolor": "black", "axes.edgecolor": "black",
                         "xtick.direction": "in", "ytick.direction": "in", "axes.grid": False})
    names = list(summaries); y = np.arange(len(names)); left = np.zeros(len(names))
    fig, axes = plt.subplots(1, 2, figsize=(12, max(6, .37 * len(names))), gridspec_kw={"width_ratios": [2, 1]}, layout="constrained")
    for metric, color in (("helix", "#d5916c"), ("sheet", "#73a2b9"), ("coil", "#d5d5d5")):
        values = np.array([100 * (summaries[n]["mean_" + metric] or 0) for n in names])
        axes[0].barh(y, values, left=left, label=metric, color=color, edgecolor="black", linewidth=.7); left += values
    axes[0].set_yticks(y, [f"{n} (n={summaries[n]['completed_n']}/10)" for n in names]); axes[0].invert_yaxis()
    axes[0].set_xlim(0,100); axes[0].set_xlabel("Residues (%)"); axes[0].legend(loc="upper center", bbox_to_anchor=(.5,1.08), ncol=3)
    axes[1].scatter([summaries[n]["mean_plddt"] for n in names], y, color="black", s=25)
    axes[1].set_yticks(y, []); axes[1].invert_yaxis(); axes[1].set_xlim(0,100); axes[1].set_xlabel("Mean CA pLDDT")
    fig.suptitle("90-residue Boltz-2 monomers · mean of trajectory means, cycles 01–05\nComplete declared cohorts only; n denotes completed trajectories", fontsize=11)
    fig.savefig(output / "comparison.svg", transparent=True); fig.savefig(output / "comparison.png", dpi=160); plt.close(fig)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__); parser.add_argument("--full", action="store_true")
    analyze(parser.parse_args().full)
