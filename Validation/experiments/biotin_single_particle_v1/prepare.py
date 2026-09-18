"""Freeze a physical-guidance-on/FK-off batch replay from the audited prior study."""
import argparse
import json
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
from boltz_replay_validation import checksum, validate


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--source-job", required=True)
    p.add_argument("--project", default="test2")
    p.add_argument("--records", type=Path, required=True)
    p.add_argument("--limit", type=int)
    args = p.parse_args()
    status = MCPServer("run").tool_call("job_status", {"job_id": args.source_job})
    if status["status"] != "completed":
        raise ValueError("Source replay must have completed")
    source = Path(status["output_root"])
    if project_root(args.project).resolve() not in source.resolve().parents:
        raise ValueError("Source replay belongs to a different workspace")
    old = json.loads((source / "replay_config.json").read_text())
    validate(source, old)
    if old["schema"] != 1:
        raise ValueError("Expected the original paired singleton/batch study")
    ids = old["ids"]
    if args.limit is not None:
        if not 1 <= args.limit <= 5:
            raise ValueError("Pilot limit must be1–5")
        ids = ids[:args.limit]
    journal = Journal(source)
    output = project_root(args.project) / "validation_runs" / ("biotin-single-particle-" + secrets.token_hex(8))
    inputs = output / "inputs"
    inputs.mkdir(parents=True)
    for name in ids:
        receipt = source / "singleton" / name / "completed.json"
        row = json.loads(receipt.read_text())
        journal.load(receipt, row["input"])
        shutil.copytree(source / "inputs" / name, inputs / name)
        (inputs / "rng").mkdir(exist_ok=True)
        for path in (source / "rng").glob(name + "_*"):
            shutil.copy2(path, inputs / "rng" / path.name)
    for path in (source / "inputs").glob("*.json"):
        shutil.copy2(path, inputs / path.name)
    atomic_json(inputs / "source_replay_status.json", status)
    config = dict(schema=2, output=str(output), ids=ids, seed=0, potentials=True,
                  fk_steering=False, phase="structure", trace_steps=[1] + list(range(5, 201, 5)),
                  source_replay_job=args.source_job,
                  files={str(p.relative_to(output)): checksum(p) for p in inputs.rglob("*") if p.is_file()})
    shutil.copytree(PIPELINE / "scripts", output / ".studio_runtime/pipeline/scripts",
                    ignore=shutil.ignore_patterns("__pycache__", "*.pyc"))
    atomic_json(output / "replay_config.json", config)
    atomic_json(output / "studio_run_label.json", dict(name=f"Biotin physical guidance, FK off — {len(ids)} inputs + exposure trace"))
    plan = desktop_plan(dict(project=args.project, workflow="boltz_replay_validation", output=str(output)))
    args.records.mkdir(parents=True, exist_ok=True)
    atomic_json(args.records / "plan.json", plan)
    print(json.dumps({key: plan[key] for key in ("id", "sha256", "normalized_request")}, indent=2))


if __name__ == "__main__":
    main()
