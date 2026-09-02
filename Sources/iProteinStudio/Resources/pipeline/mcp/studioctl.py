#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from server import MCPServer

from iprotein_mcp.broker import cancel_job, list_jobs, load_state, resume_job, run_worker, start_job, wait_job
from iprotein_mcp.catalog import detect_engines, list_projects, list_runs, query_results, run_status
from iprotein_mcp.common import StudioError, import_artifact
from iprotein_mcp.plans import admin_plan, iterative_plan, prediction_plan, rfd3_plan, target_prepare_plan


def emit(value):
    print(json.dumps(value, indent=2, sort_keys=True))


def main() -> int:
    parser = argparse.ArgumentParser(description="Stable JSON front controller for iProteinStudio workflows.")
    sub = parser.add_subparsers(dest="command", required=True)
    sub.add_parser("doctor")
    sub.add_parser("detect")
    projects = sub.add_parser("projects")
    runs = sub.add_parser("runs")
    runs.add_argument("--project")
    status = sub.add_parser("status")
    status.add_argument("run_id")
    jobs = sub.add_parser("jobs")
    job_status = sub.add_parser("job-status")
    job_status.add_argument("job_id")
    results = sub.add_parser("results")
    results.add_argument("run_id")
    results.add_argument("--dataset")
    results.add_argument("--metric")
    results.add_argument("--hit-only", action="store_true")
    results.add_argument("--limit", type=int, default=100)
    imported = sub.add_parser("import")
    imported.add_argument("path")
    for name in ("plan-prediction", "plan-target", "plan-iterative", "plan-rfd3-denovo", "plan-rfd3-partial", "plan-rfd3-motif"):
        command = sub.add_parser(name)
        command.add_argument("request_json")
    start = sub.add_parser("start")
    start.add_argument("plan_id")
    start.add_argument("plan_sha256")
    wait = sub.add_parser("wait")
    wait.add_argument("job_id")
    wait.add_argument("--timeout", type=int, default=30)
    cancel = sub.add_parser("cancel")
    cancel.add_argument("job_id")
    resume = sub.add_parser("resume")
    resume.add_argument("job_id")
    worker = sub.add_parser("_run-job")
    worker.add_argument("--job-id", required=True)
    args = parser.parse_args()
    try:
        if args.command == "doctor":
            bridge = Path(__file__).resolve().parent
            servers = {profile: len(MCPServer(profile).allowed) for profile in ("read", "run", "admin")}
            schemas = sorted(path.name for path in (bridge / "schemas").glob("*-v*.json"))
            if not schemas:
                raise StudioError("No versioned MCP schemas were packaged.")
            emit({
                "ok": True,
                "bridge_version": (bridge / "MCP_VERSION").read_text(encoding="utf-8").strip(),
                "python": sys.version.split()[0],
                "runtime_root": str(__import__("iprotein_mcp.common", fromlist=["runtime_root"]).runtime_root()),
                "profiles": servers,
                "schemas": schemas,
            })
        elif args.command == "detect":
            emit(detect_engines())
        elif args.command == "projects":
            emit({"projects": list_projects()})
        elif args.command == "runs":
            emit({"runs": list_runs(args.project)})
        elif args.command == "status":
            emit(run_status(args.run_id))
        elif args.command == "jobs":
            emit({"jobs": list_jobs()})
        elif args.command == "job-status":
            emit(load_state(args.job_id))
        elif args.command == "results":
            emit(query_results(args.run_id, args.dataset, args.metric, args.hit_only, args.limit))
        elif args.command == "import":
            emit(import_artifact(args.path))
        elif args.command.startswith("plan-"):
            with open(args.request_json, encoding="utf-8") as handle:
                request = json.load(handle)
            tool_names = {
                "plan-prediction": "prediction_plan", "plan-target": "target_prepare_plan",
                "plan-iterative": "iterative_design_plan", "plan-rfd3-denovo": "rfd3_denovo_plan",
                "plan-rfd3-partial": "rfd3_partial_diffusion_plan", "plan-rfd3-motif": "rfd3_motif_scaffolding_plan",
            }
            emit(MCPServer("run").tool_call(tool_names[args.command], request))
        elif args.command == "start":
            emit(start_job(args.plan_id, args.plan_sha256))
        elif args.command == "wait":
            emit(wait_job(args.job_id, args.timeout))
        elif args.command == "cancel":
            emit(cancel_job(args.job_id))
        elif args.command == "resume":
            emit(resume_job(args.job_id))
        elif args.command == "_run-job":
            return run_worker(args.job_id)
        return 0
    except StudioError as exc:
        print(json.dumps({"error": str(exc)}), file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
