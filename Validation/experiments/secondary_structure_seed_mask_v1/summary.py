#!/usr/bin/env python3
"""Summarize the completed, audited ten-pair seed-only experiment.

Uses trajectory means, never treats the five related optimized cycles as
independent observations. Scientific target attainment is reported separately
from the completed-output audit. No settings promotion is implied.
"""
from __future__ import annotations

import argparse
from collections import Counter
import csv
import hashlib
import json
import math
from pathlib import Path
import random
import statistics

ARMS = ("beta_seed_only", "mixed_seed_only")
METRICS = (
    "helix_fraction", "sheet_fraction", "coil_fraction", "iptm", "ipsae_min",
    "complex_plddt", "binder_plddt", "sequence_entropy_bits", "max_residue_fraction",
    "max_identical_residue_run",
)
BOOTSTRAP_SEED = 927315
BOOTSTRAP_REPLICATES = 20000


def require(condition, message):
    if not condition:
        raise ValueError(message)


def number(value, label):
    result = float(value)
    require(math.isfinite(result), f"nonfinite {label}")
    return result


def percentile(values, fraction):
    values = sorted(values)
    position = (len(values) - 1) * fraction
    lower = math.floor(position)
    upper = math.ceil(position)
    return values[lower] + (values[upper] - values[lower]) * (position - lower)


def paired_bootstrap(differences, seed=BOOTSTRAP_SEED, replicates=BOOTSTRAP_REPLICATES):
    require(len(differences) == 10, "paired inference requires all ten trajectory pairs")
    require(replicates >= 100, "too few bootstrap replicates")
    rng = random.Random(seed)
    means = [statistics.mean(rng.choices(differences, k=len(differences))) for _ in range(replicates)]
    return {
        "mean_difference": statistics.mean(differences),
        "paired_bootstrap_95_ci": [percentile(means, 0.025), percentile(means, 0.975)],
        "pairs_increased": sum(value > 0 for value in differences),
        "pairs_decreased": sum(value < 0 for value in differences),
        "pairs_unchanged": sum(value == 0 for value in differences),
        "trajectory_differences": differences,
    }


def build_comparison(report, manifest, trajectories, structures):
    config = manifest["config"]
    require(manifest["phase"] == "full", "only the declared full phase can enter this summary")
    require(report.get("passed") is True and report.get("all_complete") is True, "full operational audit must pass before summary")
    require(set(report["arms"]) == set(config["arms"]) == set(ARMS), "unexpected or missing comparison arm")
    require(config["campaign"]["full_trajectories"] == 10 and config["campaign"]["design_cycles"] == 5, "expected ten trajectories of five optimized cycles")
    require(report.get("audited_structures") == report.get("expected_structures") == 120, "full audit must contain 120 structures including 20 initialization structures")
    require(len(trajectories) == 20 and len(structures) == 120, "derived CSV cardinality differs from declaration")
    expected_runs = {f"run_{index:03d}" for index in range(1, 11)}
    by_arm = {}
    for arm in ARMS:
        rows = [row for row in trajectories if row["arm"] == arm]
        require(len(rows) == 10 and {row["run"] for row in rows} == expected_runs, f"missing/duplicate paired trajectory in {arm}")
        require(report["arm_audits"][arm]["audit_status"] == "audited_complete", f"arm was not audited: {arm}")
        by_arm[arm] = {row["run"]: row for row in rows}
        arm_structures = [row for row in structures if row["arm"] == arm]
        expected_keys = {(run, cycle) for run in expected_runs for cycle in range(6)}
        actual_keys = {(row["run"], int(row["cycle"])) for row in arm_structures}
        require(len(arm_structures) == 60 and actual_keys == expected_keys, f"structure CSV run/cycle mismatch in {arm}")
        for prefix, endpoint in (("optimized_mean", "optimized_cycle_mean"), ("final", "final_cycle")):
            for metric in METRICS:
                observed = statistics.mean(number(row[f"{prefix}_{metric}"], f"{arm}/{metric}") for row in rows)
                expected = report["arms"][arm]["endpoints"][endpoint][metric]
                require(abs(observed - expected) < 1e-10, f"trajectory CSV differs from audited report: {arm}/{endpoint}/{metric}")
                selected = [row for row in arm_structures if int(row["cycle"]) > 0] if prefix == "optimized_mean" else [row for row in arm_structures if int(row["cycle"]) == 5]
                structural_mean = statistics.mean(number(row[metric], f"structure {arm}/{metric}") for row in selected)
                require(abs(structural_mean - expected) < 1e-10, f"structure CSV differs from audited report: {arm}/{endpoint}/{metric}")

    endpoints = {}
    for prefix, endpoint in (("optimized_mean", "optimized_cycle_mean"), ("final", "final_cycle")):
        contrast = {}
        for metric in METRICS:
            differences = [number(by_arm[ARMS[1]][run][f"{prefix}_{metric}"], metric) - number(by_arm[ARMS[0]][run][f"{prefix}_{metric}"], metric) for run in sorted(expected_runs)]
            contrast[metric] = paired_bootstrap(differences)
        arm_values = {}
        for arm in ARMS:
            selected = [row for row in structures if row["arm"] == arm and (int(row["cycle"]) > 0 if prefix == "optimized_mean" else int(row["cycle"]) == 5)]
            counts = Counter("".join(row["sequence"] for row in selected))
            require("X" not in counts and sum(counts.values()) == 90 * len(selected), f"invalid optimized sequences in {arm}")
            arm_values[arm] = {
                "mean": {metric: report["arms"][arm]["endpoints"][endpoint][metric] for metric in METRICS},
                "amino_acid_fraction": {aa: count / sum(counts.values()) for aa, count in sorted(counts.items())},
                "worst_observed_max_residue_fraction": max(float(row["max_residue_fraction"]) for row in selected),
                "worst_observed_identical_residue_run": max(int(row["max_identical_residue_run"]) for row in selected),
                "minimum_observed_sequence_entropy_bits": min(float(row["sequence_entropy_bits"]) for row in selected),
                "sequence_diversity": report["arms"][arm]["sequence_diversity"]["all_optimized_cycles" if prefix == "optimized_mean" else "final_cycle_across_trajectories"],
            }
        endpoints[endpoint] = {"arms": arm_values, "mixed_minus_beta": contrast}
    return {
        "schema": 1,
        "method": {
            "primary_endpoint": "mean of cycles 01–05 within each trajectory, followed by equal-weight mean of 10 trajectories per arm",
            "primary_contrast": "mixed seed-only minus beta seed-only, paired by trajectory seed",
            "secondary_endpoint": "cycle 05 across 10 paired trajectories",
            "initialization": "90-residue full sequence sampled before 45 independent X masks; cycle 00 excluded from design endpoints",
            "replicates": 10,
            "optimized_structures_per_arm": 50,
            "bootstrap": {"method": "paired trajectory percentile bootstrap", "replicates": BOOTSTRAP_REPLICATES, "seed": BOOTSTRAP_SEED, "confidence": 0.95},
            "uncertainty": "conditional on this target/model/configuration; ten trajectory seeds are the independent units; intervals are not adjusted for multiple metrics",
        },
        "operational_passed": report["passed"],
        "scientific_decision": report.get("decision_rule_evaluation"),
        "endpoints": endpoints,
        "initial_seed_composition": {arm: {run: {key: plan[key] for key in ("unmasked_composition", "visible_seed_composition")} for run, plan in report["arm_audits"][arm]["seed_plans"].items()} for arm in ARMS},
        "limitations": [
            "One target and one prediction/design configuration; structure predictions do not validate physical folding or binding.",
            "Full trajectory 001 repeats the smoke seed and is counted once; smoke is not an extra replicate.",
            "Both arms use seed-only controls; later SolubleMPNN redesign has no secondary-structure prior.",
            "Historical natural and weaker beta controls differ in sampler order and strength and are descriptive comparisons only.",
            "Scientific target failure does not invalidate a completed operationally sound experiment; no default setting is promoted.",
        ],
    }


def markdown(result):
    names = {"helix_fraction": "Helix", "sheet_fraction": "Sheet", "coil_fraction": "Coil", "iptm": "iPTM", "ipsae_min": "ipSAE", "complex_plddt": "Complex pLDDT", "binder_plddt": "Binder pLDDT", "sequence_entropy_bits": "Sequence entropy (bits)", "max_residue_fraction": "Largest residue fraction", "max_identical_residue_run": "Longest identical-residue run"}
    percentage = {"helix_fraction", "sheet_fraction", "coil_fraction", "max_residue_fraction"}
    lines = ["# Seed sampling before 50% X masking: full comparison", "", "Both arms completed 10 trajectories of five optimized cycles. Primary values average cycles 01–05 within each trajectory, then average the 10 trajectories. Cycle 00 is excluded. The paired contrast is mixed minus beta-only; 95% intervals resample whole trajectory pairs 20,000 times.", ""]
    for endpoint, title in (("optimized_cycle_mean", "Primary: cycles 01–05 trajectory means"), ("final_cycle", "Secondary: final cycle 05")):
        data = result["endpoints"][endpoint]
        lines += [f"## {title}", "", "| Measure | Beta seed only | Beta + helix-kill seed only | Mixed − beta (95% CI) |", "|---|---:|---:|---:|"]
        for metric in METRICS:
            scale = 100 if metric in percentage or metric.endswith("plddt") else 1
            unit = "%" if metric in percentage else ""
            difference_unit = " pp" if metric in percentage else ""
            first = data["arms"][ARMS[0]]["mean"][metric] * scale
            second = data["arms"][ARMS[1]]["mean"][metric] * scale
            contrast = data["mixed_minus_beta"][metric]
            low, high = [value * scale for value in contrast["paired_bootstrap_95_ci"]]
            decimals = 1 if scale == 100 else 3
            lines.append(f"| {names[metric]} | {first:.{decimals}f}{unit} | {second:.{decimals}f}{unit} | {contrast['mean_difference'] * scale:+.{decimals}f}{difference_unit} ({low:+.{decimals}f}, {high:+.{decimals}f}) |")
        lines += ["", "pLDDT is shown on a 0–100 scale. Largest residue fraction and longest run are means of per-sequence values.", ""]
        for arm in ARMS:
            values = data["arms"][arm]
            diversity = values["sequence_diversity"]
            identity = diversity["mean_pairwise_identity"]
            lines.append(f"- {arm}: {diversity['unique_sequences']}/{diversity['sequences']} unique sequences; mean pairwise identity {identity:.1%}; lowest sequence entropy {values['minimum_observed_sequence_entropy_bits']:.3f} bits; largest observed residue fraction {values['worst_observed_max_residue_fraction']:.1%}; longest observed identical-residue run {values['worst_observed_identical_residue_run']}.")
        lines.append("")
    lines += ["## Declared structural target", "", "Operational audit passed for both arms. The scientific criterion is mean sheet ≥25% and mean helix <40% across all 10 complete trajectories.", ""]
    decision = result["scientific_decision"]
    if decision:
        for arm, values in decision["arms"].items():
            lines.append(f"- {arm}: {'met' if values['meets_declared_rule'] else 'not met'}; sheet {values['sheet_mean']:.1%}, helix {values['helix_mean']:.1%}.")
    lines += ["", "## Interpretation limits", "", *[f"- {value}" for value in result["limitations"]], "", "Bootstrap intervals describe seed-to-seed variability for this single target and configuration and are not adjusted for multiple metrics.", ""]
    return "\n".join(lines)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, required=True)
    parser.add_argument("--analysis-dir", type=Path)
    args = parser.parse_args()
    analysis = args.analysis_dir or args.root / "analysis" / "full"
    inputs = {"report": analysis / "audit.json", "manifest": args.root / "manifest_full.json", "trajectories": analysis / "audited_per_trajectory.csv", "structures": analysis / "audited_per_structure.csv"}
    report = json.loads(inputs["report"].read_text())
    manifest = json.loads(inputs["manifest"].read_text())
    require(report["raw_sha256"].get("manifest_full.json") == hashlib.sha256(inputs["manifest"].read_bytes()).hexdigest(), "manifest changed after the completed audit")
    with inputs["trajectories"].open(newline="") as stream:
        trajectories = list(csv.DictReader(stream))
    with inputs["structures"].open(newline="") as stream:
        structures = list(csv.DictReader(stream))
    comparison = build_comparison(report, manifest, trajectories, structures)
    comparison["input_sha256"] = {name: hashlib.sha256(path.read_bytes()).hexdigest() for name, path in inputs.items()}
    (analysis / "comparison.json").write_text(json.dumps(comparison, indent=2, sort_keys=True) + "\n")
    (analysis / "comparison.md").write_text(markdown(comparison))
    print(json.dumps({"comparison": str(analysis / "comparison.md"), "data": str(analysis / "comparison.json"), "operational_passed": comparison["operational_passed"], "scientific_decision": comparison["scientific_decision"]}, indent=2))


if __name__ == "__main__":
    main()
