#!/usr/bin/env python3
"""Read existing NISE artifacts only; no model imports or inference. Requires numpy."""
import argparse
import collections
import csv
import hashlib
import json
import statistics
from datetime import datetime
from pathlib import Path

import numpy as np


def read(path):
    return json.loads(path.read_text())


def digest(paths, root):
    result = hashlib.sha256()
    for path in sorted(paths):
        result.update(str(path.relative_to(root)).encode() + b"\0")
        result.update(hashlib.sha256(path.read_bytes()).digest())
    return result.hexdigest()


def ranks(values):
    ordered = sorted(values)
    return [statistics.mean(i + 1 for i, v in enumerate(ordered) if v == x)
            for x in values]


def audit(run, jobs):
    job_id = read(run / "studio_job.json")["id"]
    state = read(jobs / job_id / "state.json")
    request = read(run / "nise_config.json")["request"]
    paths = sorted((run / "candidates").glob("*.json"))
    candidates = [read(p) for p in paths]
    refs = sorted((run / "phase0/cycle00").glob("L*_ref.pdb"))
    result = {
        "folder": run.name, "job_id": job_id, "name": state["display_name"],
        "status": state["status"], "exit_code": state["exit_code"],
        "started_at": state["started_at"], "finished_at": state["finished_at"],
        "recorded_wall_seconds": (datetime.fromisoformat(state["finished_at"]) -
                                  datetime.fromisoformat(state["started_at"])).total_seconds(),
        "request": request, "initial_reference_count": len(refs),
        "sequence_candidate_count": len(candidates),
        "candidate_set_sha256": digest(paths, run),
        "initial_reference_set_sha256": digest(refs, run),
        "phase0": {}, "optimization": {},
    }
    for label, subset in [
        ("phase0", [c for c in candidates if c["name"].startswith("L")]),
        ("optimization", [c for c in candidates if not c["name"].startswith("L")]),
    ]:
        for cycle in sorted({c["cycle"] for c in subset}):
            rows = [c for c in subset if c["cycle"] == cycle]
            passing = [c for c in rows if c["passed"]]
            result[label][str(cycle)] = {
                "folded": len(rows), "passed": len(passing),
                "atom_passed": sum(c["atom_checks"]["passed"] for c in rows),
                "passing_lineages": sorted({c["name"].split("_")[0] for c in passing})
                    if label == "phase0" else None,
                "atom_failures_overlapping": dict(collections.Counter(
                    f for c in rows for f in c["atom_checks"]["failures"])),
            }
    gate = [c for c in candidates if c["name"].startswith("L") and c["cycle"] == 3]
    result["gate"] = [{k: c[k] for k in ["name", "ca_rmsd", "ligand_rmsd", "passed"]}
                      | {"atom_passed": c["atom_checks"]["passed"]} for c in gate]
    if (run / "summary.json").exists():
        summary = read(run / "summary.json")
        result["winners"] = []
        for w in sorted(summary["trajectory_winners"], key=lambda w: -w["score"]):
            matching = [c for c in candidates if c["sequence"] == w["sequence"]
                        and c["trajectory"] == w["trajectory"]
                        and abs(c["score"] - w["score"]) < 1e-10]
            assert len(matching) == 1, (w, matching)
            c = matching[0]
            result["winners"].append(w | {k: c[k] for k in
                ["name", "cycle", "ca_rmsd", "ligand_rmsd", "passed", "pdb"]}
                | {"ligand_consistency_was_required":
                   c["cycle"] >= request["nise_ligand_sc_from_cycle"]})
    screening = run / "nesso_screening.csv"
    if screening.exists():
        with screening.open() as stream:
            rows = list(csv.DictReader(stream))
        result["nesso"] = {
            "scored": len(rows),
            "eligible": sum(r["nesso_eligible"] == "True" for r in rows),
            "selected": sum(r["selected_for_boltz"] == "True" for r in rows),
            "rejections": [r for r in rows if r["nesso_eligible"] != "True"],
            "selected_subset_correlations": {},
        }
        for c in candidates:
            if c.get("nesso"):
                n = c["nesso"]
                assert abs(n["screening_score"] - (n["affinity_probability_binary"]
                           + 1 - n["entropy_crop_pl"])) < 1e-10
        for cycle in sorted({c["cycle"] for c in candidates if c.get("nesso")}):
            paired = [c for c in candidates if c["cycle"] == cycle and c.get("nesso")]
            x = [c["nesso"]["screening_score"] for c in paired]
            y = [c["score"] for c in paired]
            result["nesso"]["selected_subset_correlations"][str(cycle)] = {
                "n": len(paired), "pearson": statistics.correlation(x, y),
                "spearman": statistics.correlation(ranks(x), ranks(y)),
            }
    result["rfd3_fixtures"] = []
    for p in sorted(run.glob("phase0/cycle00/rfd3_initial/rfd3/fixtures/*.npz")):
        with np.load(p, allow_pickle=False) as z:
            fixed = z["feats/is_motif_atom_with_fixed_coord"].astype(bool)
            rasa = z["feats/ref_atomwise_rasa"]
            result["rfd3_fixtures"].append({
                "path": str(p.relative_to(run)),
                "fixed_atoms": int(fixed.sum()),
                "buried_atoms": int((fixed & (rasa[:, 0] == 1)).sum()),
                "exposed_atoms": int((fixed & (rasa[:, 2] == 1)).sum()),
                "hotspot_atoms": int(z["feats/is_atom_level_hotspot"].sum()),
            })
    result["rfd3_partial_pdbs"] = [str(p.relative_to(run)) for p in sorted(
        run.glob("phase0/cycle00/rfd3_initial/rfd3/L*/queue*/backbones/*.pdb"))]
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--runs", type=Path, required=True)
    parser.add_argument("--jobs", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    results = [audit(p, args.jobs) for p in sorted(args.runs.glob("nise-*"))
               if (p / "studio_job.json").exists()]
    args.output.write_text(json.dumps(results, indent=2) + "\n")
    for r in results:
        print(r["name"], r["status"], "initial", r["initial_reference_count"],
              "sequence folds", r["sequence_candidate_count"],
              "wall seconds", round(r["recorded_wall_seconds"]))


if __name__ == "__main__":
    main()
