#!/usr/bin/env python3
"""Bounded ligand-NISE acceptance: holo → real MPNN gap → holo → apo → replay.

This is a lifecycle/correctness smoke, not a throughput benchmark or a test of
search efficacy. It submits a fingerprinted plan to Studio's shared broker.
"""
import argparse
import csv
import json
import os
from pathlib import Path
import platform
import shutil
import subprocess
import sys

STUDIO = Path(__file__).resolve().parents[3]
PIPELINE = STUDIO / "Sources/iProteinStudio/Resources/pipeline"


def plan(output, source):
    sys.path.insert(0, str(PIPELINE / "mcp"))
    from iprotein_mcp.common import atomic_json, runtime_root
    from iprotein_mcp.plans import _persist, _script_provenance
    from iprotein_mcp.nise import contract
    from iprotein_mcp.catalog import workflow_guide
    root = runtime_root()
    print(json.dumps(workflow_guide("nise")))
    rows = list(csv.DictReader((source / "trajectory.csv").open()))
    row = next(r for r in rows if r["name"] == "c09_t4_n0_s23")
    output.mkdir(parents=True, exist_ok=False)
    scripts = output / "snapshot/scripts"
    shutil.copytree(PIPELINE / "scripts", scripts, ignore=shutil.ignore_patterns("__pycache__", "*.pyc"))
    runner = output / "snapshot/acceptance.py"
    shutil.copy2(__file__, runner)
    settings = contract().preflight(root, {"smiles": "O=C(NCCO)c1ccc(-c2c3ccc(=O)cc-3oc3cc([O-])ccc23)c(C(=O)[O-])c1", "scheduler": "resident", "preorganisation": True, "top_x": 1})
    manifest = {"schema": 1, "purpose": __doc__, "settings": settings,
                "sequence": row["sequence"], "source_candidate": row["name"],
                "source_csv": str(source / "trajectory.csv"), "runtime": str(root),
                "hardware": platform.platform(), "commit": subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=STUDIO, text=True).strip(),
                "working_tree": "Uncommitted implementation; exact executed files fingerprinted in the plan", "seed": 17,
                "expected": {"holo": 2, "mpnn_sequences": 1, "apo": 1, "structure_and_affinity_loads_in_holo_session": 2}}
    atomic_json(output / "manifest.json", manifest)
    command = ["/usr/bin/caffeinate", "-dimsu", str(root / "venvs/NanoHunter_boltz/bin/python"), str(runner), "run", "--output", str(output)]
    files = [runner, output / "manifest.json", source / "trajectory.csv"] + sorted(scripts.rglob("*.py")) + contract().required_files(root)
    files += sorted((root / "src/LASErMPNN").rglob("*.py"))
    files += sorted((root / "venvs/NanoHunter_boltz/lib").glob("python*/site-packages/boltz/**/*.py"))
    frozen = _persist("desktop_nise_validation", "nise-validation", {"output": str(output), "workflow": "nise-acceptance",
        "steps": [{"command": command, "cwd": str(output), "stage": "nise-acceptance"}], "environment_overrides": {}},
        command, "apple_gpu_exclusive", _script_provenance(files))
    atomic_json(output / "plan.json", frozen)
    print(json.dumps({"id": frozen["id"], "sha256": frozen["sha256"]}))


def run(output):
    from types import SimpleNamespace
    sys.path.insert(0, str(output / "snapshot/scripts/nise"))
    from runtime import Backend, atomic
    import nise_lib as science
    import nise_run
    cfg = json.loads((output / "manifest.json").read_text())
    settings = cfg["settings"]
    root = Path(cfg["runtime"])
    args = SimpleNamespace(seed=cfg["seed"], use_potentials=True, fs_distance=10.0, ala_budget=2, gly_budget=0)
    backend = Backend(root, output, settings, output / "snapshot/scripts")
    def execute():
        first = backend.fold({"parent": cfg["sequence"]}, settings["smiles"], output / "holo-parent", args)["parent"]
        sequence = backend.design(first.pdb, output / "mpnn", 1, settings["smiles"], args, 0.5, 0.7, args.seed, "all", True)[0]
        name = "c01_t0_n0_s0"
        child = backend.fold({name: sequence}, settings["smiles"], output / "holo-child", args)[name]
        sc = science.self_consistency(child.pdb, first.pdb)
        node = nise_run.Node(name, sequence, child.pdb, first.pdb, sc.ca_rmsd, sc.ligand_rmsd,
                             child.ligand_plddt, child.pbind, science.rank_score(child), 1)
        # Apo tests the emitted child regardless of whether this one proposal
        # would pass selection. This smoke makes no search-success claim.
        backend.record_candidate(node, True, child)
        backend.preorganisation(args)
        backend.close()
    try:
        execute()
        sessions = len(list((output / "sessions").iterdir()))
        execute()
        if len(list((output / "sessions").iterdir())) != sessions:
            raise RuntimeError("Replay unexpectedly started a new model worker")
        receipts = [json.loads(p.read_text()) for p in output.glob("holo-*/**/completed.json")]
        holo_sessions = {r["result"]["timing"]["session"] for r in receipts}
        if len(receipts) != 2 or len(holo_sessions) != 1:
            raise RuntimeError("Two holo requests did not share one resident session")
        if any(r["result"]["timing"]["model_load_count"] != 2 for r in receipts):
            raise RuntimeError("Structure/affinity checkpoint load count is wrong")
        atomic(output / "audit.json", {"status": "passed", "holo_predictions": 2, "apo_predictions": 1,
               "holo_sessions": 1, "total_sessions": sessions, "replay_new_sessions": 0,
               "scope": "Lifecycle and artifact acceptance only; no throughput default promoted"})
    finally:
        backend.close()


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("action", choices=["plan", "run"])
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--source", type=Path)
    args = parser.parse_args()
    if args.action == "plan":
        if args.source is None:
            parser.error("plan requires --source (the original fluorescein run)")
        plan(args.output.resolve(), args.source.resolve())
    else:
        run(args.output.resolve())
