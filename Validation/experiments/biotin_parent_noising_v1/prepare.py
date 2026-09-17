"""Create a reviewed immutable branch-test plan; this script does not launch it."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import secrets
import shutil
import sys

REPO = Path(__file__).resolve().parents[3]
PIPELINE = REPO / "Sources/iProteinStudio/Resources/pipeline"
sys.path.insert(0, str(PIPELINE / "mcp"))
from iprotein_mcp.common import atomic_json, runtime_root, project_root
from iprotein_mcp.desktop import desktop_plan
from iprotein_mcp.nise import contract


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--project", default="test2")
    parser.add_argument("--source-run", required=True)
    parser.add_argument("--candidate", default="c06_t1_n0_s58")
    parser.add_argument("--records", type=Path, required=True)
    args = parser.parse_args()
    source = project_root(args.project) / "nise_runs" / args.source_run
    if source.resolve().parent != (project_root(args.project) / "nise_runs").resolve():
        raise ValueError("Source run must belong to the selected workspace")
    record_path = source / "candidates" / (args.candidate + ".json")
    if record_path.resolve().parent != (source / "candidates").resolve():
        raise ValueError("Invalid candidate identifier")
    record = json.loads(record_path.read_text())
    requested = json.loads((Path(__file__).parent / "request.json").read_text())
    settings = contract().preflight(runtime_root(), requested)
    output = project_root(args.project) / "nise_runs" / ("nise-branch-" + secrets.token_hex(8))
    inputs = output / "branch_test_inputs"
    inputs.mkdir(parents=True)
    copied = {"parent.json": record_path, "parent.pdb": source / record["pdb"],
              "reference.pdb": source / record["ref_pdb"], "ligand_atom_map.json": source / "ligand_atom_map.json"}
    for name, path in copied.items():
        if source.resolve() not in path.resolve().parents:
            raise ValueError("Source artifact escaped its run")
        shutil.copy2(path, inputs / name)
    descriptor = dict(schema=1, cycle=2, source_run=args.source_run, source_candidate=args.candidate,
        files={name: hashlib.sha256((inputs / name).read_bytes()).hexdigest() for name in copied})
    shutil.copytree(PIPELINE / "scripts", output / ".studio_runtime/pipeline/scripts",
                    ignore=shutil.ignore_patterns("__pycache__", "*.pyc"))
    atomic_json(output / "nise_config.json", dict(output=str(output), request=settings, branch_test=descriptor))
    atomic_json(output / "studio_run_label.json", dict(name="Biotin: previous-parent partial-noising test"))
    plan = desktop_plan(dict(project=args.project, workflow="nise_branch_test", output=str(output)))
    args.records.mkdir(parents=True, exist_ok=True)
    atomic_json(args.records / "plan.json", plan)
    print(json.dumps({key: plan[key] for key in ("id", "sha256", "normalized_request")}, indent=2))


if __name__ == "__main__":
    main()
