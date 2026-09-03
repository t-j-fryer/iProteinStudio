#!/usr/bin/env python3
from __future__ import annotations

import argparse
import copy
import json
import os
import sys
from pathlib import Path
from typing import Any, Callable, Dict, List

from iprotein_mcp import __version__
from iprotein_mcp.broker import cancel_job, list_jobs, load_state, resume_job, start_job, wait_job
from iprotein_mcp.catalog import detect_engines, list_projects, list_runs, query_results, read_resource, results_overview, run_status, workflow_guide
from iprotein_mcp.common import StudioError, append_audit, import_artifact, validate_schema
from iprotein_mcp.inspect import inspect_target
from iprotein_mcp.plans import admin_plan, iterative_plan, load_plan, prediction_plan, rfd3_plan, target_prepare_plan


SCHEMAS = Path(__file__).resolve().parent / "schemas"


def schema(name: str) -> Dict[str, Any]:
    return json.loads((SCHEMAS / name).read_text(encoding="utf-8"))


EMPTY = {"type": "object", "additionalProperties": False, "properties": {}}
PROJECT_OPTIONAL = {"type": "object", "additionalProperties": False, "properties": {"project": {"type": "string"}, "limit": {"type": "integer", "minimum": 1, "maximum": 500}}}
RUN_ID = {"type": "object", "additionalProperties": False, "required": ["run_id"], "properties": {"run_id": {"type": "string"}}}
JOB_ID = {"type": "object", "additionalProperties": False, "required": ["job_id"], "properties": {"job_id": {"type": "string"}}}
WORKFLOW_GUIDE = {
    "type": "object", "additionalProperties": False, "required": ["workflow"],
    "properties": {"workflow": {"enum": ["prediction", "iterative_design", "rfd3_protein_binder", "rfd3_partial_diffusion", "rfd3_motif_scaffolding"]}},
}

SERVER_INSTRUCTIONS = (
    "Before planning scientific work call workflow_guide for that workflow. For protein de-novo binders use "
    "SolubleMPNN by default, never LASErMPNN/LigandMPNN, and omit contig so Studio derives it. When no epitope "
    "is known use binding_site_mode=surface_scan; never substitute the fixed protein's centre of mass. Complete a "
    "1-5-backbone end-to-end smoke run before a new campaign over 10 backbones. Use immutable plan then "
    "job_start; poll job_wait/job_status. On failure read message, error and pipeline_log_tail before changing "
    "settings; managed run logs never require arbitrary folder or shell access. After results exist, call "
    "results_overview before results_query: iterative results are run→cycle→artifacts and RFdiffusion3 results "
    "are backbone→MPNN derivative→complex/binder-alone validation. A hit belongs to the checked cycle or "
    "derivative, not automatically to its parent."
)


def rfd3_schema(mode: str) -> Dict[str, Any]:
    value = schema("rfd3-v1.json")
    value["properties"]["request"]["properties"]["design_mode"] = {"const": mode}
    return value


def tool(description: str, input_schema: Dict[str, Any]) -> Dict[str, Any]:
    return {"description": description, "inputSchema": input_schema}


RESULT_QUERY = {
    "type": "object",
    "additionalProperties": False,
    "required": ["run_id"],
    "properties": {
        "run_id": {"type": "string"},
        "dataset": {"type": "string"},
        "metric": {"type": "string"},
        "hit_only": {"type": "boolean", "default": False},
        "limit": {"type": "integer", "minimum": 1, "maximum": 500, "default": 100},
    },
}
RESULT_OVERVIEW = {
    "type": "object",
    "additionalProperties": False,
    "required": ["run_id"],
    "properties": {
        "run_id": {"type": "string"},
        "hit_only": {"type": "boolean", "default": False},
        "limit": {"type": "integer", "minimum": 1, "maximum": 200, "default": 100},
    },
}
ARTIFACT_IMPORT = {
    "type": "object", "additionalProperties": False, "required": ["path"],
    "properties": {"path": {"type": "string", "minLength": 1}},
}
TARGET_INSPECT = {
    "type": "object", "additionalProperties": False, "required": ["kind"],
    "properties": {
        "kind": {"enum": ["protein", "ligand"]},
        "structure": {"type": "string"}, "smiles": {"type": "string"},
        "resname": {"type": "string"}, "chain": {"type": "string"},
        "chains": {"type": "array", "items": {"type": "string"}},
    },
}
TARGET_PREPARE = schema("target-prepare-v1.json")
JOBS_LIST = {
    "type": "object", "additionalProperties": False,
    "properties": {"limit": {"type": "integer", "minimum": 1, "maximum": 500}},
}
JOB_WAIT = {
    "type": "object", "additionalProperties": False, "required": ["job_id"],
    "properties": {
        "job_id": {"type": "string"},
        "timeout_seconds": {"type": "integer", "minimum": 0, "maximum": 55, "default": 30},
    },
}
ENGINE_INSTALL = {
    "type": "object", "additionalProperties": False, "required": ["components"],
    "properties": {
        "components": {
            "type": "array", "minItems": 1, "uniqueItems": True,
            "items": {"enum": ["boltz", "boltz-affinity", "intellifold", "intellifold-full", "protenix-v2", "protenix-mini", "protenix-constraint", "openfold-3", "antifold", "lasermpnn", "rfd3"]},
        }
    },
}

TOOLS: Dict[str, Dict[str, Any]] = {
    "system_detect": tool("Detect managed engines. Report the returned state exactly; only state=ok is runnable. Read-only.", EMPTY),
    "workflow_guide": tool("Get Studio's workflow order, scientific defaults, routing rules, smoke-test policy, and common failure traps. Call this before creating a scientific plan.", WORKFLOW_GUIDE),
    "projects_list": tool("List managed iProteinStudio projects. Read-only.", EMPTY),
    "runs_list": tool("List recognized prediction, iterative-design and RFdiffusion3 runs.", PROJECT_OPTIONAL),
    "run_status": tool("Read durable run state, result files and bounded log tails.", RUN_ID),
    "results_overview": tool("Read the app-equivalent scientific hierarchy before interpreting results: iterative run→cycle→design/complex/binder artifacts (plus target-aligned trajectory frames), or RFdiffusion3 backbone→MPNN derivative→complex/binder validation. Hit verdicts remain attached to checked variants.", RESULT_OVERVIEW),
    "results_query": tool("After results_overview, read one normalized CSV dataset and optionally summarize a numeric score distribution.", RESULT_QUERY),
    "artifact_import": tool("Copy an explicitly allowed input file into immutable content-addressed Studio storage and return its digest.", ARTIFACT_IMPORT),
    "target_inspect": tool("Inspect exact chains, sequence, canonical target contig, and coarse exposed-residue candidates, or RFD3-compatible ligand atoms. Exposure candidates are not a validated epitope.", TARGET_INSPECT),
    "target_prepare_plan": tool("Validate and freeze a target-only structure prediction with an explicit alignment policy.", TARGET_PREPARE),
    "prediction_plan": tool("Validate and freeze a prediction batch without starting GPU work.", schema("prediction-v1.json")),
    "iterative_design_plan": tool("Validate and freeze an iterative-design request; Studio injects its measured scheduling policy.", schema("iterative-design-v1.json")),
    "rfd3_denovo_plan": tool("Validate and freeze an RFD3 campaign. With no protein epitope, omit hotspots and binding_site_mode resolves to whole-surface scanning with multiple outward solvent ORIs—never target COM. Use solublempnn by default, omit contig, and predict every candidate before ranking.", rfd3_schema("deNovo")),
    "rfd3_partial_diffusion_plan": tool("Validate and freeze protein-complex partial diffusion with partial_t in Angstroms and target coordinates fixed upstream.", rfd3_schema("partialDiffusion")),
    "rfd3_motif_scaffolding_plan": tool("Validate and freeze motif scaffolding with explicit non-empty residue atom selections.", rfd3_schema("motifScaffolding")),
    "job_start": tool("Start an immutable plan after checking its digest and exact installed script provenance. Expensive and mutating.", schema("job-start-v1.json")),
    "jobs_list": tool("List durable agent jobs and their bounded log tails.", JOBS_LIST),
    "job_status": tool("Read durable status plus actionable message, error, and bounded pipeline_log_tail. Diagnose these fields before changing settings or requesting filesystem access.", JOB_ID),
    "job_wait": tool("Wait at most 55 seconds for a job state change, then return its current durable status.", JOB_WAIT),
    "job_cancel": tool("Cancel the complete process group for a queued or running job. Mutating.", JOB_ID),
    "job_resume": tool("Resume a failed or cancelled job using its original immutable plan and durable outputs. Mutating.", JOB_ID),
    "engine_install_plan": tool("Freeze an explicit managed-engine installation plan. Does not download or install until job_start.", ENGINE_INSTALL),
    "engine_repair_plan": tool("Freeze a managed virtual-environment repair plan.", EMPTY),
    "storage_minimise_plan": tool("Freeze the existing checksum-constrained storage minimization operation.", EMPTY),
}

for name, definition in TOOLS.items():
    read_only = name in {"system_detect", "workflow_guide", "projects_list", "runs_list", "run_status", "results_overview", "results_query", "jobs_list", "job_status", "job_wait"}
    definition["annotations"] = {
        "readOnlyHint": read_only,
        "destructiveHint": name in {"job_start", "job_cancel", "storage_minimise_plan"},
        "idempotentHint": read_only or name in {"job_start", "job_cancel"},
        "openWorldHint": name in {"target_prepare_plan", "prediction_plan", "iterative_design_plan", "rfd3_denovo_plan", "rfd3_partial_diffusion_plan", "rfd3_motif_scaffolding_plan", "job_start", "job_resume", "engine_install_plan", "engine_repair_plan"},
    }

READ_TOOLS = ["system_detect", "workflow_guide", "projects_list", "runs_list", "run_status", "results_overview", "results_query"]
RUN_TOOLS = READ_TOOLS + ["artifact_import", "target_inspect", "target_prepare_plan", "prediction_plan", "iterative_design_plan", "rfd3_denovo_plan", "rfd3_partial_diffusion_plan", "rfd3_motif_scaffolding_plan", "job_start", "jobs_list", "job_status", "job_wait", "job_cancel", "job_resume"]
ADMIN_TOOLS = ["system_detect", "engine_install_plan", "engine_repair_plan", "storage_minimise_plan", "job_start", "jobs_list", "job_status", "job_wait", "job_cancel", "job_resume"]
ADMIN_KINDS = {"engine_install", "engine_repair", "storage_minimise"}


class MCPServer:
    def __init__(self, profile: str):
        self.profile = profile
        self.allowed = READ_TOOLS if profile == "read" else RUN_TOOLS if profile == "run" else ADMIN_TOOLS
        self.protocol_version = "2025-06-18"

    def tool_call(self, name: str, arguments: Dict[str, Any]) -> Dict[str, Any]:
        if name not in self.allowed:
            raise StudioError(f"Tool '{name}' is not available in the {self.profile} profile.")
        if not isinstance(arguments, dict):
            raise StudioError("Tool arguments must be a JSON object.")
        validate_schema(arguments, TOOLS[name]["inputSchema"])
        if name == "system_detect": result = detect_engines()
        elif name == "workflow_guide": result = workflow_guide(arguments["workflow"])
        elif name == "projects_list": result = {"projects": list_projects()}
        elif name == "runs_list": result = {"runs": list_runs(arguments.get("project"), arguments.get("limit", 100))}
        elif name == "run_status": result = run_status(arguments["run_id"])
        elif name == "results_overview": result = results_overview(arguments["run_id"], bool(arguments.get("hit_only", False)), int(arguments.get("limit", 100)))
        elif name == "results_query": result = query_results(arguments["run_id"], arguments.get("dataset"), arguments.get("metric"), bool(arguments.get("hit_only", False)), int(arguments.get("limit", 100)))
        elif name == "artifact_import": result = import_artifact(arguments["path"])
        elif name == "target_inspect": result = inspect_target(arguments)
        elif name == "target_prepare_plan": result = target_prepare_plan(arguments)
        elif name == "prediction_plan": result = prediction_plan(arguments)
        elif name == "iterative_design_plan": result = iterative_plan(arguments)
        elif name == "rfd3_denovo_plan": result = rfd3_plan(arguments, "deNovo")
        elif name == "rfd3_partial_diffusion_plan": result = rfd3_plan(arguments, "partialDiffusion")
        elif name == "rfd3_motif_scaffolding_plan": result = rfd3_plan(arguments, "motifScaffolding")
        elif name == "engine_install_plan": result = admin_plan(arguments, "engine_install")
        elif name == "engine_repair_plan": result = admin_plan(arguments, "engine_repair")
        elif name == "storage_minimise_plan": result = admin_plan(arguments, "storage_minimise")
        elif name == "jobs_list": result = {"jobs": list_jobs(int(arguments.get("limit", 100)))}
        elif name == "job_status": result = load_state(arguments["job_id"])
        elif name == "job_wait": result = wait_job(arguments["job_id"], int(arguments.get("timeout_seconds", 30)))
        elif name == "job_cancel":
            self.ensure_job_scope(arguments["job_id"])
            result = cancel_job(arguments["job_id"])
        elif name == "job_resume":
            self.ensure_job_scope(arguments["job_id"])
            result = resume_job(arguments["job_id"])
        elif name == "job_start":
            plan = load_plan(arguments["plan_id"], arguments["plan_sha256"])
            if self.profile == "admin" and plan["kind"] not in ADMIN_KINDS:
                raise StudioError("The admin profile may start only administration plans.")
            if self.profile == "run" and plan["kind"] in ADMIN_KINDS:
                raise StudioError("The scientific run profile cannot start administration plans.")
            result = start_job(arguments["plan_id"], arguments["plan_sha256"])
        else:
            raise StudioError(f"Unimplemented tool: {name}")
        append_audit(name, arguments, {"ok": True, "id": result.get("id") if isinstance(result, dict) else None})
        return result

    def ensure_job_scope(self, job_id: str) -> None:
        state = load_state(job_id)
        is_admin = state.get("kind") in ADMIN_KINDS
        if self.profile == "admin" and not is_admin:
            raise StudioError("The admin profile cannot mutate a scientific job.")
        if self.profile == "run" and is_admin:
            raise StudioError("The scientific run profile cannot mutate an administration job.")

    def dispatch(self, request: Dict[str, Any]) -> Dict[str, Any]:
        method = request.get("method")
        params = request.get("params") or {}
        if method == "initialize":
            requested = params.get("protocolVersion")
            if isinstance(requested, str) and requested:
                self.protocol_version = requested
            return {"protocolVersion": self.protocol_version, "capabilities": {"tools": {"listChanged": False}, "resources": {"subscribe": False, "listChanged": False}, "prompts": {"listChanged": False}}, "serverInfo": {"name": f"iproteinstudio-{self.profile}", "version": __version__}, "instructions": SERVER_INSTRUCTIONS}
        if method == "ping": return {}
        if method == "tools/list": return {"tools": [{"name": name, **TOOLS[name]} for name in self.allowed]}
        if method == "tools/call":
            name = params.get("name", "")
            arguments = params.get("arguments") or {}
            try:
                value = self.tool_call(name, arguments)
                text = json.dumps(value, indent=2, sort_keys=True)
                if len(text.encode("utf-8")) > 2_000_000:
                    raise StudioError("Tool result exceeds the 2 MB context safety limit; request fewer rows or use an artifact resource.")
                return {"content": [{"type": "text", "text": text}], "structuredContent": value, "isError": False}
            except (StudioError, KeyError, TypeError, ValueError) as exc:
                append_audit(name, arguments if isinstance(arguments, dict) else {}, {"ok": False, "error": str(exc)})
                return {"content": [{"type": "text", "text": str(exc)}], "isError": True}
        if method == "resources/list":
            return {"resources": [{"uri": "iprotein://capabilities", "name": "Capabilities", "mimeType": "application/json"}, {"uri": "iprotein://engines", "name": "Installed engines", "mimeType": "application/json"}, {"uri": "iprotein://projects", "name": "Projects", "mimeType": "application/json"}]}
        if method == "resources/templates/list":
            return {"resourceTemplates": [{"uriTemplate": "iprotein://runs/{run_id}/status", "name": "Run status", "mimeType": "application/json"}, {"uriTemplate": "iprotein://runs/{run_id}/manifest", "name": "Run manifest", "mimeType": "application/json"}, {"uriTemplate": "iprotein://runs/{run_id}/overview", "name": "Grouped run results", "mimeType": "application/json"}, {"uriTemplate": "iprotein://runs/{run_id}/metrics", "name": "Run metrics", "mimeType": "application/json"}, {"uriTemplate": "iprotein://runs/{run_id}/artifacts", "name": "Run artifacts", "mimeType": "application/json"}]}
        if method == "resources/read":
            uri = params.get("uri", "")
            value = read_resource(uri)
            return {"contents": [{"uri": uri, "mimeType": "application/json", "text": json.dumps(value, indent=2, sort_keys=True)}]}
        if method == "prompts/list": return {"prompts": []}
        raise StudioError(f"Unsupported MCP method: {method}")

    def serve(self) -> int:
        for line in sys.stdin:
            try:
                request = json.loads(line)
                if not isinstance(request, dict):
                    raise ValueError("request must be an object")
                if "id" not in request:
                    continue
                try:
                    result = self.dispatch(request)
                    response = {"jsonrpc": "2.0", "id": request["id"], "result": result}
                except StudioError as exc:
                    response = {"jsonrpc": "2.0", "id": request["id"], "error": {"code": -32601, "message": str(exc)}}
            except Exception as exc:
                response = {"jsonrpc": "2.0", "id": None, "error": {"code": -32700, "message": f"Invalid MCP JSON: {exc}"}}
            sys.stdout.write(json.dumps(response, separators=(",", ":")) + "\n")
            sys.stdout.flush()
        return 0


def main() -> int:
    parser = argparse.ArgumentParser(description="iProteinStudio MCP server")
    parser.add_argument("--profile", choices=["read", "run", "admin"], required=True)
    args = parser.parse_args()
    if args.profile == "admin" and os.environ.get("IPROTEINSTUDIO_ENABLE_ADMIN_MCP") != "1":
        parser.error("the admin profile requires IPROTEINSTUDIO_ENABLE_ADMIN_MCP=1")
    return MCPServer(args.profile).serve()


if __name__ == "__main__":
    raise SystemExit(main())
