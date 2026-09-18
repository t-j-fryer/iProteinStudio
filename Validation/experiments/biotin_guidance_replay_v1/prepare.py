"""Freeze audited completed initial backbones and create a broker plan; no launch."""
import argparse
import json
import os
from pathlib import Path
import secrets
import shutil
import sys

REPO = Path(__file__).resolve().parents[3]
PIPELINE = REPO / "Sources/iProteinStudio/Resources/pipeline"
sys.path[:0] = [str(PIPELINE / "mcp"), str(PIPELINE / "scripts"), str(PIPELINE / "scripts/nise")]
from iprotein_mcp.common import atomic_json, project_root
from iprotein_mcp.desktop import desktop_plan
from server import MCPServer
from runtime import Journal
from boltz_replay_validation import checksum


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--project", default="test2")
    p.add_argument("--source-job", required=True)
    p.add_argument("--records", type=Path, required=True)
    p.add_argument("--limit", type=int)
    args = p.parse_args()
    status = MCPServer("run").tool_call("job_status", {"job_id": args.source_job})
    if status["status"] != "cancelled":
        raise ValueError("Pause the source job and wait for its workers to stop first")
    source = Path(status["output_root"])
    if project_root(args.project).resolve() not in source.resolve().parents:
        raise ValueError("Source job belongs to a different workspace")
    receipts = sorted((source / "phase0/cycle00").glob("*/completed.json"))
    if args.limit is not None:
        if not 1 <= args.limit <= 5:
            raise ValueError("Pilot limit must be 1–5")
        receipts = receipts[:args.limit]
    journal = Journal(source)
    output = project_root(args.project) / "validation_runs" / ("biotin-replay-" + secrets.token_hex(8))
    inputs = output / "inputs"
    inputs.mkdir(parents=True)
    ids = []
    for path in receipts:
        row = json.loads(path.read_text())
        journal.load(path, row["input"])
        name = path.parent.name
        ids.append(name)
        destination = inputs / name
        destination.mkdir()
        shutil.copy2(path, destination / "completed.json")
        shutil.copy2(path.parent / "yaml" / f"{name}.yaml", destination / f"{name}.yaml")
        prediction = Path(row["result"]["prediction"]["pdb"])
        if source.resolve() not in prediction.resolve().parents:
            raise ValueError("Prediction escaped its source run")
        shutil.copy2(prediction, destination / prediction.name)
        shutil.copy2(prediction.parent / f"confidence_{name}_model_0.json", destination / f"confidence_{name}_model_0.json")
        # Preserve the original RDKit conformer as well as sequence/SMILES.
        # Boltz's unseeded ETKDG parser otherwise advances a separate RNG in a
        # multi-input request, beyond Python/NumPy/torch seed control.
        shutil.copytree(prediction.parent.parent.parent / "processed", destination / "processed")
    for name in ("nise_config.json", "ligand_atom_map.json"):
        shutil.copy2(source / name, inputs / name)
    # Retain the original worker configuration to audit explicit/default settings.
    old = json.loads(receipts[0].read_text())
    session = Path(old["result"]["timing"]["session"])
    shutil.copy2(session / "config.json", inputs / "original_worker_config.json")
    atomic_json(inputs / "source_status.json", status)
    config = dict(schema=1, output=str(output), ids=ids, seed=0, potentials=False, phase="structure",
                  source_job=args.source_job,
                  files={str(p.relative_to(output)): checksum(p) for p in inputs.rglob("*") if p.is_file()})
    shutil.copytree(PIPELINE / "scripts", output / ".studio_runtime/pipeline/scripts",
                    ignore=shutil.ignore_patterns("__pycache__", "*.pyc"))
    atomic_json(output / "replay_config.json", config)
    atomic_json(output / "studio_run_label.json", dict(name=f"Biotin pocket-only replay — {len(ids)} initial backbones"))
    plan = desktop_plan(dict(project=args.project, workflow="boltz_replay_validation", output=str(output)))
    args.records.mkdir(parents=True, exist_ok=True)
    atomic_json(args.records / "plan.json", plan)
    print(json.dumps({key: plan[key] for key in ("id", "sha256", "normalized_request")}, indent=2))


if __name__ == "__main__":
    main()
