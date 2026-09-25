from __future__ import annotations

import json
import os
import subprocess
from pathlib import Path
from typing import Any, Dict, List, Optional

from .common import StudioError, csv_rows, load_json, process_alive, project_root, projects_root, runtime_root, safe_managed_path, tail_text


KNOWN_RESULTS = (
    "nesso_verification/nesso_screening.csv",
    "nesso_verification/psichic_screening.csv",
    "psichic_screening.csv",
    "trajectory.csv",
    "predictions.csv",
    "comparison_scores_long.csv",
    "summary_all_runs.csv",
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

RESULT_METRICS = (
    "iptm",
    "ipsae_min",
    "complex_plddt",
    "binder_plddt",
    "complex_rmsd",
    "binder_backbone_rmsd",
    "binder_rmsd",
    "score",
    "ranking_score",
    "ca_valid_pct",
    "motif_insertion_rmsd",
    "motif_prediction_rmsd",
    "motif_max_drift",
)


def _result_context(dataset: str, row: Dict[str, str]) -> Optional[str]:
    explicit = str(row.get("prediction_context", "")).strip()
    if explicit:
        return explicit
    if dataset == "trajectory.csv":
        return "design_complex"
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
    if dataset == "trajectory.csv":
        return "boltz"
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
    if (path / "studio_engine_batch.json").is_file():
        return "iterative_batch"
    if (path / "nise_config.json").is_file():
        return "nise"
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
    for relative in ("studio_engine_batch.json", "studio_run.json", "run_summary.json", "campaign_progress.json", "summary.json", "progress.json"):
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


def _boolean(value: Any) -> Optional[bool]:
    text = str(value or "").strip().lower()
    if text in {"1", "true", "yes", "pass"}:
        return True
    if text in {"0", "false", "no", "fail"}:
        return False
    return None


def _filters(value: Any) -> List[str]:
    return sorted({item.strip() for item in str(value or "").split(";") if item.strip()})


def _metrics(row: Dict[str, str]) -> Dict[str, float]:
    result: Dict[str, float] = {}
    for key in RESULT_METRICS:
        try:
            value = float(row.get(key, ""))
        except (TypeError, ValueError):
            continue
        if value == value and value not in {float("inf"), float("-inf")}:
            result[key] = value
    return result


def _json_map(value: Any) -> Dict[str, Any]:
    if isinstance(value, dict):
        return value
    try:
        parsed = json.loads(str(value or ""))
    except (TypeError, ValueError, json.JSONDecodeError):
        return {}
    return parsed if isinstance(parsed, dict) else {}


def _run_artifact_reference(root: Path, value: Any) -> Optional[str]:
    """Return only a verified path relative to the managed run.

    CSV files intentionally retain their original absolute provenance. A copied
    campaign may therefore mention another Mac. Match the GUI's relocation
    behavior, but never expose or follow an arbitrary external path through MCP.
    """
    text = str(value or "").strip()
    if not text:
        return None
    source = Path(text)
    candidates: List[Path] = []
    if source.is_absolute():
        candidates.append(source)
        parts = source.parts
        positions = [index for index, part in enumerate(parts) if part == root.name]
        if positions:
            suffix = parts[positions[-1] + 1 :]
            if suffix:
                candidates.append(root.joinpath(*suffix))
    else:
        candidates.append(root / source)
    for candidate in candidates:
        try:
            resolved = candidate.resolve()
        except OSError:
            continue
        if resolved == root or root not in resolved.parents or not resolved.is_file():
            continue
        return resolved.relative_to(root).as_posix()
    return None


def _verdict(values: List[Optional[bool]]) -> Optional[bool]:
    known = [value for value in values if value is not None]
    if not known:
        return None
    return any(known)


def _artifact(root: Path, row: Dict[str, str], role: str, path_key: str,
              predictor: Optional[str], context: str) -> Optional[Dict[str, Any]]:
    relative = _run_artifact_reference(root, row.get(path_key))
    if relative is None:
        return None
    return {
        "role": role,
        "path": relative,
        "predictor": predictor,
        "prediction_context": context,
        "metrics": _metrics(row),
        "is_hit": _boolean(row.get("is_hit", row.get("hit"))),
        "failed_filters": _filters(row.get("failed_filters")),
    }


def _iterative_design_predictor(root: Path) -> Optional[str]:
    manifest = root / "studio_run.json"
    if not manifest.is_file():
        return None
    try:
        arguments = load_json(manifest).get("arguments", [])
    except StudioError:
        return None
    if not isinstance(arguments, list) or "--predictor" not in arguments:
        return None
    index = arguments.index("--predictor")
    return str(arguments[index + 1]) if index + 1 < len(arguments) else None


def _iterative_rows(root: Path) -> List[Dict[str, str]]:
    comparison = csv_rows(root / "comparison_scores_long.csv", limit=10000)
    if comparison:
        return comparison
    rows: List[Dict[str, str]] = []
    predictor = _iterative_design_predictor(root) or "unknown"
    for run_root in sorted(root.glob("run_*")):
        if not run_root.is_dir():
            continue
        try:
            run_number = str(int(run_root.name.removeprefix("run_")))
        except ValueError:
            continue
        for raw in csv_rows(run_root / "metrics_per_cycle.csv", limit=10000):
            row = dict(raw)
            row.update({"stage": "design", "predictor": predictor, "run": run_number})
            rows.append(row)
        for checkpoint in sorted(run_root.glob("post_*/cycle_*/post_metrics_row.csv")):
            for raw in csv_rows(checkpoint, limit=1000):
                row = dict(raw)
                row.setdefault("run", run_number)
                row["stage"] = "post"
                row["predictor"] = checkpoint.parents[1].name.removeprefix("post_")
                rows.append(row)
    return rows


def _iterative_overview(root: Path, limit: int, hit_only: bool = False) -> Dict[str, Any]:
    grouped: Dict[int, Dict[int, List[Dict[str, Any]]]] = {}
    for row in _iterative_rows(root):
        try:
            run_number = int(row.get("run", "0"))
            cycle = int(row.get("cycle", "0"))
        except ValueError:
            continue
        stage = str(row.get("stage", "design")).lower()
        predictor = str(row.get("predictor") or _iterative_design_predictor(root) or "unknown")
        role = "complex_reprediction" if stage == "post" else (
            "starting_structure" if cycle == 0 else "designed_complex"
        )
        artifact = _artifact(root, row, role, "structure_path", predictor,
                             "complex" if stage == "post" else "design_stage")
        artifacts = grouped.setdefault(run_number, {}).setdefault(cycle, [])
        if artifact:
            artifacts.append(artifact)
        if stage == "post":
            binder = _artifact(root, row, "binder_alone", "binder_structure_path",
                               predictor, "binder_alone")
            if binder:
                # A binder-only card must not imply that complex scores belong
                # to the monomer prediction.
                binder["metrics"] = {
                    key: value for key, value in binder["metrics"].items()
                    if key in {"binder_plddt", "binder_rmsd"}
                }
                artifacts.append(binder)

    groups: List[Dict[str, Any]] = []
    for run_number in sorted(grouped):
        variants: List[Dict[str, Any]] = []
        trajectory: List[Dict[str, Any]] = []
        for cycle in sorted(grouped[run_number]):
            artifacts = grouped[run_number][cycle]
            verdicts = [item["is_hit"] for item in artifacts]
            failed = sorted({name for item in artifacts for name in item["failed_filters"]})
            title = "Starting structure" if cycle == 0 else f"Cycle {cycle:02d}"
            variant = {
                "id": f"cycle|{cycle}", "title": title, "cycle": cycle,
                "is_hit": _verdict(verdicts), "failed_filters": failed,
                "artifacts": artifacts,
            }
            report_path = root / f"run_{run_number:03d}/cycle_{cycle:02d}/pred_min/geometry_report.json"
            report_reference = _run_artifact_reference(root, report_path)
            if report_reference:
                report = load_json(root / report_reference)
                variant["geometry_diagnostics"] = {
                    "path": report_reference,
                    "policy": report.get("policy"),
                    "violation_count": report.get("violation_count"),
                    "error_count": report.get("error_count"),
                }
            variants.append(variant)
            design = next((item for item in artifacts if item["role"] in {
                "starting_structure", "designed_complex"
            }), None)
            if design:
                trajectory.append({"id": variant["id"], "label": title, "path": design["path"]})
        groups.append({
            "id": f"iterative|{run_number}", "title": f"Run {run_number:02d}",
            "is_hit": _verdict([item["is_hit"] for item in variants]),
            "variants": variants,
            "trajectory": {
                "frames": trajectory,
                "reference": trajectory[0]["id"] if trajectory else None,
                "alignment": "matching target-chain C-alpha atoms (chains B onward)",
                "excludes": "independent complex and binder-alone validation structures",
            },
        })
    if hit_only:
        groups = [group for group in groups if group.get("is_hit") is True]
    return {
        "organization": "run -> cycle -> design/complex-reprediction/binder-alone",
        "groups": groups[:limit], "truncated": len(groups) > limit,
    }


def _rfd3_backbone_rows(root: Path) -> List[Dict[str, str]]:
    rows = csv_rows(root / "rfd3/backbone_metrics.csv", limit=10000)
    if rows:
        return rows
    recovered: List[Dict[str, str]] = []
    for result in sorted((root / "rfd3").glob("**/results/design_*.json")):
        try:
            raw = load_json(result)
        except StudioError:
            continue
        row = {key: str(value) for key, value in raw.items() if not isinstance(value, (dict, list))}
        for key in ("diffused_index_map", "motif_fixed_atoms", "motif_insertion_rmsd_by_token"):
            if key in raw:
                row[key] = json.dumps(raw[key], sort_keys=True)
        design = result.stem
        row["design"] = design
        row["backbone_pdb"] = str(result.parent.parent / "backbones" / f"{design}.pdb")
        recovered.append(row)
    return recovered


def _rfd3_overview(root: Path, limit: int) -> Dict[str, Any]:
    backbone_rows = _rfd3_backbone_rows(root)
    backbone_names = {
        str(row.get("design") or Path(str(row.get("backbone_pdb", ""))).stem)
        for row in backbone_rows
    }
    derivative_parent: Dict[str, str] = {}
    sequence_by_derivative: Dict[str, str] = {}
    for row in csv_rows(root / "mpnn/sequences.csv", limit=10000):
        parent = Path(str(row.get("backbone_pdb", ""))).stem or str(row.get("design", ""))
        base = str(row.get("design") or parent)
        index = str(row.get("seq_index", "")).strip()
        derivative = str(row.get("name") or (f"{base}_{index}" if index else base))
        derivative_parent[derivative] = parent
        if row.get("sequence"):
            sequence_by_derivative[derivative] = row["sequence"]

    verdict_rows: Dict[str, Dict[str, str]] = {}
    for relative in ("analysis/top100.csv", "analysis/scored_designs.csv", "analysis/design_metrics.csv"):
        for row in csv_rows(root / relative, limit=10000):
            key = str(row.get("name") or row.get("design") or "")
            if key:
                verdict_rows[key] = {**verdict_rows.get(key, {}), **row}
    rmsd_rows = {
        str(row.get("name") or row.get("design") or ""): row
        for row in csv_rows(root / "analysis/rmsd_metrics.csv", limit=10000)
    }

    def parent_for(derivative: str, row: Dict[str, str]) -> str:
        explicit = Path(str(row.get("backbone_pdb", ""))).stem
        if explicit:
            return explicit
        if derivative in derivative_parent:
            return derivative_parent[derivative]
        matches = [name for name in backbone_names if derivative == name or derivative.startswith(name + "_")]
        return max(matches, key=len) if matches else derivative

    groups: Dict[str, Dict[str, Any]] = {}
    for row in backbone_rows:
        parent = str(row.get("design") or Path(str(row.get("backbone_pdb", ""))).stem)
        if not parent:
            continue
        group = groups.setdefault(parent, {"primary_artifacts": [], "variants": {}})
        artifact = _artifact(root, row, "generated_backbone", "backbone_pdb",
                             "rfd3-mlx", "generated_backbone")
        if artifact:
            artifact["motif_mapping"] = _json_map(row.get("diffused_index_map"))
            group["primary_artifacts"].append(artifact)

    prediction_sets = (
        ("predictions/holo/prediction_metrics.csv", "complex_reprediction", "complex"),
        ("predictions/complex/prediction_metrics.csv", "complex_reprediction", "complex"),
        ("predictions/apo/prediction_metrics.csv", "binder_alone", "binder_alone"),
        ("predictions/monomer/prediction_metrics.csv", "binder_alone", "binder_alone"),
        ("predictions/binder/prediction_metrics.csv", "binder_alone", "binder_alone"),
    )
    for dataset, role, context in prediction_sets:
        for raw in csv_rows(root / dataset, limit=10000):
            derivative = str(raw.get("name") or raw.get("design") or "")
            if not derivative:
                continue
            row = {**raw, **rmsd_rows.get(derivative, {}), **verdict_rows.get(derivative, {})}
            parent = parent_for(derivative, row)
            group = groups.setdefault(parent, {"primary_artifacts": [], "variants": {}})
            variant = group["variants"].setdefault(derivative, {
                "id": derivative,
                "title": (f"MPNN sequence {derivative[len(parent) + 1:]}"
                          if derivative.startswith(parent + "_") else derivative),
                "sequence": sequence_by_derivative.get(derivative),
                "artifacts": [],
            })
            predictor = _result_predictor(dataset, row) or "unknown"
            if role == "binder_alone" and not str(row.get("binder_plddt", "")).strip():
                row["binder_plddt"] = str(row.get("complex_plddt", ""))
            artifact = _artifact(root, row, role, "pdb", predictor, context)
            if artifact:
                if role == "binder_alone":
                    artifact["metrics"] = {
                        key: value for key, value in artifact["metrics"].items()
                        if key in {"binder_plddt", "binder_rmsd"}
                    }
                variant["artifacts"].append(artifact)

    result_groups: List[Dict[str, Any]] = []
    for parent in sorted(groups)[:limit]:
        group = groups[parent]
        variants: List[Dict[str, Any]] = []
        for derivative in sorted(group["variants"]):
            variant = group["variants"][derivative]
            verdicts = [item["is_hit"] for item in variant["artifacts"]]
            variant["is_hit"] = _verdict(verdicts)
            variant["failed_filters"] = sorted({
                name for item in variant["artifacts"] for name in item["failed_filters"]
            })
            variants.append(variant)
        result_groups.append({
            "id": f"rfd3|{parent}", "title": parent,
            "is_hit": _verdict([item["is_hit"] for item in variants]),
            "primary_artifacts": group["primary_artifacts"],
            "variants": variants,
        })
    return {
        "organization": "RFdiffusion3 backbone -> MPNN derivative -> complex/binder-alone validation",
        "groups": result_groups,
    }


def _nise_overview(root, limit):
    groups = {}
    count = 0
    checks = {r["name"]: r for r in load_json(root / "preorg.json").get("ranked", [])} if (root / "preorg.json").is_file() else {}
    truncated = False
    for path in sorted((root / "candidates").glob("*.json")):
        if count >= max(1, min(limit, 500)):
            truncated = True
            break
        row = load_json(path)
        structure = _run_artifact_reference(root, row.get("pdb"))
        if structure is None:
            continue
        tid = row.get("trajectory")
        key = f"trajectory-{tid}" if tid is not None else "broad-search"
        group = groups.setdefault(key, {"id": key, "title": f"Trajectory {tid + 1}" if tid is not None else "Broad search", "variants": [], "is_hit": None})
        masked = row.get("branch") == "masked-backbone"
        artifacts = [{"role": "masked_backbone" if masked else "designed_complex", "path": structure, "predictor": "boltz"}]
        check = checks.get(row["name"])
        if check:
            apo = _run_artifact_reference(root, check.get("apo_pdb"))
            if apo:
                artifacts.append({"role": "binder_alone", "path": apo, "predictor": "boltz", "metrics": {k: v for k, v in check.items() if k not in {"apo_pdb", "holo_pdb"}}})
        group["variants"].append({"id": row["name"], "cycle": row["cycle"], "is_hit": None,
            "passed_self_consistency": row.get("geometry_passed", row["passed"]),
            "passed_selection": row["passed"], "score_status": row.get("score_status", "scored"),
            "sequence": row["sequence"], "branch": row.get("branch", "mpnn"),
            "final_eligible": row.get("final_eligible", row["passed"] and not masked),
            "nesso_screening_scores": row.get("nesso"),
            "psichic_screening_scores": row.get("psichic"),
            "metrics": {k: row.get(k) for k in ("ligand_plddt", "pbind", "score", "ca_rmsd", "ligand_rmsd")}, "artifacts": artifacts})
        count += 1
    return {"organization": "trajectory → cycle/candidate → holo/apo artifacts", "groups": list(groups.values()),
            "candidate_limit": limit, "returned_candidates": count, "truncated": truncated,
            "note": "Self-consistency is a search filter, not an independently validated binding hit. Preorganisation reranks only the final apo-tested shortlist."}


def _iterative_batch_overview(root: Path, limit: int, framework_id: Optional[str],
                              design_engine: Optional[str], hit_only: bool) -> Dict[str, Any]:
    descriptor = load_json(root / "studio_engine_batch.json")
    paths = descriptor.get("campaigns", [])
    if not isinstance(paths, list) or not paths or len({Path(p).name for p in paths}) != len(paths):
        raise StudioError("The saved batch has invalid campaign membership.")
    workspace = root.parent.resolve()
    campaigns, groups = [], []
    for index, path in enumerate(paths):
        child = (workspace / Path(path).name).resolve()
        if child.parent != workspace or not (child / "studio_run.json").is_file():
            raise StudioError("A batch campaign is missing or outside its workspace: " + Path(path).name)
        manifest = load_json(child / "studio_run.json")
        request = manifest.get("request", {})
        framework = request.get("scaffoldID", "none")
        ids = descriptor.get("engineIDs", [])
        engine = ids[index] if index < len(ids) else request.get("designPredictor", "unknown")
        child_id = workspace.name + "/" + child.name
        campaigns.append({"run_id": child_id, "framework_id": framework, "design_engine": engine,
                          "requested_trajectories": request.get("numDesigns", 0),
                          "optimization_cycles": request.get("numCycles", 0)})
        if framework_id is not None and framework_id != framework:
            continue
        if design_engine is not None and design_engine != engine:
            continue
        for group in _iterative_overview(child, limit + 1, hit_only)["groups"]:
            if hit_only and group.get("is_hit") is not True:
                continue
            group.update(id="iterative|" + child.name + "|" + group["id"],
                         title=framework + " · " + engine + " · " + group["title"],
                         campaign_run_id=child_id, framework_id=framework, design_engine=engine,
                         artifact_run_id=child_id)
            groups.append(group)
    return {"organization": "framework / engine campaign -> independent trajectory -> cycle -> artifacts",
            "campaigns": campaigns, "groups": groups[:limit], "truncated": len(groups) > limit,
            "frameworks": sorted({c["framework_id"] for c in campaigns}),
            "design_engines": sorted({c["design_engine"] for c in campaigns}),
            "requested_trajectories": sum(c["requested_trajectories"] for c in campaigns),
            "expected_optimized_cycle_outputs": sum(c["requested_trajectories"] * c["optimization_cycles"] for c in campaigns),
            "note": "Artifact paths are relative to each group's artifact_run_id, not the batch. Cycle outputs are not independent trajectories. Query each campaign_run_id for raw tables."}


def results_overview(run_id: str, hit_only: bool = False, limit: int = 100,
                     framework_id: Optional[str] = None, design_engine: Optional[str] = None) -> Dict[str, Any]:
    """Return the same scientific hierarchy presented by the native app.

    This intentionally complements, rather than replaces, results_query: agents
    use the overview to understand parentage and verdicts, then query a named
    table when they need every raw column or a distribution.
    """
    root = resolve_run(run_id)
    workflow = classify_run(root)
    if workflow == "iterative_batch":
        result = _iterative_batch_overview(root, limit, framework_id, design_engine, hit_only)
    elif framework_id is not None or design_engine is not None:
        raise StudioError("Framework/engine filters require an iterative batch run_id.")
    elif workflow == "nise":
        result = _nise_overview(root, limit)
    elif workflow == "iterative":
        result = _iterative_overview(root, limit, hit_only)
    elif workflow == "rfdiffusion3":
        result = _rfd3_overview(root, limit)
    else:
        result = {
            "organization": "prediction batch (one independent result per emitted sample)",
            "groups": [],
            "note": "Use results_query for prediction batches.",
        }
    groups = result["groups"]
    if hit_only:
        groups = [group for group in groups if group.get("is_hit") is True]
    return {
        "run_id": run_id,
        "workflow": workflow,
        **result,
        "groups": groups,
        "truncated": result.get("truncated", len(groups) >= limit),
        "next_step": (
            "Use results_query with one of run_status.result_files for raw rows and score distributions. "
            "Treat derivative/cycle verdicts as authoritative; never promote a parent merely because one artifact looks plausible."
        ),
    }


def workflow_guide(workflow: str) -> Dict[str, Any]:
    """Return client-neutral operating guidance for the typed Studio tools.

    This deliberately lives in the MCP server rather than only in a Codex or
    Claude skill: desktop clients receive the same scientific routing rules.
    """
    if workflow == "nise":
        return {"workflow": "nise", "tool": "nise_plan", "designer": "lasermpnn", "predictor": "boltz",
                "objective": "ligand_pLDDT/100 + affinity_probability_binary; missing affinity fails",
                "order": ["system_detect", "nise_plan", "job_start with plan digest", "job_status", "results_overview", "results_query"],
                "scope": "Small molecules only. Apo preorganisation is an optional final shortlist analysis.",
                "geometry": "Optional exposure_mode=biotin-carboxamide-v1 for verified free biotin: accept open/restricted exits, reject unresolved/blocked, no rotation rescue. Shared repeated checks after folding and self-consistency, before Boltz affinity; NESSO cannot check coordinates. Terminal acid oxygen SASA is replaced; other atom requirements remain. Bounded CPU workers with immutable per-structure geometry receipts.",
                "initial_restart": "nise_plan restart_from accepts a source NISE directory name in the same project. Audits and copies matching Protein Hunter cycle00 predictions into a new immutable plan, recalculating selection; source run and old decisions remain unchanged.",
                "stages": {"initial_backbones": ["backbone_method", "rfd3_num_bins", "num_starts", "binder_min_len", "binder_max_len", "phase0_refine_cycles", "phase0_seqs1", "phase0_gate_seqs", "phase0_seqs2", "early_score_gate", "phase0_sc_ca", "phase0_nesso_screen", "phase0_nesso_refine_top_k", "phase0_nesso_expand_top_k"],
                           "optimization": ["trajectories", "first_cycle_seqs", "partial_noising", "noise_radius", "noise_percent", "noise_predictions", "noise_mpnn_seqs", "noise_advance", "nise_seqs", "beam", "max_cycles", "patience", "nesso_screen", "nesso_top_k", "nise_sc_ca", "nise_sc_lig", "nise_ligand_sc_from_cycle", "adaptive_proposals", "initial_proposals", "min_improvement", "selective_affinity", "affinity_batch_size"]},
                "initial_generator": "Choose protein-hunter (default X-token hallucination) or rfdiffusion3 (experimental). Total starts default to 1,000. RFdiffusion3 shares starts across length groups, then uses the same NISE funnel; it never substitutes hallucination on failure.",
                "advancement": "first_cycle_seqs defaults to 64 from each starting seed; later cycles use nise_seqs=32 per parent and beam=3 (up to 96). Optional partial_noising reduces ordinary sampling to the best beam - noise_advance current parents (default two) and uses one branch from the best current parent from cycle 2: 32 masked Boltz folds, select the best passing backbone, 32 MPNN repairs, optional NESSO shortlist, then Boltz scoring. Reserve noise_advance=1 places, keep two normal places; failed branch places stay empty. Mask within 6 Angstrom heavy-atom distance at 25%, experimental. This changes sequence identity, not coordinates; masked scores cannot become finalists. With no screening, default noising uses 64 normal + 32 masked + 32 repair = 128 later folds. Legacy saved requests retain one sampling count. Optional adaptive rounds double from initial_proposals to this cap without replacing parents. NESSO shortlists each new round, pooling folded results. No rollback or rescue.",
                "search_policy": "New requests: 0.80 first-refinement Boltz gate, selective affinity, 30 optimization cycles, four-cycle patience, 8 seeds and beam 3. Adaptive proposals are experimental and off by default. Selective affinity evaluates geometry first, omits the head at cycle00/gate, and bounds P(bind) by 1 for exact selection among folded candidates. Biotin retrospective savings are not Studio benchmarks.",
                "screening_engine": "nesso (default) or psichic; both experimental. PSICHIC ranks 1 - predicted_nonbinder, supports complete sequences up to 700 residues, GPU ESM batch8 + CPU graph16. It has no placement-confidence term. All four original outputs are saved. Existing nesso_screen/phase0_nesso_screen switches and shortlist budgets apply to the selected engine. scoring_mode=boltz (default) retains Boltz final selection; scoring_mode=screening uses the chosen scorer for all scored advancement and patience, with Boltz structure/geometry only and no affinity head. Objective mode requires both screening switches, selective_affinity=true (geometry-first execution), policy3 and partial_noising=false. nesso_early_score_gate (0–2) and psichic_early_score_gate (0–1) default to 0.4 and 0.2 respectively (0 disables); never reuse Boltz early_score_gate for these objectives.",
                "nesso": "Independent optional initial and optimization screens. Initial refinement folds phase0_nesso_refine_top_k per lineage (default 1); the gate remains unscreened; expansion scores all derivatives, selects max one per original lineage and folds phase0_nesso_expand_top_k total (default 20). Boltz performs all atom/structural checks; final ranking uses the objective selected by scoring_mode. NESSO exposes no ligand pLDDT. nesso_top_k is a per-trajectory shortlist, pooled across that trajectory's parents. Rank by NESSO P(bind) + (1 - entropy_crop_pl), with deterministic name ties. Require finite pocket-cropped protein-ligand entropy in (0.000001, 1]; reject invalid placements before shortlist caps. Full entropy is diagnostic only. All scores and rejections are saved; no fallback. Accuracy for designed binders is unvalidated.",
                "scheduling": "One exclusive GPU owner; within-cycle model reuse by default; cross-cycle resident structure and affinity models are experimental pending ligand throughput validation.",
                "resume": "Replay audited sequence/prediction operations from Phase 0; never resample completed sequences.",
                "smoke": "Use a bounded trial before a large campaign. Keep raw outputs and record validation in both Lab Books."}
    common = {
        "execution_contract": [
            "Call system_detect; never infer installation state from tool availability.",
            "Create a workflow plan and review its normalized_request and command_preview.",
            "Start only with the returned plan_id and plan_sha256.",
            "Use job_wait/job_status; on failure read message, error, and pipeline_log_tail before changing any setting.",
            "Use runs_list and run_status, then results_overview before results_query. The overview preserves scientific parentage; the query exposes raw tables and distributions.",
            "Never request arbitrary filesystem access for a managed run. Artifact paths returned by results_overview are verified relative to that run.",
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
                "Review results as backbone -> MPNN derivative -> complex and binder-alone validation. The saved hit verdict belongs to the derivative; a generated backbone alone is never a validated hit.",
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
                "Review the source backbone and each sequence derivative together with target-aligned complex recovery and binder-alone recovery; do not interpret those predictions as unrelated designs.",
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
                "Score motif recovery only from the recorded functional atoms and mapping. Keep generator insertion RMSD distinct from independently predicted motif RMSD.",
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
            "defaults": {"target_template_mode": "guide"},
            "rules": [
                "Use the MCP plan rather than assembling the runner command; Studio injects the measured resident/cycle-wave scheduler.",
                "Require target MSAs when target protein chains are present, and use an orthogonal predictor for final checking when requested. Unconditioned monomer initialization has no target MSA.",
                "When the user supplies a trusted target PDB/CIF, pass it as target_template_path. Guide mode works with Boltz-2, Protenix v2, and IntelliFold v2 Flash/full. Do not request strong coordinate restraint; it is disabled after Apple-GPU acceptance failures.",
                "The target template applies only to target chains during design cycles. Never template binder A or independent complex/binder-alone validation folds.",
                "Secondary-structure control is initialization-only helix kill: --negative-helix-constant accepts a finite strength from 0 to 1, with 0 disabled. Later MPNN cycles use normal sampling. Beta, mixed, sustained, loop-kill and inspection controls are retired.",
                "Nanobody GUI budgets explicitly choose a total across frameworks, the same count per framework, or custom allocations. Saved child numDesigns/--num-runs is the independent trajectory count, not the number of cycle outputs. Eight frameworks at 100 each means 800 trajectories per engine; five cycles means 4000 optimized outputs plus 800 starts.",
                "runs_list includes iterative_batch parents. Use results_overview on that parent with optional framework_id/design_engine filters; read each group artifact_run_id when resolving artifacts, and query campaign_run_id for its raw tables. Earlier framework outputs remain part of the batch.",
                "Review results as run -> ordered cycles. Each cycle keeps its design structure, independent complex reprediction, binder-alone fold, scores, and saved filter verdict together.",
                "The GUI trajectory contains only cycle design-stage structures, ordered from cycle 00, and rigidly aligns later frames to matching target-chain C-alpha atoms (chains B onward). Do not mix validation folds into that optimization trajectory.",
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
        for suffix in ("/status", "/manifest", "/overview", "/metrics", "/artifacts"):
            if remainder.endswith(suffix):
                run_id = remainder[: -len(suffix)]
                if suffix == "/status":
                    return run_status(run_id)
                if suffix == "/overview":
                    return results_overview(run_id, False, 100)
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
