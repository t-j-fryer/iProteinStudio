#!/usr/bin/env python3
"""Audit immutable protein-binding outputs and report paired helix-kill effects."""
from __future__ import annotations

import argparse
from collections import Counter
import csv
import importlib.util
import json
import math
import random
import statistics
import sys
from pathlib import Path

import campaign as study

METRICS = ("helix", "sheet", "coil", "plddt", "iptm", "ipsae_min", "complex_plddt")


def _chain_sequence_and_sse(path, chain_id, expected_sequence, assign_sse=False):
    import numpy as np
    from biotite.sequence import ProteinSequence
    from biotite.structure import annotate_sse, get_residue_starts
    if path.suffix.lower() in {".cif", ".mmcif"}:
        from biotite.structure.io.pdbx import CIFFile, get_structure
        atoms = get_structure(CIFFile.read(path), model=1, extra_fields=["b_factor"])
    else:
        from biotite.structure.io.pdb import PDBFile
        atoms = PDBFile.read(path).get_structure(model=1, extra_fields=["b_factor"])
    study.require(len(atoms) and np.isfinite(atoms.coord).all(), f"Empty or nonfinite coordinates: {path}")
    atoms = atoms[atoms.chain_id == chain_id]
    study.require(len(atoms), f"Structure has no chain {chain_id}: {path}")
    starts = get_residue_starts(atoms, add_exclusive_stop=True)
    observed, confidence = [], []
    for start, end in zip(starts[:-1], starts[1:]):
        residue = atoms[start:end]
        ca = residue[residue.atom_name == "CA"]
        study.require(len(ca) == 1, f"Every residue requires exactly one CA atom: {path}")
        name = str(ca.res_name[0])
        observed.append("X" if name == "UNK" else ProteinSequence.convert_letter_3to1(name))
        confidence.append(float(ca.b_factor[0]))
    study.require(len(observed) == len(expected_sequence),
                  f"Chain {chain_id} length {len(observed)} != expected {len(expected_sequence)}: {path}")
    study.require(all(expected == "X" or expected == actual for expected, actual in zip(expected_sequence, observed)),
                  f"Chain {chain_id} sequence differs from the request: {path}")
    result = {"observed_sequence": "".join(observed), "confidence": confidence}
    if assign_sse:
        codes = "".join(annotate_sse(atoms))
        study.require(len(codes) == len(expected_sequence) and set(codes) <= {"a", "b", "c"},
                      f"Incomplete P-SEA assignment for chain {chain_id}: {path}")
        counts = Counter(codes)
        result.update({"psea": codes, "helix": counts["a"] / len(codes),
                       "sheet": counts["b"] / len(codes), "coil": counts["c"] / len(codes),
                       "plddt": statistics.mean(confidence)})
    return result


def evaluate(path, binder_sequence, target_sequence):
    binder = _chain_sequence_and_sse(path, "A", binder_sequence, assign_sse=True)
    target = _chain_sequence_and_sse(path, "B", target_sequence)
    confidence_path = path.with_name("confidence.json")
    study.require(confidence_path.is_file(), f"Missing normalized confidence: {confidence_path}")
    confidence = study.read(confidence_path)
    values = {}
    for name in ("iptm", "complex_plddt"):
        value = float(confidence[name])
        study.require(math.isfinite(value) and 0 <= value <= 1, f"Invalid {name}: {confidence_path}")
        values[name] = value
    ipsae = confidence.get("ipsae_min")
    if ipsae is not None:
        ipsae = float(ipsae)
        study.require(math.isfinite(ipsae) and 0 <= ipsae <= 1, f"Invalid ipSAE(min): {confidence_path}")
    return {**{key: binder[key] for key in ("helix", "sheet", "coil", "plddt", "psea")},
            **values, "ipsae_min": ipsae, "target_observed_sequence": target["observed_sequence"]}


def native_structures(directory, predictor):
    if predictor == "boltz":
        return [path for path in (directory / "boltz").glob("boltz_results_*/predictions/*/*")
                if path.suffix in (".cif", ".pdb")]
    if predictor == "intellifold":
        return [path for path in (directory / "intellifold").rglob("*")
                if path.suffix in (".cif", ".pdb") and "predictions" in path.parts]
    if predictor.startswith("protenix"):
        return [path for path in directory.rglob("*.cif") if "predictions" in path.parts and "pred_min" not in path.parts]
    return list(directory.rglob("*_model.cif")) + list(directory.rglob("*_model.pdb"))


def check_logs(root, predictor):
    logs = sorted(root.rglob("predict.log"))
    study.require(logs, "Missing native prediction logs")
    warnings, evidence = [], []
    markers_to_find = ("gpu available: true (mps), used: true", "iproteinstudio_device", "device=mps",
                       "device: mps", "device mps", "device(type='mps')", "metal", "mlx.core.gpu")
    for path in logs:
        content = path.read_text(errors="replace")
        markers = [line for line in content.splitlines() if any(marker in line.lower() for marker in markers_to_find)]
        study.require(markers, f"Missing explicit Apple GPU execution evidence: {path}")
        evidence.append({"path": str(path.relative_to(root)), "lines": markers})
        for line in content.splitlines():
            lower = line.lower()
            if ("fallback" in lower or "fall back" in lower) and ("cpu" in lower or "=1" in lower):
                if predictor == "boltz" and "linalg_svd" in lower:
                    warnings.append({"path": str(path.relative_to(root)), "line": line})
                else:
                    study.require(False, f"Forbidden CPU fallback: {path}: {line}")
    return warnings, evidence


def audit(phase, arm_name):
    manifest = study.prepare()
    path = study.OUTPUT / "audits" / phase / f"{arm_name}.json"
    if path.exists():
        value = study.read(path)
        study.require(value["manifest_sha256"] == study.sha(study.OUTPUT / "manifest.json"), "Audit identity changed")
        for relative, checksum in value["raw_sha256"].items():
            study.require(study.sha(study.OUTPUT / relative) == checksum, "Audited raw output changed")
        return value
    plan = study.read(study.OUTPUT / "plans" / phase / f"{arm_name}.json")
    state = study.read(study.OUTPUT / "status" / phase / f"{arm_name}.json")
    root = Path(plan["normalized_request"]["campaign"])
    arm, campaign = study.CONFIG["arms"][arm_name], study.CONFIG["campaign"]
    target_sequence = manifest["target"]["sequence"]
    offset = 0 if phase == "pilot" else campaign["pilot_trajectories"]
    count = campaign["pilot_trajectories"] if phase == "pilot" else campaign["trajectories"] - offset
    snapshot = root / ".studio_runtime/pipeline"
    stage = study.read(study.OUTPUT / "stage_receipt.json")
    for name in ("nanohunter_run.sh", "scripts/secondary_structure_control.py", "scripts/validate_prediction_geometry.py"):
        study.require(study.sha(snapshot / name) == stage["files"][name]["after_sha256"], f"Snapshot changed: {name}")
    spec = importlib.util.spec_from_file_location("geometry", snapshot / "scripts/validate_prediction_geometry.py")
    geometry = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(geometry)
    sys.path.insert(0, str(snapshot / "scripts"))
    from secondary_structure_control import generate_sequence

    trajectories, rows, failures = [], [], []
    for local in range(1, count + 1):
        global_index = local + offset
        run = root / f"run_{local:03d}"
        summary = {"arm": arm_name, "phase": phase, "trajectory": global_index,
                   "outcome": "failed", "completed_cycles": 0}
        if not run.exists():
            summary["outcome"] = "not_started"
            trajectories.append(summary)
            continue
        seed_plan = study.read(run / "secondary_structure_plan.json")
        sequence, expected = generate_sequence(
            campaign["length"], campaign["length"], 50, arm["predictor"],
            campaign["binder_seed"] + global_index, "antihelix", arm["strength"],
            0.5, 0.5, 0.5, 0, "seed-only", "mask-first",
        )
        study.require(seed_plan == expected, f"Initialization does not replay: {run}")
        study.require(not list(run.rglob("secondary_structure_bias.json")), "Secondary bias escaped initialization")
        metrics_path = run / "metrics_per_cycle.csv"
        metrics = list(csv.DictReader(metrics_path.open())) if metrics_path.exists() else []
        this_run = []
        for metric in metrics:
            cycle = int(metric["cycle"])
            directory = run / f"cycle_{cycle:02d}"
            structures = [directory / "pred_min" / name for name in ("model_0.cif", "model_0.pdb")
                          if (directory / "pred_min" / name).is_file()]
            study.require(len(structures) == 1, f"Normalized cardinality differs: {directory}")
            raw = native_structures(directory, arm["predictor"])
            study.require(len(raw) == 1, f"Native prediction cardinality differs ({len(raw)}): {directory}")
            binder_sequence = metric["binder_sequence"]
            study.require(len(binder_sequence) == campaign["length"]
                          and (binder_sequence == sequence if cycle == 0 else "X" not in binder_sequence),
                          "Binder sequence contract changed")
            diagnostics = geometry.inspect_geometry(structures[0])
            study.require(not diagnostics["errors"], f"Unusable coordinates: {diagnostics['errors']}")
            geometry_receipt = study.read(directory / "pred_min/geometry_report.json")
            study.require(geometry_receipt["policy"] == "record_only" and geometry_receipt["coordinate_input_usable"],
                          "Geometry policy differs")
            recorded = geometry_receipt["structures"][0]
            study.require(recorded["sha256"] == study.sha(structures[0])
                          and recorded["violations"] == diagnostics["violations"],
                          "Geometry record differs from coordinates")
            measured = evaluate(structures[0], binder_sequence, target_sequence)
            study.require(abs(float(metric["iptm"]) - measured["iptm"]) < 1e-6, "Metrics/confidence iPTM differs")
            row = {"arm": arm_name, "phase": phase, "trajectory": global_index, "cycle": cycle,
                   "sequence": binder_sequence, "structure": str(structures[0].relative_to(study.OUTPUT)),
                   "geometry_violations": diagnostics["violations"],
                   "geometry_violation_count": len(diagnostics["violations"]), **measured}
            this_run.append(row)
            rows.append(row)
            if cycle < campaign["optimization_cycles"] and (directory / "ligandmpnn/seed.txt").exists():
                expected_seed = campaign["mpnn_seed"] + 1000 * global_index + cycle
                study.require(int((directory / "ligandmpnn/seed.txt").read_text()) == expected_seed,
                              "MPNN seed pairing differs")
        summary["geometry_violations_total"] = sum(row["geometry_violation_count"] for row in this_run)
        summary["cycles_with_geometry_violations"] = [row["cycle"] for row in this_run if row["geometry_violation_count"]]
        summary["completed_cycles"] = sum(row["cycle"] > 0 for row in this_run)
        exit_path = run / "run_exit_code.txt"
        completed = ([row["cycle"] for row in this_run] == list(range(campaign["optimization_cycles"] + 1))
                     and exit_path.is_file() and exit_path.read_text().strip() == "0")
        if completed:
            summary["outcome"] = "completed"
            summary["initial_geometry_violations"] = this_run[0]["geometry_violation_count"]
            summary["final_geometry_violations"] = this_run[-1]["geometry_violation_count"]
            timing = list(csv.DictReader((run / "timing_run.csv").open()))
            summary["wall_seconds_including_initialization"] = float(timing[0]["duration_sec"])
            for metric_name in METRICS:
                optimized = [row[metric_name] for row in this_run if row["cycle"] > 0 and row[metric_name] is not None]
                summary["mean_" + metric_name] = statistics.mean(optimized) if optimized else None
                summary["final_" + metric_name] = this_run[-1][metric_name]
            summary["final_is_hit"] = this_run[-1]["iptm"] >= campaign["hit_threshold"]
        else:
            failures.append({"trajectory": global_index, "diagnostics": state.get("error"),
                             "pipeline_log_tail": state.get("pipeline_log_tail")})
        trajectories.append(summary)
    warnings, evidence = check_logs(root, arm["predictor"])
    raw_hashes = {str(item.relative_to(study.OUTPUT)): study.sha(item) for item in root.rglob("*")
                  if item.is_file() and ".studio_runtime" not in item.parts and "__pycache__" not in item.parts}
    value = {
        "schema": 1, "phase": phase, "arm": arm_name,
        "operational_passed": all(item["outcome"] == "completed" for item in trajectories),
        "trajectories": trajectories, "structures": rows, "failures": failures,
        "raw_sha256": raw_hashes, "svd_fallback_log_lines": warnings,
        "device_evidence": evidence, "job": study.compact(state),
        "manifest_sha256": study.sha(study.OUTPUT / "manifest.json"),
    }
    study.atomic(path, value)
    return value


def paired(left, right, metric):
    keys = sorted(left.keys() & right.keys())
    differences = [right[key]["mean_" + metric] - left[key]["mean_" + metric] for key in keys
                   if right[key].get("mean_" + metric) is not None and left[key].get("mean_" + metric) is not None]
    if not differences:
        return {"n_pairs": 0, "mean_difference": None, "bootstrap_95_ci": None}
    rng = random.Random(907026)
    draws = sorted(statistics.mean(rng.choices(differences, k=len(differences))) for _ in range(10000))
    return {"n_pairs": len(differences), "mean_difference": statistics.mean(differences),
            "bootstrap_95_ci": [draws[249], draws[9749]]}


def report():
    summaries, data, trajectories = {}, {}, []
    declared = study.CONFIG["campaign"]["trajectories"]
    for name in study.CONFIG["arms"]:
        records = [item for phase in ("pilot", "remaining") for item in audit(phase, name)["trajectories"]]
        study.require(sorted(item["trajectory"] for item in records) == list(range(1, declared + 1)),
                      f"Declared outcomes missing for {name}")
        trajectories += records
        complete = {item["trajectory"]: item for item in records if item["outcome"] == "completed"}
        data[name] = complete
        summaries[name] = {
            "declared_n": declared, "completed_n": len(complete), "failed_n": declared - len(complete),
            "final_hits": sum(item["final_is_hit"] for item in complete.values()),
            "geometry_violations_total": sum(item.get("geometry_violations_total", 0) for item in records),
            **{metric: (statistics.mean(item["mean_" + metric] for item in complete.values()
                                        if item.get("mean_" + metric) is not None) if any(
                                            item.get("mean_" + metric) is not None for item in complete.values()) else None)
               for metric in METRICS},
        }
    contrasts = {
        name: {metric: paired(data[arm["reference"]], data[name], metric) for metric in METRICS}
        for name, arm in study.CONFIG["arms"].items() if arm["reference"]
    }
    output = study.OUTPUT / "analysis"
    output.mkdir(exist_ok=True)
    result = {
        "complete": True, "summaries": summaries, "paired_contrasts": contrasts,
        "methods": study.CONFIG["methods"],
        "optimized_structures": sum(item["completed_cycles"] for item in trajectories),
        "manifest_sha256": study.sha(study.OUTPUT / "manifest.json"),
    }
    study.atomic(output / "report.json", result)
    fields = sorted(set().union(*(item.keys() for item in trajectories)))
    with (output / "trajectories.csv").open("w", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields)
        writer.writeheader()
        writer.writerows(trajectories)
    target = study.read(study.OUTPUT / "manifest.json")["target"]
    lines = [
        "# Binding helix-kill strength benchmark", "",
        f"Target `{target['name']}` ({target['length']} aa); exact supplied {target['msa_format']} MSA SHA-256 `{target['msa_sha256']}`.", "",
        "90-aa binders; 10 declared trajectories per arm. P-SEA and scores are averaged over cycles 01-05 within trajectories; cycle 00 is excluded.", "",
        "| Engine / strength | Completed | Final hits | Helix | Sheet | Coil | iPTM | ipSAE(min) | Binder pLDDT |",
        "|---|---:|---:|---:|---:|---:|---:|---:|---:|",
    ]
    for name, row in summaries.items():
        fraction = lambda key: f"{row[key]:.1%}" if row[key] is not None else "—"
        score = lambda key: f"{row[key]:.3f}" if row[key] is not None else "—"
        plddt = f"{row['plddt']:.1f}" if row["plddt"] is not None else "—"
        lines.append(f"| {name} | {row['completed_n']}/{declared} | {row['final_hits']} | "
                     f"{fraction('helix')} | {fraction('sheet')} | {fraction('coil')} | "
                     f"{score('iptm')} | {score('ipsae_min')} | {plddt} |")
    lines += ["", "Paired bootstrap: 10,000 trajectory resamples, seed 907026, no multiplicity adjustment. "
              "Fold summaries are conditional on completion; failures retain their declared seeds. iPTM is a predictor score, not experimental binding evidence. "
              "ipSAE(min) is reported only when the engine emits PAE suitable for that calculation. No cross-engine speed or score-calibration claim is made."]
    (output / "REPORT.md").write_text("\n".join(lines) + "\n")
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--phase", choices=["pilot", "remaining"])
    parser.add_argument("--arm", choices=list(study.CONFIG["arms"]))
    parser.add_argument("--report", action="store_true")
    args = parser.parse_args()
    study.require(args.report or (args.phase and args.arm), "Choose --report or both --phase and --arm")
    result = report() if args.report else audit(args.phase, args.arm)
    print(json.dumps({key: value for key, value in result.items()
                      if key in ("complete", "arm", "phase", "operational_passed", "optimized_structures")}))


if __name__ == "__main__":
    main()

