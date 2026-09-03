from __future__ import annotations

import copy
import json
import math
import re
import secrets
from pathlib import Path
from typing import Any, Dict, List, Tuple

from .common import (
    StudioError,
    agent_root,
    atomic_json,
    canonical_digest,
    file_digest,
    import_artifact,
    project_root,
    runtime_root,
    utc_now,
    validate_slug,
)


PREDICTORS = {"boltz", "intellifold", "protenix-v2", "protenix-mini", "openfold-3-mlx"}
SEQUENCE_MODELS = {"lasermpnn", "ligandmpnn", "solublempnn", "proteinmpnn"}
RFD3_MODES = {"deNovo", "partialDiffusion", "motifScaffolding"}
BOOLEAN_ITERATIVE_FLAGS = {
    "--boltz-use-potentials", "--boltz-no-potentials", "--post-binder-alone",
    "--post-no-binder-alone", "--require-target-msa", "--random-binder",
    "--helix-kill",
}
VALUE_ITERATIVE_FLAGS = {
    "--workflow", "--predictor", "--sequence-designer", "--num-runs",
    "--num-opt-cycles", "--iptm-threshold", "--model", "--post-predictor",
    "--post-mode", "--post-iptm-threshold", "--filter-min-iptm",
    "--filter-min-ipsae", "--filter-max-complex-rmsd",
    "--filter-min-binder-plddt", "--filter-max-binder-rmsd", "--mpnn-seed",
    "--antifold-seed", "--lasermpnn-seed", "--ligand-temp-cycle1",
    "--ligand-temp-other", "--target-msa-mode", "--target-msa-generator",
    "--nanobody-cdrs", "--nanobody-cdr-ranges", "--binder-min-len",
    "--binder-max-len", "--binder-random-seed", "--negative-helix-constant",
}
RESERVED_ITERATIVE_FLAGS = {
    "--template-yaml", "--run-name", "--out-root", "--max-parallel",
    "--design-scheduler", "--wave-batch-size", "--throughput-profile",
    "--mps-memory-reserve-gb", "--mps-mem-fraction", "--resume",
}
INSTALL_COMPONENTS = {
    "boltz": "--with-boltz",
    "boltz-affinity": "--with-boltz-affinity",
    "intellifold": "--with-intellifold",
    "intellifold-full": "--with-intellifold-full",
    "protenix-v2": "--with-protenix-v2",
    "protenix-mini": "--with-protenix-mini",
    "protenix-constraint": "--with-protenix-constraint",
    "openfold-3": "--with-openfold3",
    "antifold": "--with-antifold",
    "lasermpnn": "--with-lasermpnn",
    "rfd3": "--with-rfd3",
}


def _bounded_int(value: Any, label: str, minimum: int, maximum: int) -> int:
    if isinstance(value, bool):
        raise StudioError(f"{label} must be an integer.")
    try:
        number = int(value)
    except (TypeError, ValueError) as exc:
        raise StudioError(f"{label} must be an integer.") from exc
    if number < minimum or number > maximum:
        raise StudioError(f"{label} must be between {minimum} and {maximum}.")
    return number


def _bounded_float(value: Any, label: str, minimum: float, maximum: float) -> float:
    if isinstance(value, bool):
        raise StudioError(f"{label} must be a number.")
    try:
        number = float(value)
    except (TypeError, ValueError) as exc:
        raise StudioError(f"{label} must be a number.") from exc
    if number < minimum or number > maximum:
        raise StudioError(f"{label} must be between {minimum} and {maximum}.")
    return number


def _reject_protein_denovo_contig(value: Any) -> None:
    """Keep adapter grammar out of agent-authored scientific requests."""
    if value is None or not str(value).strip():
        return
    raise StudioError(
        "Omit `contig` for protein de-novo design. Studio derives the pinned MLX adapter's "
        "canonical binder-first form from `lengths` and the inspected target chains. "
        "RFdiffusion1-style `A1-236/0 45-75` is incompatible, and even an apparently valid "
        "manual contig is rejected so it cannot silently disagree with the normalized target. "
        "Do not change unrelated potentials, calibration, or length settings to work around "
        "this error."
    )


def _script_provenance(paths: List[Path]) -> List[Dict[str, Any]]:
    result = []
    for path in paths:
        if not path.is_file():
            raise StudioError(f"Required installed script is missing: {path}")
        result.append({"path": str(path), "sha256": file_digest(path)})
    return result


def _persist(kind: str, project: str, normalized: Dict[str, Any], preview: List[str], resource_class: str, provenance: List[Dict[str, Any]]) -> Dict[str, Any]:
    body = {
        "schema_version": 1,
        "kind": kind,
        "project": project,
        "normalized_request": normalized,
        "command_preview": preview,
        "resource_class": resource_class,
        "provenance": provenance,
    }
    digest = canonical_digest(body)
    plan_id = f"plan-{digest[:16]}"
    plan = {**body, "id": plan_id, "sha256": digest, "created_at": utc_now()}
    path = agent_root() / "plans" / f"{plan_id}.json"
    if path.exists():
        existing = json.loads(path.read_text(encoding="utf-8"))
        if existing.get("sha256") != digest:
            raise StudioError(f"Plan collision at {path}")
        return existing
    atomic_json(path, plan)
    return plan


def _prediction_plan(arguments: Dict[str, Any], kind: str, output_folder: str, prefix: str) -> Dict[str, Any]:
    root = runtime_root()
    project = validate_slug(arguments.get("project", ""))
    project_root(project)
    request = copy.deepcopy(arguments.get("request"))
    if not isinstance(request, dict):
        raise StudioError("request must be a prediction JSON object.")
    predictors = request.get("predictors")
    if not isinstance(predictors, list) or not predictors:
        raise StudioError("Select at least one prediction engine.")
    if any(value not in PREDICTORS for value in predictors) or len(set(predictors)) != len(predictors):
        raise StudioError("Prediction engines must be distinct supported engine identifiers.")
    jobs = request.get("jobs")
    if not isinstance(jobs, list) or not jobs or len(jobs) > 10_000:
        raise StudioError("jobs must contain between 1 and 10,000 folds.")
    normalized_jobs = []
    seen = set()
    for index, job in enumerate(jobs):
        if not isinstance(job, dict) or not isinstance(job.get("chains"), list) or not job["chains"]:
            raise StudioError(f"Prediction job {index + 1} has no chains.")
        name = validate_slug(job.get("name", f"fold-{index + 1}"), "job name")
        if name in seen:
            raise StudioError(f"Duplicate prediction job name: {name}")
        seen.add(name)
        chains = []
        chain_ids = set()
        for chain in job["chains"]:
            if not isinstance(chain, dict):
                raise StudioError(f"Job {name} contains an invalid chain.")
            chain_id = str(chain.get("id", "")).strip().upper()
            if not re.fullmatch(r"[A-Z0-9]{1,4}", chain_id) or chain_id in chain_ids:
                raise StudioError(f"Job {name} has an invalid or duplicate chain ID.")
            chain_ids.add(chain_id)
            chain_kind = chain.get("kind")
            if chain_kind == "protein":
                sequence = re.sub(r"\s+", "", str(chain.get("sequence", ""))).upper()
                if not sequence or not re.fullmatch(r"[ACDEFGHIKLMNPQRSTVWYX]+", sequence):
                    raise StudioError(f"Job {name}, chain {chain_id} has an invalid protein sequence.")
                msa = chain.get("msa", "auto")
                if msa not in {"auto", "empty"}:
                    artifact = import_artifact(str(msa))
                    msa = artifact["path"]
                chains.append({"id": chain_id, "kind": chain_kind, "sequence": sequence, "msa": msa})
            elif chain_kind == "ligand":
                smiles = str(chain.get("smiles", "")).strip()
                if not smiles or len(smiles) > 10_000:
                    raise StudioError(f"Job {name}, chain {chain_id} has no usable SMILES string.")
                chains.append({"id": chain_id, "kind": chain_kind, "smiles": smiles})
            else:
                raise StudioError(f"Job {name}, chain {chain_id} must be protein or ligand.")
        normalized_jobs.append({"name": name, "chains": chains})
    contains_ligand = any(chain["kind"] == "ligand" for job in normalized_jobs for chain in job["chains"])
    if request.get("affinity", False) and ("boltz" not in predictors or not contains_ligand):
        raise StudioError("The affinity head requires Boltz and at least one ligand chain.")
    intellifold_model = request.get("intellifold_model", "v2-flash")
    if intellifold_model not in {"v2-flash", "v2"}:
        raise StudioError("intellifold_model must be v2-flash or v2.")
    run_suffix = secrets.token_hex(4)
    output = project_root(project) / output_folder / f"{prefix}-{run_suffix}"
    config = {
        "root": str(root),
        "output": str(output),
        "predictors": predictors,
        "intellifold_model": intellifold_model if "intellifold" in predictors else None,
        "use_potentials": bool(request.get("use_potentials", False) and "boltz" in predictors),
        "affinity": bool(request.get("affinity", False) and "boltz" in predictors and contains_ligand),
        "num_seeds": _bounded_int(request.get("num_seeds", 1), "num_seeds", 1, 20),
        "diffusion_samples": _bounded_int(request.get("diffusion_samples", 0), "diffusion_samples", 0, 20),
        "max_parallel": _bounded_int(request.get("max_parallel", 0), "max_parallel", 0, 128),
        "batch_size": _bounded_int(request.get("batch_size", 0), "batch_size", 0, 1024),
        "msa": {
            "cache_dir": str(root / "msa_cache"),
            "index_roots": [str(root / "msa_cache"), str(root / "objects" / "sha256"), str(root / "scaffold_msa_cache"), str(root / "projects")],
            "allow_server": not bool(request.get("offline_only", False)),
        },
        "jobs": normalized_jobs,
    }
    script = root / "rfd3_scripts" / "predict_batch.py"
    preview = ["/usr/bin/caffeinate", "-dimsu", "/usr/bin/python3", str(script), "--config", str(output / "prediction_config.json")]
    return _persist(kind, project, {"config": config, "output": str(output)}, preview, "apple_gpu_exclusive", _script_provenance([script]))


def prediction_plan(arguments: Dict[str, Any]) -> Dict[str, Any]:
    return _prediction_plan(arguments, "prediction", "prediction_runs", "prediction-mcp")


def target_prepare_plan(arguments: Dict[str, Any]) -> Dict[str, Any]:
    sequences = arguments.get("sequences")
    if not isinstance(sequences, list) or not sequences:
        raise StudioError("sequences must contain at least one target protein chain.")
    chains = []
    for index, record in enumerate(sequences):
        if not isinstance(record, dict):
            raise StudioError("Each target sequence must contain an id and sequence.")
        chains.append({"id": record.get("id", chr(ord("A") + index)), "kind": "protein", "sequence": record.get("sequence", ""), "msa": "auto"})
    request = {
        "predictors": arguments.get("predictors"),
        "intellifold_model": arguments.get("intellifold_model", "v2-flash"),
        "offline_only": bool(arguments.get("offline_only", False)),
        "num_seeds": arguments.get("num_seeds", 1),
        "diffusion_samples": arguments.get("diffusion_samples", 0),
        "max_parallel": arguments.get("max_parallel", 0),
        "batch_size": arguments.get("batch_size", 0),
        "jobs": [{"name": arguments.get("name", "prepared-target"), "chains": chains}],
    }
    return _prediction_plan({"project": arguments.get("project"), "request": request}, "target_prepare", "target_runs", "target-mcp")


def _normalize_iterative_arguments(values: Any) -> Tuple[List[str], str]:
    if not isinstance(values, list) or not values or not all(isinstance(item, str) for item in values):
        raise StudioError("arguments must be a non-empty array of command argument strings.")
    normalized: List[str] = []
    seen = set()
    index = 0
    predictor = None
    while index < len(values):
        flag = values[index]
        if flag in RESERVED_ITERATIVE_FLAGS:
            raise StudioError(f"{flag} is controlled by Studio for reproducibility and scheduling.")
        if flag in BOOLEAN_ITERATIVE_FLAGS:
            if flag in seen:
                raise StudioError(f"Duplicate iterative argument: {flag}")
            normalized.append(flag)
            seen.add(flag)
            index += 1
            continue
        if flag not in VALUE_ITERATIVE_FLAGS or index + 1 >= len(values):
            raise StudioError(f"Unsupported or valueless iterative argument: {flag}")
        value = values[index + 1]
        if value.startswith("--") or "\x00" in value or len(value) > 20_000:
            raise StudioError(f"Invalid value for {flag}.")
        if flag == "--predictor":
            predictor = value
        normalized.extend([flag, value])
        seen.add(flag)
        index += 2
    required = {"--workflow", "--predictor", "--sequence-designer", "--num-runs", "--num-opt-cycles", "--iptm-threshold"}
    missing = sorted(required - seen)
    if missing:
        raise StudioError(f"Missing required iterative arguments: {', '.join(missing)}")
    assert predictor is not None
    return normalized, predictor


def iterative_plan(arguments: Dict[str, Any]) -> Dict[str, Any]:
    root = runtime_root()
    project = validate_slug(arguments.get("project", ""))
    destination = project_root(project)
    template = import_artifact(str(arguments.get("template_path", "")))
    user_args, predictor = _normalize_iterative_arguments(arguments.get("arguments"))
    run_name = validate_slug(arguments.get("run_name", f"mcp-{secrets.token_hex(4)}"), "run name")
    campaign = destination / run_name
    if campaign.exists():
        raise StudioError(f"Run directory already exists: {campaign}")
    scheduler = ["--max-parallel", "1", "--mps-memory-reserve-gb", "2", "--mps-mem-fraction", "0.8", "--throughput-profile", "auto"]
    if predictor == "protenix-v2":
        scheduler += ["--design-scheduler", "cycle-wave"]
    else:
        scheduler += ["--design-scheduler", "resident", "--wave-batch-size", "all"]
    final_args = user_args + ["--template-yaml", str(campaign / "input_template.yaml"), "--run-name", run_name, "--out-root", str(destination)] + scheduler + ["--resume"]
    overrides = arguments.get("environment_overrides", {})
    if not isinstance(overrides, dict):
        raise StudioError("environment_overrides must be an object.")
    runner = root / "nanohunter_run.sh"
    preview = ["/usr/bin/caffeinate", "-dimsu", str(runner)] + final_args
    normalized = {"arguments": final_args, "environment_overrides": overrides, "template_artifact": template, "campaign": str(campaign), "run_name": run_name}
    return _persist("iterative_design", project, normalized, preview, "apple_gpu_exclusive", _script_provenance([runner]))


def rfd3_plan(arguments: Dict[str, Any], expected_mode: str) -> Dict[str, Any]:
    if expected_mode not in RFD3_MODES:
        raise StudioError(f"Internal unsupported RFD3 mode: {expected_mode}")
    root = runtime_root()
    project = validate_slug(arguments.get("project", ""))
    destination = project_root(project)
    request = copy.deepcopy(arguments.get("request"))
    if not isinstance(request, dict):
        raise StudioError("request must be an RFD3 Studio request object.")
    supplied_mode = request.get("design_mode", expected_mode)
    if supplied_mode != expected_mode:
        raise StudioError(f"This tool only accepts design_mode={expected_mode}.")
    target_kind = request.get("target_kind")
    if target_kind not in {"protein", "small_molecule"}:
        raise StudioError("target_kind must be protein or small_molecule.")
    if expected_mode != "deNovo" and target_kind != "protein":
        raise StudioError("Partial diffusion and motif scaffolding require a protein binder-target complex.")
    defaults = {
        "conditions": {}, "is_non_loopy": True, "lengths": [65], "num_backbones": 100,
        "timesteps": 200, "recycles": 2, "batch_size": 4,
        "queues_per_bin": 2, "precision": "bf16", "seed_base": 0,
        "sequences_per_backbone": 4, "sequence_temperature": 0.10,
        "first_shell_temperature": 1.00, "use_potentials": True,
        "run_affinity": target_kind == "small_molecule", "run_apo": True,
        "hit_filters": {}, "extra_predictors": [], "intellifold_model": "v2-flash",
        "conformers": [], "mpnn_max_parallel": 6, "boltz_chunk_size": 50,
        "boltz_calibrate_n": 12, "preserve_partial_sequence": True,
        "source_binder_chain": "A",
    }
    if target_kind == "small_molecule":
        defaults.update({"component_id": "LG1", "ligand_source": "smiles"})
    else:
        # Match the GUI's visible, literature-informed starting filters. They
        # remain editable and are persisted with the plan.
        defaults["hit_filters"] = {
            "minimum_iptm": 0.50,
            "minimum_ipsae_min": 0.50,
            "maximum_complex_rmsd": 2.5,
            "minimum_binder_plddt": 0.80,
            "maximum_binder_rmsd": 2.0,
            **({"maximum_motif_rmsd": 1.0} if expected_mode == "motifScaffolding" else {}),
        }
    for key, value in defaults.items():
        request.setdefault(key, value)
    request.setdefault("sequence_model", "solublempnn" if target_kind == "protein" else "lasermpnn")
    run_name = validate_slug(arguments.get("run_name", f"rfd3-mcp-{secrets.token_hex(4)}"), "run name")
    campaign = destination / "rfd3_runs" / run_name
    if campaign.exists():
        raise StudioError(f"Run directory already exists: {campaign}")
    if target_kind == "protein":
        artifact = import_artifact(str(request.get("target_structure", "")))
        request["target_structure"] = artifact["path"]
        chains = request.get("target_chains") or [part.strip() for part in str(request.get("target_chain", "B")).split(",") if part.strip()]
        if not chains or len(chains) > 25 or not all(re.fullmatch(r"[^\d\s]", str(chain)) for chain in chains):
            raise StudioError("target_chains must contain between 1 and 25 single-character structure chain IDs.")
        request["target_chains"] = chains
        sequence_parts = [re.sub(r"\s+", "", part).upper() for part in str(request.get("target_sequence", "")).split(":")]
        if any(not part or not re.fullmatch(r"[ACDEFGHIKLMNPQRSTVWYXBZJUO]+", part) for part in sequence_parts):
            raise StudioError("A valid target_sequence is required for every selected protein chain.")
        if len(sequence_parts) != len(chains):
            raise StudioError("Colon-separated target_sequence parts must match target_chains.")
        request["target_sequence"] = ":".join(sequence_parts)
        if request["sequence_model"] not in {"solublempnn", "proteinmpnn"}:
            raise StudioError(
                "Protein campaigns require SolubleMPNN or ProteinMPNN. Use solublempnn by "
                "default for soluble protein binders; LASErMPNN and LigandMPNN are for "
                "small-molecule interfaces."
            )
        if not request.get("extra_predictors"):
            raise StudioError("Protein campaigns require at least one explicit verification predictor.")
        if expected_mode == "deNovo":
            _reject_protein_denovo_contig(request.get("contig"))
    else:
        source = request.get("ligand_source", "smiles")
        if source == "structure_file":
            artifact = import_artifact(str(request.get("ligand_structure", "")))
            request["ligand_structure"] = artifact["path"]
        elif source != "smiles" or not str(request.get("smiles", "")).strip():
            raise StudioError("A small-molecule request needs a SMILES string or a ligand structure file.")
        component = str(request.get("component_id", "")).strip().upper()
        if not (1 <= len(component) <= 3 and component.isalnum()) or component == "LIG":
            raise StudioError("Use a 1–3 character ligand component code other than LIG.")
        request["component_id"] = component
        if not str(request.get("smiles", "")).strip():
            raise StudioError("A ligand SMILES is required by sequence design and affinity validation even when a structure supplies the pose.")
        if request["sequence_model"] not in {"lasermpnn", "ligandmpnn"}:
            raise StudioError("Small-molecule campaigns require LASErMPNN or LigandMPNN.")
    lengths = request.get("lengths", [65])
    if not isinstance(lengths, list) or not lengths or len(lengths) > 100:
        raise StudioError("lengths must contain between 1 and 100 binder lengths.")
    request["lengths"] = sorted(set(_bounded_int(value, "binder length", 5, 1000) for value in lengths))
    request["num_backbones"] = _bounded_int(request.get("num_backbones", 100), "num_backbones", 1, 100_000)
    request["timesteps"] = _bounded_int(request.get("timesteps", 200), "timesteps", 1, 1000)
    request["recycles"] = _bounded_int(request.get("recycles", 2), "recycles", 0, 20)
    request["batch_size"] = _bounded_int(request.get("batch_size", 4), "batch_size", 1, 64)
    request["queues_per_bin"] = _bounded_int(request.get("queues_per_bin", 2), "queues_per_bin", 1, 4)
    request["sequences_per_backbone"] = _bounded_int(request.get("sequences_per_backbone", 4), "sequences_per_backbone", 1, 1000)
    if expected_mode == "partialDiffusion" and bool(request.get("preserve_partial_sequence", True)):
        request["sequences_per_backbone"] = 1
    request.setdefault("top_n", min(100, request["num_backbones"] * request["sequences_per_backbone"]))
    request["top_n"] = _bounded_int(request["top_n"], "top_n", 1, 100_000)
    if request["top_n"] > request["num_backbones"] * request["sequences_per_backbone"]:
        raise StudioError("top_n exceeds the number of sequences the campaign will create.")
    if request.get("precision", "bf16") not in {"bf16", "fp32"}:
        raise StudioError("precision must be bf16 or fp32.")
    if request.get("sequence_model", "lasermpnn") not in SEQUENCE_MODELS:
        raise StudioError("Unsupported inverse-folding model.")
    extras = request.get("extra_predictors", [])
    if not isinstance(extras, list) or any(value not in PREDICTORS for value in extras):
        raise StudioError("extra_predictors contains an unsupported engine.")
    request["extra_predictors"] = list(dict.fromkeys(extras))
    if sum(value.startswith("protenix-") for value in request["extra_predictors"]) > 1:
        raise StudioError("Choose either Protenix v2 or Mini, not both.")
    allowed_conditions = {"buried", "exposed", "hbondDonor", "hbondAcceptor", "hotspot"}
    conditions = request.get("conditions", {})
    if not isinstance(conditions, dict):
        raise StudioError("conditions must map explicit atom/residue names to condition arrays.")
    for site, values in conditions.items():
        if not isinstance(values, list) or any(value not in allowed_conditions for value in values):
            raise StudioError(f"Condition site {site} contains an unsupported conditioning class.")
    if target_kind == "protein" and expected_mode == "deNovo":
        hotspots = sorted(site for site, values in conditions.items() if "hotspot" in values)
        mode = request.get("binding_site_mode")
        if mode is None:
            if request.get("ori_token") is not None:
                mode = "manual"
            elif hotspots or request.get("infer_ori_strategy") == "hotspots":
                mode = "targeted_epitope"
            elif request.get("infer_ori_strategy") == "com":
                raise StudioError(
                    "Target-centre ORI is unsafe for a fixed protein. Choose surface_scan, "
                    "surface_patch, targeted_epitope, or manual."
                )
            else:
                mode = "surface_scan"
        if mode not in {"surface_scan", "surface_patch", "targeted_epitope", "manual"}:
            raise StudioError(
                "binding_site_mode must be surface_scan, surface_patch, targeted_epitope, or manual."
            )
        patch = request.get("surface_patch_residues", [])
        if not isinstance(patch, list) or any(not isinstance(value, str) for value in patch):
            raise StudioError("surface_patch_residues must be an array of residues such as B42.")
        if mode == "surface_scan":
            if hotspots or patch or request.get("ori_token") is not None:
                raise StudioError(
                    "surface_scan cannot also include hotspots, broad-region residues, or ori_token."
                )
            request.pop("infer_ori_strategy", None)
            request.pop("ori_token", None)
        elif mode == "surface_patch":
            if hotspots:
                raise StudioError(
                    "surface_patch is positioning only. Remove hotspot conditions or choose targeted_epitope."
                )
            if not patch or any(not re.fullmatch(r"[^\d\s]-?\d+", value.strip()) for value in patch):
                raise StudioError("surface_patch requires target residues such as B42.")
            if any(value.strip()[0] not in request["target_chains"] for value in patch):
                raise StudioError("Every broad-region residue must belong to a selected target chain.")
            request["surface_patch_residues"] = sorted(set(value.strip() for value in patch))
            request.pop("infer_ori_strategy", None)
            request.pop("ori_token", None)
        elif mode == "targeted_epitope":
            if not hotspots:
                raise StudioError("targeted_epitope requires at least one explicit hotspot condition.")
            if patch or request.get("ori_token") is not None:
                raise StudioError("targeted_epitope cannot also use broad-region residues or ori_token.")
            request["infer_ori_strategy"] = "hotspots"
            request.pop("ori_token", None)
        else:
            xyz = request.get("ori_token")
            if (not isinstance(xyz, list) or len(xyz) != 3
                    or any(not isinstance(value, (int, float)) or not math.isfinite(value)
                           for value in xyz)):
                raise StudioError("manual placement requires a finite three-number ori_token.")
            if hotspots or patch:
                raise StudioError("manual placement cannot also include hotspots or broad-region residues.")
            request.pop("infer_ori_strategy", None)
        request["binding_site_mode"] = mode
    filters = request.get("hit_filters", {})
    if not isinstance(filters, dict):
        raise StudioError("hit_filters must be an object.")
    for key in ("minimum_iptm", "minimum_ipsae_min", "minimum_binder_plddt"):
        if filters.get(key) is not None:
            filters[key] = _bounded_float(filters[key], key, 0.0, 1.0)
    for key in ("maximum_complex_rmsd", "maximum_binder_rmsd", "maximum_motif_rmsd"):
        if filters.get(key) is not None:
            filters[key] = _bounded_float(filters[key], key, 0.0, 100.0)
    conformers = request.get("conformers", [])
    if not isinstance(conformers, list):
        raise StudioError("conformers must be an array.")
    staged_conformers = []
    for entry in conformers:
        if not isinstance(entry, dict) or not entry.get("path"):
            raise StudioError("Each conformer needs a path, label and positive weight.")
        artifact = import_artifact(str(entry["path"]))
        weight = _bounded_float(entry.get("weight", 1.0), "conformer weight", 0.000001, 1_000_000)
        staged_conformers.append({"path": artifact["path"], "label": str(entry.get("label", Path(artifact["name"]).stem)), "weight": weight})
    request["conformers"] = staged_conformers
    if expected_mode == "partialDiffusion":
        request["partial_t"] = _bounded_float(request.get("partial_t", 2.0), "partial_t (Å)", 0.1, 15.0)
        binder = str(request.get("source_binder_chain", "A")).strip().upper()
        if not re.fullmatch(r"[A-Z]", binder) or binder in request["target_chains"]:
            raise StudioError("Choose one source binder chain that is not a target chain.")
        request["source_binder_chain"] = binder
        request["motif_sites"] = {}
        request.pop("infer_ori_strategy", None)
        request.pop("ori_token", None)
        request.pop("binding_site_mode", None)
        request.pop("surface_patch_residues", None)
    elif expected_mode == "motifScaffolding":
        binder = str(request.get("source_binder_chain", "A")).strip().upper()
        if not re.fullmatch(r"[A-Z]", binder) or binder in request["target_chains"]:
            raise StudioError("Choose one source motif chain that is not a target chain.")
        request["source_binder_chain"] = binder
        sites = request.get("motif_sites")
        if not isinstance(sites, dict) or not sites:
            raise StudioError("Motif scaffolding requires explicit motif_sites.")
        normalized_sites = {}
        for residue, atoms in sites.items():
            residue = str(residue).strip().upper()
            atoms = str(atoms).strip().upper()
            if not re.fullmatch(r"[^\d\s]-?\d+", residue):
                raise StudioError(f"Invalid motif residue: {residue}")
            if not residue.startswith(binder):
                raise StudioError(f"Motif residue {residue} is not on source motif chain {binder}.")
            if not atoms or not re.fullmatch(r"[A-Z0-9',*]+(?:,[A-Z0-9',*]+)*|BKBN|TIP|ALL", atoms):
                raise StudioError(f"Motif residue {residue} needs an explicit non-empty atom selection.")
            normalized_sites[residue] = atoms
        request["motif_sites"] = normalized_sites
        request.pop("partial_t", None)
        request.pop("infer_ori_strategy", None)
        request.pop("ori_token", None)
        request.pop("binding_site_mode", None)
        request.pop("surface_patch_residues", None)
    else:
        request.pop("partial_t", None)
        request["motif_sites"] = {}
    request.update({"rfd3_root": str(root / "rfd3"), "campaign_dir": str(campaign), "design_name": project, "nanohunter_root": str(root), "design_mode": expected_mode})
    prepare = root / "rfd3_scripts" / "prepare_campaign.py"
    scripts = [prepare]
    if target_kind == "small_molecule":
        runner = root / "rfd3" / "scripts" / "run_rfd3_nise_campaign.py"
    else:
        runner = root / "rfd3_scripts" / "rfd3_protein_campaign.py"
    scripts.append(runner)
    preview = [str(root / "rfd3" / ".venv" / "bin" / "python"), str(prepare), str(campaign / "config" / "studio_request.json"), "&&", "/usr/bin/caffeinate", "-dimsu", str(root / "rfd3" / ".venv" / "bin" / "python"), str(runner), "--config", str(campaign / "config" / "campaign.json")]
    generated = request["num_backbones"] * request["sequences_per_backbone"]
    normalized = {
        "request": request,
        "campaign": str(campaign),
        "target_kind": target_kind,
        "operator_guidance": {
            "start_all_candidates": True,
            "ranking_stage": "Rank after independent structure prediction, not from RFD3 backbone scores alone.",
            "binding_site": (
                "Whole-target surface coverage: Studio will calculate outward solvent-surface ORIs and split the exact backbone quota across them."
                if request.get("binding_site_mode") == "surface_scan" else
                "Broad-region placement only: selected residues position the ORI but are not contact hotspots."
                if request.get("binding_site_mode") == "surface_patch" else
                "Targeted epitope: the reviewed residues are real RFdiffusion3 hotspot constraints."
                if request.get("binding_site_mode") == "targeted_epitope" else
                "Manual expert ORI coordinates."
                if request.get("binding_site_mode") == "manual" else
                "Small-molecule or existing-complex placement policy."
            ),
            "smoke_test_recommended": request["num_backbones"] > 10,
            "smoke_test_size": min(5, request["num_backbones"]),
            "candidate_count": generated,
            "next_action": (
                "For a new target/settings combination, first run 1-5 backbones through every requested "
                "stage. Re-plan the full campaign only after that job completes."
                if request["num_backbones"] > 10 else
                "Review this normalized request and then call job_start with both plan identifiers."
            ),
        },
    }
    return _persist(f"rfd3_{expected_mode}", project, normalized, preview, "apple_gpu_exclusive", _script_provenance(scripts))


def admin_plan(arguments: Dict[str, Any], kind: str) -> Dict[str, Any]:
    root = runtime_root()
    setup = root / "setup_pipeline.sh"
    if kind == "engine_install":
        components = arguments.get("components")
        if not isinstance(components, list) or not components or any(value not in INSTALL_COMPONENTS for value in components):
            raise StudioError(f"components must use supported identifiers: {', '.join(sorted(INSTALL_COMPONENTS))}")
        flags = [INSTALL_COMPONENTS[value] for value in dict.fromkeys(components)]
    elif kind == "engine_repair":
        flags = ["--repair-venvs"]
    elif kind == "storage_minimise":
        flags = ["--minimize-storage"]
    else:
        raise StudioError(f"Unknown administration plan kind: {kind}")
    normalized = {"arguments": flags, "root": str(root)}
    preview = ["/usr/bin/caffeinate", "-dimsu", "/bin/bash", str(setup)] + flags
    return _persist(kind, "_admin", normalized, preview, "environment_install", _script_provenance([setup]))


def load_plan(plan_id: str, expected_sha256: str) -> Dict[str, Any]:
    validate_slug(plan_id, "plan ID")
    path = agent_root() / "plans" / f"{plan_id}.json"
    try:
        plan = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise StudioError(f"Unknown or unreadable plan: {plan_id}") from exc
    stored_sha = plan.get("sha256")
    body = {key: value for key, value in plan.items() if key not in {"id", "sha256", "created_at"}}
    actual_sha = canonical_digest(body)
    if stored_sha != actual_sha or expected_sha256 != stored_sha:
        raise StudioError("Plan digest mismatch; re-run preflight instead of executing changed settings.")
    for item in plan.get("provenance", []):
        path = Path(item.get("path", ""))
        if not path.is_file() or file_digest(path) != item.get("sha256"):
            raise StudioError(f"Installed workflow code changed after preflight: {path}. Create a new plan.")
    return plan
