from __future__ import annotations

import json
import os
import subprocess
from pathlib import Path
from typing import Any, Dict, List, Optional

from .common import StudioError, csv_rows, load_json, process_alive, project_root, projects_root, runtime_root, safe_managed_path, tail_text


KNOWN_RESULTS = (
    "predictions.csv",
    "analysis/top100.csv",
    "analysis/scored_designs.csv",
    "analysis/design_metrics.csv",
    "analysis/rmsd_metrics.csv",
    "rfd3/backbone_metrics.csv",
    "mpnn/sequences.csv",
    "predictions/holo/prediction_metrics.csv",
    "predictions/apo/prediction_metrics.csv",
    "predictions/complex/prediction_metrics.csv",
    "predictions/binder/prediction_metrics.csv",
    "predictions/monomer/prediction_metrics.csv",
)


def _result_context(dataset: str, row: Dict[str, str]) -> Optional[str]:
    explicit = str(row.get("prediction_context", "")).strip()
    if explicit:
        return explicit
    if dataset == "rfd3/backbone_metrics.csv":
        return "generated_backbone"
    if dataset == "analysis/rmsd_metrics.csv":
        return "complex_and_binder_alone_comparison"
    if "/holo/" in dataset or "/complex/" in dataset:
        return "complex"
    if any(token in dataset for token in ("/apo/", "/binder/", "/monomer/")):
        return "binder_alone"
    evidence = " ".join(str(row.get(key, "")) for key in ("pdb", "yaml", "name")).lower()
    if any(token in evidence for token in ("/holo/", "/complex/")):
        return "complex"
    if any(token in evidence for token in ("/apo/", "/binder/", "/monomer/")):
        return "binder_alone"
    return None


def _result_predictor(dataset: str, row: Dict[str, str]) -> Optional[str]:
    explicit = str(row.get("predictor", "")).strip()
    if explicit:
        return explicit
    if dataset == "rfd3/backbone_metrics.csv":
        return "rfd3-mlx"
    evidence = " ".join(str(value) for value in row.values()).lower()
    for token, predictor in (
        ("intellifold", "intellifold"),
        ("protenix", "protenix"),
        ("openfold", "openfold-3"),
        ("boltz", "boltz"),
    ):
        if token in evidence:
            return predictor
    return None


def _normalize_result_rows(dataset: str, rows: List[Dict[str, str]]) -> List[Dict[str, str]]:
    """Add durable semantic labels without rewriting completed user runs.

    New runners write these fields directly. The inference below is deliberately
    limited to Studio-owned dataset paths and well-known predictor output names,
    allowing older campaigns to remain intelligible through MCP.
    """
    normalized: List[Dict[str, str]] = []
    for source in rows:
        row = dict(source)
        context = _result_context(dataset, row)
        predictor = _result_predictor(dataset, row)
        if context and not str(row.get("prediction_context", "")).strip():
            row["prediction_context"] = context
        if predictor and not str(row.get("predictor", "")).strip():
            row["predictor"] = predictor
        normalized.append(row)
    return normalized


def detect_engines() -> Dict[str, Any]:
    root = runtime_root()
    setup = root / "setup_pipeline.sh"
    if not setup.is_file():
        return {"runtime_root": str(root), "staged": False, "engines": {}, "message": "Run iProteinStudio once to stage its managed pipeline."}
    try:
        completed = subprocess.run(
            ["/bin/bash", str(setup), "--detect"],
            cwd=str(root),
            capture_output=True,
            text=True,
            timeout=120,
            env={**os.environ, "NANOHUNTER_ROOT": str(root)},
        )
    except (OSError, subprocess.TimeoutExpired) as exc:
        raise StudioError(f"Engine detection failed: {exc}") from exc
    engines: Dict[str, Dict[str, str]] = {}
    for line in (completed.stdout + "\n" + completed.stderr).splitlines():
        parts = line.split("|", 3)
        if len(parts) >= 3 and parts[0] == "NHSTATE":
            engines[parts[1]] = {"state": parts[2], "detail": parts[3] if len(parts) > 3 else ""}
    return {
        "runtime_root": str(root),
        "staged": True,
        "exit_code": completed.returncode,
        "engines": engines,
    }


def classify_run(path: Path) -> Optional[str]:
    if (path / "prediction_config.json").exists() or (path / "predictions.csv").exists():
        return "prediction"
    if (path / "config" / "campaign.json").exists() or (path / "campaign_progress.json").exists():
        return "rfdiffusion3"
    if (path / "studio_run.json").exists():
        return "iterative"
    return None


def run_record(path: Path, project: str) -> Dict[str, Any]:
    workflow = classify_run(path) or "unknown"
    manifest = {}
    for relative in ("studio_run.json", "run_summary.json", "campaign_progress.json"):
        candidate = path / relative
        if candidate.is_file():
            try:
                manifest[relative] = load_json(candidate)
            except StudioError:
                manifest[relative] = {"unreadable": True}
    pid = None
    pid_file = path / "campaign.pid"
    if pid_file.is_file():
        try:
            pid = int(pid_file.read_text().strip())
        except (OSError, ValueError):
            pass
    result_files = [relative for relative in KNOWN_RESULTS if (path / relative).is_file()]
    return {
        "id": f"{project}/{path.relative_to(project_root(project)).as_posix()}",
        "project": project,
        "name": path.name,
        "path": str(path),
        "workflow": workflow,
        "process_alive": process_alive(pid),
        "pid": pid,
        "result_files": result_files,
        "summary": manifest,
        "modified_at": path.stat().st_mtime,
    }


def list_projects() -> List[Dict[str, Any]]:
    records = []
    for path in sorted(projects_root().iterdir()) if projects_root().exists() else []:
        if path.is_dir() and not path.name.startswith("."):
            records.append({"id": path.name, "path": str(path), "modified_at": path.stat().st_mtime})
    return records


def list_runs(project: Optional[str] = None, limit: int = 100) -> List[Dict[str, Any]]:
    roots = [project_root(project)] if project else [Path(item["path"]) for item in list_projects()]
    records: List[Dict[str, Any]] = []
    for root in roots:
        for current, directories, _files in os.walk(root):
            directories[:] = [name for name in directories if not name.startswith(".") and name not in {"inputs", "assets", "logs"}]
            path = Path(current)
            if path == root:
                continue
            workflow = classify_run(path)
            if workflow:
                records.append(run_record(path, root.name))
                directories[:] = []
    records.sort(key=lambda item: item["modified_at"], reverse=True)
    return records[: max(1, min(limit, 500))]


def resolve_run(run_id: str) -> Path:
    parts = Path(run_id).parts
    if len(parts) < 2:
        raise StudioError("run_id must be '<project>/<relative-run-path>'.")
    root = project_root(parts[0])
    path = (root / Path(*parts[1:])).resolve()
    if root not in path.parents or not path.is_dir():
        raise StudioError(f"Unknown or unsafe run_id: {run_id}")
    if not classify_run(path):
        raise StudioError(f"Directory is not a recognized iProteinStudio run: {run_id}")
    return path


def run_status(run_id: str) -> Dict[str, Any]:
    path = resolve_run(run_id)
    record = run_record(path, Path(run_id).parts[0])
    logs = []
    seen = set()
    for relative in ("studio.log", "campaign.stdout.log", "logs/prediction.log"):
        candidate = path / relative
        if candidate.is_file():
            logs.append({"path": relative, "tail": tail_text(candidate, 30)})
            seen.add(relative)
    # RFdiffusion campaigns write one log per resumable stage. Surface the most
    # recently modified stage logs so an agent never needs arbitrary folder
    # access merely to learn why a managed run failed.
    stage_logs = sorted((path / "logs").glob("*.log"),
                        key=lambda item: item.stat().st_mtime, reverse=True)
    for candidate in stage_logs[:8]:
        relative = candidate.relative_to(path).as_posix()
        if relative not in seen:
            logs.append({"path": relative, "tail": tail_text(candidate, 30)})
    record["logs"] = logs
    return record


def query_results(run_id: str, dataset: Optional[str], metric: Optional[str], hit_only: bool, limit: int) -> Dict[str, Any]:
    path = resolve_run(run_id)
    available = [relative for relative in KNOWN_RESULTS if (path / relative).is_file()]
    if dataset:
        if dataset not in KNOWN_RESULTS:
            raise StudioError(f"Unknown result dataset '{dataset}'.")
        selected = dataset
    elif available:
        selected = available[0]
    else:
        return {"run_id": run_id, "available": [], "rows": [], "columns": []}
    rows = _normalize_result_rows(selected, csv_rows(path / selected, limit=1000))
    if hit_only:
        rows = [row for row in rows if str(row.get("hit", row.get("passes_filters", ""))).lower() in {"1", "true", "yes", "pass"}]
    if metric:
        rows = [row for row in rows if row.get(metric, "") not in {"", None}]
        def numeric(row: Dict[str, str]) -> float:
            try:
                return float(row.get(metric, "nan"))
            except (TypeError, ValueError):
                return float("nan")
        values = [numeric(row) for row in rows]
        values = [value for value in values if value == value]
        distribution = {
            "metric": metric,
            "count": len(values),
            "minimum": min(values) if values else None,
            "maximum": max(values) if values else None,
            "mean": sum(values) / len(values) if values else None,
        }
    else:
        distribution = None
    rows = rows[: max(1, min(limit, 500))]
    columns = list(rows[0]) if rows else []
    for row in rows[1:]:
        for column in row:
            if column not in columns:
                columns.append(column)
    return {
        "run_id": run_id,
        "dataset": selected,
        "available": available,
        "columns": columns,
        "distribution": distribution,
        "rows": rows,
    }


def workflow_guide(workflow: str) -> Dict[str, Any]:
    """Return client-neutral operating guidance for the typed Studio tools.

    This deliberately lives in the MCP server rather than only in a Codex or
    Claude skill: desktop clients receive the same scientific routing rules.
    """
    common = {
        "execution_contract": [
            "Call system_detect; never infer installation state from tool availability.",
            "Create a workflow plan and review its normalized_request and command_preview.",
            "Start only with the returned plan_id and plan_sha256.",
            "Use job_wait/job_status; on failure read message, error, and pipeline_log_tail before changing any setting.",
            "Use runs_list, run_status, and results_query for outputs; never request arbitrary filesystem access for a managed run.",
        ],
        "long_campaign_rule": (
            "For a new target/settings combination, complete a 1-5 backbone end-to-end smoke run "
            "before starting more than 10 backbones. Keep the scientific settings and predictors identical."
        ),
    }
    guides = {
        "rfd3_protein_binder": {
            "tool": "rfd3_denovo_plan",
            "defaults": {
                "sequence_model": "solublempnn",
                "extra_predictors": ["boltz"],
                "binding_site_mode": "surface_scan",
                "run_apo": True,
                "hit_filters": {
                    "minimum_iptm": 0.50,
                    "minimum_ipsae_min": 0.50,
                    "maximum_complex_rmsd": 2.5,
                    "minimum_binder_plddt": 0.80,
                    "maximum_binder_rmsd": 2.0,
                },
            },
            "rules": [
                "Use SolubleMPNN by default for soluble protein-protein binders. ProteinMPNN is an explicit alternative.",
                "Never use LASErMPNN or LigandMPNN for a protein target; those are small-molecule-interface models.",
                "Omit contig. Studio derives the canonical binder-first contig from lengths and the selected target chains.",
                "Use target_inspect before planning. Its exposure labels are coarse candidates, not proof of a coherent epitope.",
                "Choose one placement mode: surface_scan (default, no known site), surface_patch (broad region, no hotspot conditioning), targeted_epitope (reviewed hotspot residues), or manual (expert XYZ).",
                "Never use the fixed protein centre of mass as a no-hotspot fallback. surface_scan computes several solvent-accessible outward ORIs and divides the requested designs across them.",
                "Generate sequences for every requested backbone and independently predict every candidate before ranking. Do not prefilter by RFD3 internal scores.",
                "Do not rank on iPTM alone: report the saved iPTM, ipSAE(min), target-aligned complex RMSD, binder-only pLDDT, and binder-only RMSD gates.",
            ],
        },
        "rfd3_partial_diffusion": {
            "tool": "rfd3_partial_diffusion_plan",
            "defaults": {"partial_t": 2.0, "sequence_model": "solublempnn", "run_apo": True},
            "rules": [
                "partial_t is coordinate-noise scale in Angstroms, not a timestep count.",
                "The target chains are fixed; the source binder chain is diffused and must be distinct.",
                "Preserve the binder sequence for structural refinement unless redesign is explicitly requested.",
                "Do not inject de-novo origin/hotspot overrides; retain the diffused-region COM behavior.",
            ],
        },
        "rfd3_motif_scaffolding": {
            "tool": "rfd3_motif_scaffolding_plan",
            "defaults": {"sequence_model": "solublempnn", "run_apo": True, "maximum_motif_rmsd": 1.0},
            "rules": [
                "Provide an explicit non-empty atom selection for every motif residue; never rely on all-atom defaults.",
                "Fix the minimum functional and orientation-defining atoms needed for the chemistry.",
                "Use the recorded source-to-design motif mapping; never assume an unindexed motif kept its residue number.",
                "Reject virtual side-chain atoms and malformed local geometry before downstream ranking.",
            ],
        },
        "prediction": {
            "tool": "prediction_plan",
            "rules": [
                "Use an explicit MSA policy for every protein chain.",
                "A de-novo binder uses msa=empty; a natural target normally uses msa=auto unless the user supplies a validated alignment.",
                "Use all requested predictors and keep predictor-specific scores distinct in results.",
            ],
        },
        "iterative_design": {
            "tool": "iterative_design_plan",
            "rules": [
                "Use the MCP plan rather than assembling the runner command; Studio injects the measured resident/cycle-wave scheduler.",
                "Require the target MSA for design campaigns and use an orthogonal predictor for final checking when requested.",
            ],
        },
    }
    if workflow not in guides:
        raise StudioError(f"Unknown workflow guide: {workflow}")
    return {"workflow": workflow, **common, **guides[workflow]}


def read_resource(uri: str) -> Dict[str, Any]:
    if uri == "iprotein://capabilities":
        return {"server_profiles": ["read", "run", "admin"], "workflows": ["prediction", "iterative_design", "rfd3_de_novo", "rfd3_partial_diffusion", "rfd3_motif_scaffolding"], "transport": "stdio"}
    if uri == "iprotein://engines":
        return detect_engines()
    if uri == "iprotein://projects":
        return {"projects": list_projects()}
    prefix = "iprotein://runs/"
    if uri.startswith(prefix):
        remainder = uri[len(prefix) :]
        for suffix in ("/status", "/manifest", "/metrics", "/artifacts"):
            if remainder.endswith(suffix):
                run_id = remainder[: -len(suffix)]
                if suffix == "/status":
                    return run_status(run_id)
                if suffix == "/metrics":
                    return query_results(run_id, None, None, False, 200)
                path = resolve_run(run_id)
                if suffix == "/manifest":
                    documents = {}
                    for relative in ("studio_run.json", "prediction_config.json", "config/studio_request.json", "config/campaign.json", "campaign_progress.json", "run_summary.json"):
                        candidate = path / relative
                        if candidate.is_file():
                            documents[relative] = load_json(candidate)
                    return {"run_id": run_id, "documents": documents}
                artifacts = []
                for candidate in path.rglob("*"):
                    if candidate.is_file() and candidate.stat().st_size <= 2_000_000_000:
                        artifacts.append({"path": candidate.relative_to(path).as_posix(), "bytes": candidate.stat().st_size})
                        if len(artifacts) >= 500:
                            break
                return {"run_id": run_id, "artifacts": artifacts, "truncated": len(artifacts) >= 500}
    raise StudioError(f"Unknown iProteinStudio resource URI: {uri}")
