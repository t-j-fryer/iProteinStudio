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
    "analysis/rmsd_metrics.csv",
    "predictions/holo/prediction_metrics.csv",
    "predictions/apo/prediction_metrics.csv",
    "predictions/complex/prediction_metrics.csv",
    "predictions/binder/prediction_metrics.csv",
)


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
    for relative in ("studio.log", "campaign.stdout.log", "logs/prediction.log"):
        candidate = path / relative
        if candidate.is_file():
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
    rows = csv_rows(path / selected, limit=1000)
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
    return {
        "run_id": run_id,
        "dataset": selected,
        "available": available,
        "columns": list(rows[0]) if rows else [],
        "distribution": distribution,
        "rows": rows,
    }


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
