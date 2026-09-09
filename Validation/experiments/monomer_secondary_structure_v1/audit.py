#!/usr/bin/env python3
"""Read-only structural audit and trajectory-level monomer control comparison."""
from __future__ import annotations

import argparse
from collections import Counter
import csv
import json
import math
from pathlib import Path
import random
import statistics
import subprocess
import sys

import campaign as study

sys.path.insert(0, str(study.SOURCE / "scripts"))
from initialization_assessment import assess_structure
from initialization_refinement import Refinement
from secondary_structure_control import generate_sequence

METRICS = ("helix", "sheet", "coil", "plddt", "uncertain_coil_fraction", "sequence_entropy")
ASSESSMENT = dict(max_attempts=1, min_uncertain_coil_length=16, confidence_threshold=50)


def option(args, name, default=None):
    return args[args.index(name) + 1] if name in args else default


def evaluate(path, sequence):
    assessment = assess_structure(path, sequence, ASSESSMENT)
    counts = Counter(sequence.replace("X", ""))
    total = sum(counts.values())
    return {**assessment["fractions"], "plddt": statistics.mean(assessment["confidence"]),
            "uncertain_coil_fraction": sum(r["end"] - r["start"] + 1 for r in assessment["reconsider_regions"]) / len(sequence),
            "sequence_entropy": -sum((n / total) * math.log2(n / total) for n in counts.values()) if total else None,
            "psea": assessment["psea"], "per_residue_confidence": assessment["confidence"],
            "coil_segments": assessment["coil_segments"]}


def check_prediction_logs(root):
    logs = sorted(root.rglob("predict.log"))
    study.require(bool(logs), "Missing predictor logs")
    svd = []
    for path in logs:
        content = path.read_text(errors="replace")
        study.require("gpu available: true (mps), used: true" in content.lower(),
                      f"Missing explicit MPS execution evidence: {path}")
        for line in content.splitlines():
            lower = line.lower()
            if ("fallback" in lower or "fall back" in lower) and ("cpu" in lower or "=1" in lower):
                if "linalg_svd" in lower:
                    svd.append({"log": str(path.relative_to(root)), "line": line})
                else:
                    study.require(False, f"Forbidden CPU fallback: {path}: {line}")
    return svd


def audit(phase, arm_name):
    study.prepare()
    audit_path = study.OUTPUT / "audits" / phase / f"{arm_name}.json"
    if audit_path.exists():
        value = study.read(audit_path)
        study.require(value["manifest_sha256"] == study.sha(study.OUTPUT / "manifest.json"), "Audit belongs to another manifest")
        for name, checksum in value["raw_sha256"].items():
            study.require(study.sha(study.OUTPUT / name) == checksum, f"Completed raw output changed: {name}")
        return value
    job = study.read(study.OUTPUT / "jobs" / phase / f"{arm_name}.json")
    state = study.ctl("job-status", job["id"])
    study.atomic(study.OUTPUT / "status" / phase / f"{arm_name}.json", state)
    study.require(state["status"] in {"completed", "failed"}, "Only terminal jobs can be audited")
    root = study.OUTPUT / "campaigns" / f"{phase}__{arm_name}"
    # Use the shipped read-profile overview before examining raw coordinate data.
    command = ("import json,sys; sys.path.insert(0,sys.argv[1]); from server import MCPServer; "
               "print(json.dumps(MCPServer('read').tool_call('results_overview',{'run_id':sys.argv[2]})))")
    overview = subprocess.run([sys.executable, "-c", command, str(study.RUNTIME / "mcp"),
                               f"{study.PROJECT}/{phase}__{arm_name}"], capture_output=True, text=True, check=True)
    study.atomic(study.OUTPUT / "overviews" / phase / f"{arm_name}.json", json.loads(overview.stdout))
    plan = study.read(study.OUTPUT / "plans" / phase / f"{arm_name}.json")
    args = plan["normalized_request"]["arguments"]
    c, arm = study.CONFIG["campaign"], study.CONFIG["arms"][arm_name]
    count = int(option(args, "--num-runs"))
    offset = 0 if phase == "pilot" else c["pilot_trajectories"]
    study.require(option(args, "--design-scheduler") == "run" and option(args, "--predictor") == "boltz", "Execution policy differs")
    study.require(count == (1 if phase == "pilot" else 9), "Requested trajectory count differs")
    snapshot = root / ".studio_runtime/pipeline"
    stage = study.read(study.OUTPUT / "stage_receipt.json")
    for name in ("nanohunter_run.sh", "scripts/secondary_structure_control.py", "scripts/initialization_refinement.py", "scripts/initialization_assessment.py"):
        study.require(study.sha(snapshot / name) == stage["files"][name]["after_sha256"], f"Snapshot code changed: {name}")
    rows, trajectories, inspections = [], [], []
    runs = sorted(path for path in root.glob("run_*") if path.is_dir())
    study.require([p.name for p in runs] == [f"run_{i:03d}" for i in range(1, count + 1)], "Missing or unexpected trajectory directories")
    exhausted_count = 0
    for local_index, run in enumerate(runs, 1):
        global_index = local_index + offset
        seed_plan = study.read(run / "secondary_structure_plan.json")
        expected_seed = c["binder_seed"] + global_index
        study.require(seed_plan["sampling_seed"] == expected_seed, "Initialization seed differs from pairing contract")
        study.require(seed_plan["mode"] == arm["mode"] and seed_plan["percent_x"] == arm["mask_percent"], "Seed controls differ")
        regenerated, regenerated_plan = generate_sequence(c["length"], c["length"], arm["mask_percent"], "boltz", expected_seed,
            arm["mode"], arm["anti_helix_strength"], arm["beta_strength"], arm["beta_pattern_strength"], arm["turn_strength"],
            arm["loopkill"], arm["scope"] if arm["mode"] != "none" else "seed-and-cycles", arm["sampling_order"])
        study.require(regenerated_plan == seed_plan, "Initialization plan does not replay from declared parameters")
        if "inspection" in arm:
            journal = Refinement(run / "initialization_refinement")
            status = journal.status()
            study.require(status["state"] in {"accepted", "budget_exhausted"}, "Inspection did not reach a declared terminal decision")
            exhausted = status["state"] == "budget_exhausted"
            for attempt in sorted(journal.root.glob("attempt_*")):
                candidate = study.read(attempt / "input.json")
                structure = next((attempt / "prediction").glob("model_0.*"))
                inspections.append({"arm": arm_name, "trajectory": global_index, "attempt": candidate["index"],
                                    "selected": candidate["index"] == status["selected_attempt"],
                                    "changes": candidate["changes"], **evaluate(structure, candidate["sequence"])})
        else:
            exhausted, status = False, {"recorded_attempts": 1, "selected_attempt": 0}
            study.require(not (run / "initialization_refinement").exists(), "Unrequested refinement ran in a control arm")
        expected_cycles = [0] if exhausted else list(range(c["optimization_cycles"] + 1))
        metric_rows = list(csv.DictReader((run / "metrics_per_cycle.csv").open()))
        study.require([int(row["cycle"]) for row in metric_rows] == expected_cycles, "Missing/unexpected optimization cycles")
        exit_code = int((run / "run_exit_code.txt").read_text().strip())
        study.require((exit_code != 0) == exhausted, "Run exit status does not match initialization outcome")
        exhausted_count += int(exhausted)
        this_run = []
        for row in metric_rows:
            cycle = int(row["cycle"])
            directory = run / f"cycle_{cycle:02d}"
            structures = [directory / "pred_min" / name for name in ("model_0.cif", "model_0.pdb") if (directory / "pred_min" / name).is_file()]
            study.require(len(structures) == 1, "Normalized prediction cardinality is not one")
            confidence = study.read(directory / "pred_min/confidence.json")
            study.require(bool(confidence), "Empty confidence artifact")
            raw_structures = [p for p in (directory / "boltz").glob("boltz_results_*/predictions/*/*")
                              if p.suffix in {".cif", ".pdb"}]
            study.require(len(raw_structures) == 1, "Raw predictor cardinality differs from one")
            sequence = row["binder_sequence"]
            study.require(len(sequence) == c["length"], "Monomer length differs from 90")
            if cycle == 0:
                study.require(sequence == regenerated, "Original sequence was overwritten or differs from the sampler")
            else:
                study.require("X" not in sequence, "Optimized sequence contains unresolved masks")
            result = {"arm": arm_name, "phase": phase, "trajectory": global_index, "cycle": cycle,
                      "sequence": sequence, "structure": str(structures[0].relative_to(study.OUTPUT)),
                      **evaluate(structures[0], sequence)}
            rows.append(result); this_run.append(result)
            if not exhausted and cycle < c["optimization_cycles"]:
                mpnn = directory / "ligandmpnn"
                expected_mpnn_seed = c["mpnn_seed"] + 1000 * global_index + cycle
                study.require(int((mpnn / "seed.txt").read_text()) == expected_mpnn_seed, "MPNN seed pairing differs")
                bias_path = mpnn / "secondary_structure_bias.json"
                study.require(bias_path.exists() == (arm["mode"] != "none" and arm["scope"] == "seed-and-cycles"), "Prior scope differs during normal MPNN")
        summary = {"arm": arm_name, "phase": phase, "trajectory": global_index,
                   "outcome": "budget_exhausted" if exhausted else "completed", "attempts": status["recorded_attempts"],
                   "selected_attempt": status["selected_attempt"], "completed_cycles": len(this_run) - 1}
        if not exhausted:
            timing = list(csv.DictReader((run / "timing_run.csv").open()))
            study.require(len(timing) == 1 and float(timing[0]["duration_sec"]) > 0, "Missing trajectory timing")
            summary["wall_seconds_including_initialization"] = float(timing[0]["duration_sec"])
            for metric in METRICS:
                summary["mean_" + metric] = statistics.mean(r[metric] for r in this_run if r["cycle"] > 0)
                summary["final_" + metric] = this_run[-1][metric]
        trajectories.append(summary)
    study.require(state["status"] == ("failed" if exhausted_count else "completed"), "Unexpected job failure beyond recorded exhaustion")
    svd_lines = check_prediction_logs(root)
    raw_files = [p for p in root.rglob("*") if p.is_file() and ".studio_runtime" not in p.parts
                 and "__pycache__" not in p.parts and "matplotlib" not in p.parts]
    hashes = {str(p.relative_to(study.OUTPUT)): study.sha(p) for p in raw_files}
    value = {"schema": 1, "phase": phase, "arm": arm_name, "operational_passed": True,
             "job": study.compact(state), "trajectories": trajectories, "structures": rows, "inspections": inspections,
             "raw_sha256": hashes, "exhausted": exhausted_count,
             "svd_fallback_log_lines": svd_lines,
             "analysis_criteria": ASSESSMENT, "manifest_sha256": study.sha(study.OUTPUT / "manifest.json")}
    study.atomic(audit_path, value)
    return value


def paired_summary(left, right, metric, seed=905026, replicates=10000):
    keys = sorted(left.keys() & right.keys())
    differences = [right[key][metric] - left[key][metric] for key in keys]
    if not differences:
        return {"n_pairs": 0, "mean_difference": None, "bootstrap_95_ci": None}
    rng = random.Random(seed)
    draws = sorted(statistics.mean(rng.choices(differences, k=len(differences))) for _ in range(replicates))
    return {"n_pairs": len(keys), "mean_difference": statistics.mean(differences),
            "bootstrap_95_ci": [draws[int(.025 * (replicates - 1))], draws[int(.975 * (replicates - 1))]],
            "trajectory_differences": dict(zip(map(str, keys), differences))}


def report():
    manifest = study.prepare()
    data, summaries, contrasts = {}, {}, {}
    for arm in study.CONFIG["arms"]:
        audits = [audit(phase, arm) for phase in ("pilot", "remaining")]
        rows = [row for a in audits for row in a["trajectories"]]
        study.require(sorted(r["trajectory"] for r in rows) == list(range(1, 11)), "Final n is not the declared ten trajectories")
        data[arm] = {r["trajectory"]: r for r in rows if r["outcome"] == "completed"}
        summaries[arm] = {"declared_n": 10, "completed_n": len(data[arm]), "exhausted_n": 10 - len(data[arm]),
                          "mean_attempts": statistics.mean(r["attempts"] for r in rows),
                          "mean_wall_seconds_completed": statistics.mean(r["wall_seconds_including_initialization"] for r in data[arm].values()) if data[arm] else None,
                          **{metric: statistics.mean(r["mean_" + metric] for r in data[arm].values()) if data[arm] else None for metric in METRICS}}
    for name, arm in study.CONFIG["arms"].items():
        if arm["reference"]:
            contrasts[name] = {metric: paired_summary(data[arm["reference"]], data[name], "mean_" + metric) for metric in METRICS}
    value = {"schema": 1, "complete": True, "methods": study.CONFIG["methods"], "summaries": summaries,
             "paired_contrasts": contrasts, "manifest_sha256": study.sha(study.OUTPUT / "manifest.json"),
             "limitations": ["One length, predictor, model and declared seed cohort; exploratory one-factor screen.",
                             "Fold-composition summaries are conditional on completion and show their n; initialization attrition is retained separately.",
                             "Bootstrap intervals are paired by trajectory and are not adjusted for multiple comparisons.",
                             "No threshold/default promotion or experimental folding validation."]}
    study.atomic(study.OUTPUT / "analysis/report.json", value)
    output = study.OUTPUT / "analysis/summary.csv"
    with output.open("w") as handle:
        writer = csv.DictWriter(handle, fieldnames=["arm", *next(iter(summaries.values()))])
        writer.writeheader()
        for arm, row in summaries.items():
            writer.writerow({"arm": arm, **row})
    lines = ["# Monomer secondary-structure control benchmark", "", "90 residues; Boltz-2/SolubleMPNN; 10 declared trajectories per condition; cycles 01–05 averaged within each completed trajectory.", "",
             "| Condition | Completed / declared | Exhausted | Helix | Sheet | Coil | pLDDT |", "|---|---:|---:|---:|---:|---:|---:|"]
    for arm, row in summaries.items():
        values = [f"{row[k]:.1%}" if row[k] is not None else "—" for k in ("helix", "sheet", "coil")]
        plddt = f"{row['plddt']:.1f}" if row["plddt"] is not None else "—"
        lines.append(f"| {arm} | {row['completed_n']}/10 | {row['exhausted_n']} | {' | '.join(values)} | {plddt} |")
    lines += ["", *value["limitations"], ""]
    (study.OUTPUT / "analysis/REPORT.md").write_text("\n".join(lines))
    plot(summaries)
    return value


def plot(summaries):
    import matplotlib.pyplot as plt
    import numpy as np
    plt.rcParams.update({"font.family": "Arial", "text.color": "black", "axes.labelcolor": "black",
                         "xtick.direction": "in", "ytick.direction": "in", "axes.grid": False})
    fig, ax = plt.subplots(figsize=(11, 10))
    names = list(summaries)
    left = np.zeros(len(names))
    for metric, color in (("helix", "#d5916c"), ("sheet", "#73a2b9"), ("coil", "#d5d5d5")):
        values = np.array([summaries[n][metric] or 0 for n in names])
        ax.barh(range(len(names)), values, left=left, label=metric, color=color, edgecolor="black", linewidth=.6)
        left += values
    ax.set_yticks(range(len(names)), [f"{n} (n={summaries[n]['completed_n']}/10)" for n in names])
    ax.invert_yaxis(); ax.set_xlim(0, 1); ax.set_xlabel("Fraction of residues; mean of trajectory means, cycles 01–05")
    ax.legend(loc="lower right"); fig.tight_layout()
    fig.savefig(study.OUTPUT / "analysis/secondary_structure.svg", transparent=True)
    fig.savefig(study.OUTPUT / "analysis/secondary_structure.png", dpi=160)
    plt.close(fig)


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--phase", choices=["pilot", "remaining"])
    p.add_argument("--arm", choices=list(study.CONFIG["arms"]))
    p.add_argument("--report", action="store_true")
    args = p.parse_args()
    value = report() if args.report else audit(args.phase, args.arm)
    study.emit({k: value[k] for k in ("complete", "phase", "arm", "operational_passed", "exhausted") if k in value})


if __name__ == "__main__":
    main()
