#!/usr/bin/env python3
"""Run a declared Protenix profile from Studio's prediction contract.

The adapter is deliberately small: it translates entities and passes exact A3M
paths through to upstream Protenix. Explicit ``msa: empty`` remains a
single-sequence request and can never become an online search. It does not
provide a CPU escape hatch. Both the prediction tab and design pipelines call
this file, keeping their scientific behaviour identical.
"""

from __future__ import annotations

import argparse
import hashlib
import importlib.metadata
import json
import math
import os
import re
import shutil
import subprocess
import sys
from pathlib import Path

import yaml

from ipsae_score import IPSAEError, annotate_protenix
from storage_policy import (compact_detailed_confidence, json_variants,
                            relative_symlink)


MODEL_NAMES = {
    "v2": "protenix-v2",
    "protenix-v2": "protenix-v2",
    "mini": "protenix_mini_default_v0.5.0",
    "protenix-mini": "protenix_mini_default_v0.5.0",
    "constraint": "protenix_base_constraint_v0.5.0",
    "protenix-constraint-v0.5": "protenix_base_constraint_v0.5.0",
}

CONSTRAINT_MODEL = "protenix_base_constraint_v0.5.0"
CONSTRAINT_SHA256 = "5358025b20b2212853ad75579be04387859557915f398a1d60f6a1a9a0c8c887"
CONSTRAINT_SIZE = 1_475_206_741
REQUIRED_CONSTRAINT_LOG_MARKERS = (
    "Using Apple Metal Performance Shaders (MPS).",
    "Enforcing FP32 and native PyTorch kernels for Apple MPS compatibility.",
    "Checkpoint strict load succeeded with no incompatible keys.",
    "succeeded. Model forward time:",
)
FORBIDDEN_CONSTRAINT_LOG_MARKERS = (
    "ESM language model device:", "Precompute ESM embeddings", "CPU fallback",
)


def die(message: str) -> None:
    raise SystemExit(f"Protenix adapter: {message}")


def scalar_id(value, fallback: str) -> str:
    if isinstance(value, list):
        return str(value[0]) if value else fallback
    return str(value or fallback)


def _pocket_residues(document: dict, proteins: dict[str, tuple[int, int]]) -> tuple[list[dict], float]:
    metadata = document.get("nanohunter") or {}
    raw_tokens = metadata.get("target_epitope_residues") or []
    if isinstance(raw_tokens, str):
        raw_tokens = re.split(r"[,;\s]+", raw_tokens.strip())
    if not isinstance(raw_tokens, list):
        die("nanohunter.target_epitope_residues must be a list")
    residues, seen = [], set()
    for raw in raw_tokens:
        match = re.fullmatch(r"([A-Za-z])(?::)?([1-9][0-9]*)", str(raw).strip())
        if not match:
            die(f"invalid epitope residue {raw!r}; use a chain and one-based position such as B32")
        chain, position = match.group(1).upper(), int(match.group(2))
        if chain == "A":
            die("epitope residues must belong to the target, not binder chain A")
        if chain not in proteins:
            die(f"epitope residue {chain}{position} names a missing or non-protein chain")
        entity, length = proteins[chain]
        if position > length:
            die(f"epitope residue {chain}{position} exceeds chain length {length}")
        key = (entity, position)
        if key not in seen:
            residues.append({"entity": entity, "copy": 1, "position": position})
            seen.add(key)
    try:
        distance = float(metadata.get("protenix_pocket_max_distance", 8.0))
    except (TypeError, ValueError):
        die("protenix_pocket_max_distance must be a number")
    if not math.isfinite(distance) or distance <= 0:
        die("protenix_pocket_max_distance must be finite and positive")
    return residues, distance


def convert_yaml(path: Path, constraint_model: bool = False) -> tuple[dict, list[dict], bool]:
    try:
        document = yaml.safe_load(path.read_text()) or {}
    except (OSError, yaml.YAMLError) as exc:
        die(f"cannot read {path}: {exc}")

    entities = []
    explicit_empty = []
    has_real_msa = False
    proteins: dict[str, tuple[int, int]] = {}
    for index, wrapped in enumerate(document.get("sequences") or []):
        if not isinstance(wrapped, dict) or len(wrapped) != 1:
            die(f"{path} contains an unsupported sequence entry")
        kind, raw = next(iter(wrapped.items()))
        raw = raw or {}
        chain_id = scalar_id(raw.get("id"), chr(ord("A") + index))
        if kind == "protein":
            protein = {
                "sequence": "".join(str(raw.get("sequence", "")).split()).upper(),
                "count": 1,
                "id": [chain_id],
            }
            if not protein["sequence"]:
                die(f"protein {chain_id} in {path} has no sequence")
            msa = raw.get("msa")
            # `empty` is an explicit scientific choice. Keep a reference to the
            # converted chain so mixed jobs can receive a query-only A3M later;
            # otherwise Protenix interprets the missing path as permission to
            # contact its MSA server.
            if msa and str(msa).lower() not in {"empty", "none", "null"}:
                msa_path = Path(str(msa)).expanduser().resolve()
                if not msa_path.is_file():
                    die(f"MSA for chain {chain_id} does not exist: {msa_path}")
                protein["unpairedMsaPath"] = str(msa_path)
                has_real_msa = True
            else:
                explicit_empty.append(protein)
            entities.append({"proteinChain": protein})
            proteins[chain_id.upper()] = (len(entities), len(protein["sequence"]))
        elif kind == "ligand":
            value = raw.get("smiles")
            if not value and raw.get("ccd"):
                value = str(raw["ccd"])
                if not value.startswith("CCD_"):
                    value = "CCD_" + value
            if not value:
                die(f"ligand {chain_id} in {path} has neither SMILES nor CCD")
            entities.append({"ligand": {"ligand": str(value), "count": 1, "id": [chain_id]}})
        elif kind == "dna":
            entities.append({"dnaSequence": {
                "sequence": "".join(str(raw.get("sequence", "")).split()).upper(),
                "count": 1, "id": [chain_id],
            }})
        elif kind == "rna":
            rna = {"sequence": "".join(str(raw.get("sequence", "")).split()).upper(),
                   "count": 1, "id": [chain_id]}
            msa = raw.get("msa")
            if msa and str(msa).lower() not in {"empty", "none", "null"}:
                msa_path = Path(str(msa)).expanduser().resolve()
                if not msa_path.is_file():
                    die(f"RNA MSA for chain {chain_id} does not exist: {msa_path}")
                rna["unpairedMsaPath"] = str(msa_path)
            entities.append({"rnaSequence": rna})
        else:
            die(f"unsupported entity type {kind!r} in {path}")

    if not entities:
        die(f"{path} contains no sequences")
    job = {"name": path.stem, "sequences": entities, "covalent_bonds": []}
    residues, max_distance = _pocket_residues(document, proteins)
    if residues and not constraint_model:
        # Boltz consumes the metadata directly; ordinary Protenix models do not.
        # The runner normally strips it before post-checks, so reaching this
        # branch means a caller tried to apply an unsupported restraint.
        die("epitope pocket metadata requires the Protenix Constraint model")
    if constraint_model:
        binder = proteins.get("A")
        if binder is None or binder[0] != 1:
            die("Protenix Constraint requires protein binder chain A as entity 1")
        if residues:
            job["constraint"] = {"pocket": {
                "binder_chain": {"entity": 1, "copy": 1},
                "contact_residues": residues,
                "max_distance": max_distance,
            }}
    return (job,
            explicit_empty, has_real_msa)


def materialize_single_sequence_msas(converted: list[tuple[dict, list[dict], bool]],
                                     msa_dir: Path) -> None:
    """Represent explicit-empty chains without giving Protenix search permission.

    Protenix exposes MSA use as one process-wide switch. A job containing both a
    real target alignment and an explicit-empty binder therefore needs a real
    query-only A3M for the binder: this keeps MSA features for the target while
    making ``need_msa_search`` false for every chain.
    """
    msa_dir.mkdir(parents=True, exist_ok=True)
    for job, empty_chains, has_real_msa in converted:
        if not has_real_msa:
            continue
        for index, protein in enumerate(empty_chains):
            path = msa_dir / f"{job['name']}_{index}.a3m"
            path.write_text(f">query\n{protein['sequence']}\n")
            protein["unpairedMsaPath"] = str(path.resolve())


def protenix_command(executable: Path, input_json: Path, output: Path,
                     model_name: str, seeds: str, samples: int,
                     use_msa: bool) -> list[str]:
    command = [
        str(executable), "pred", "-i", str(input_json), "-o", str(output),
        "-s", seeds, "-e", str(samples), "-n", model_name,
        "--use_default_params", "False" if model_name == CONSTRAINT_MODEL else "True",
        "--use_msa", str(use_msa),
        "--use_template", "False", "--use_rna_msa", "False",
        "--trimul_kernel", "torch", "--triatt_kernel", "torch",
        "--enable_cache", "False", "--enable_fusion", "False",
        # Protenix only writes token_pair_pae and token_asym_id when this is
        # enabled. Those are required for a real ipSAE calculation; summary
        # chain-pair PAE minima are not a substitute.
        "--enable_tf32", "False", "--need_atom_confidence", "True",
        "-d", "fp32",
    ]
    if model_name == CONSTRAINT_MODEL:
        command.extend(["-c", "10", "-p", "200", "--use_tfg_guidance", "False"])
    return command


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(8 * 1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def audit_constraint_runtime(executable: Path, checkpoint: Path, receipt: Path) -> None:
    if checkpoint.stat().st_size != CONSTRAINT_SIZE or sha256(checkpoint) != CONSTRAINT_SHA256:
        die("constraint checkpoint does not match the validated official v0.5 release")
    if not receipt.is_file():
        die("constraint install receipt is missing; repair this engine in Setup")
    try:
        installed = json.loads(receipt.read_text())
    except (OSError, json.JSONDecodeError):
        die("constraint install receipt is invalid; repair this engine in Setup")
    if installed.get("zero_substructure") != "checkpoint-equivalent-single-token-broadcast":
        die("constraint engine needs the pocket-only memory update; repair it in Setup")
    try:
        importlib.metadata.version("fair-esm")
    except importlib.metadata.PackageNotFoundError:
        pass
    else:
        die("fair-esm is installed in the constraint-only environment")
    # This adapter is launched by the constraint venv. Prove native Metal and
    # reserve the empirically validated headroom before loading 368M parameters.
    import torch
    if not torch.backends.mps.is_available():
        die("Apple MPS is unavailable; CPU execution is not offered")
    if hasattr(torch.mps, "driver_allocated_memory") and hasattr(torch.mps, "recommended_max_memory"):
        headroom = torch.mps.recommended_max_memory() - torch.mps.driver_allocated_memory()
        if headroom < 8 * 1024**3:
            die(f"constraint inference needs at least 8 GiB free Apple-GPU headroom; observed {headroom / 1024**3:.1f} GiB")


def complete_predictions(job_dir: Path) -> list[tuple[float, Path, Path]]:
    candidates = []
    for confidence in job_dir.rglob("*_summary_confidence_sample_*.json"):
        try:
            data = json.loads(confidence.read_text())
        except (OSError, json.JSONDecodeError):
            continue
        suffix = confidence.name.split("_summary_confidence_sample_", 1)[1].removesuffix(".json")
        structures = list(confidence.parent.glob(f"*_sample_{suffix}.cif"))
        if structures:
            candidates.append((float(data.get("ranking_score", float("-inf"))),
                               structures[0], confidence))
    return candidates


def best_prediction(job_dir: Path, expected: int) -> tuple[Path, Path]:
    candidates = complete_predictions(job_dir)
    structures = list(job_dir.rglob("*_sample_*.cif"))
    confidences = list(job_dir.rglob("*_summary_confidence_sample_*.json"))
    full_confidences = json_variants(job_dir, "*_full_data_sample_*.json")
    if (len(candidates) != expected or len(structures) != expected
            or len(confidences) != expected or len(full_confidences) != expected):
        die(f"expected exactly {expected} complete prediction(s) under {job_dir}; "
            f"found {len(structures)} structure(s), {len(confidences)} summary file(s), "
            f"{len(full_confidences)} full-confidence file(s), and "
            f"{len(candidates)} matched structure/summary pair(s)")
    _score, structure, confidence = max(candidates, key=lambda item: item[0])
    return structure, confidence


def normalize(output: Path, names: list[str], expected: int) -> None:
    for name in names:
        source_root = output / name
        structure, confidence = best_prediction(source_root, expected)
        pred_min = source_root / "pred_min"
        pred_min.mkdir(parents=True, exist_ok=True)
        relative_symlink(structure, pred_min / "model_0.cif", replace=True)
        relative_symlink(confidence, pred_min / "confidence.json", replace=True)


def annotate_constraint_geometry(output: Path, jobs: list[dict]) -> None:
    """Record observed pocket geometry without treating it as binding proof."""
    import numpy as np
    from biotite.structure.io.pdbx import CIFFile, get_structure

    for job in jobs:
        pocket = (job.get("constraint") or {}).get("pocket")
        if not pocket:
            continue
        pred_min = output / job["name"] / "pred_min"
        structure = pred_min / "model_0.cif"
        confidence_path = pred_min / "confidence.json"
        atoms = get_structure(CIFFile.read(structure), model=1)
        if len(atoms) == 0 or not np.isfinite(atoms.coord).all():
            die(f"constraint result has invalid coordinates: {structure}")
        entity_ids = []
        for wrapped in job["sequences"]:
            raw = next(iter(wrapped.values()))
            ids = raw.get("id") or []
            entity_ids.append(str(ids[0]) if ids else "")
        binder_chain = entity_ids[int(pocket["binder_chain"]["entity"]) - 1]
        binder_mask = (atoms.chain_id == binder_chain) & (atoms.atom_name == "CA")
        binder_ca = atoms.coord[binder_mask].astype(float)
        if len(binder_ca) == 0:
            die(f"constraint result has no binder CA atoms on chain {binder_chain}")
        distances = []
        for residue in pocket["contact_residues"]:
            chain = entity_ids[int(residue["entity"]) - 1]
            mask = ((atoms.chain_id == chain) & (atoms.atom_name == "CA")
                    & (atoms.res_id == int(residue["position"])))
            coords = atoms.coord[mask]
            if len(coords) != 1:
                die(f"expected one CA for pocket residue {chain}{residue['position']}; found {len(coords)}")
            distances.append(float(np.linalg.norm(binder_ca - coords[0], axis=1).min()))
        cutoff = float(pocket["max_distance"])
        metrics = {
            "constraint_kind": "protenix_v0.5_pocket",
            "constraint_pocket_distance_semantics": "mean nearest binder-to-target CA distance",
            "constraint_pocket_max_distance": cutoff,
            "constraint_pocket_residue_count": len(distances),
            "constraint_pocket_mean_min_ca_distance": float(np.mean(distances)),
            "constraint_pocket_max_min_ca_distance": float(np.max(distances)),
            "constraint_pocket_fraction_within_max_distance": float(np.mean(np.asarray(distances) <= cutoff)),
            "constraint_pocket_per_residue_min_ca_distances": distances,
        }
        confidence = json.loads(confidence_path.read_text())
        confidence.update(metrics)
        confidence_path.write_text(json.dumps(confidence, indent=2) + "\n")
        (pred_min / "constraint_satisfaction.json").write_text(json.dumps(metrics, indent=2) + "\n")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    inputs = parser.add_mutually_exclusive_group(required=True)
    inputs.add_argument("--yaml", type=Path)
    inputs.add_argument("--inputs", type=Path)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--nanohunter-root", type=Path, required=True)
    parser.add_argument("--model", choices=sorted(MODEL_NAMES), required=True)
    parser.add_argument("--seeds", default="42", help="comma-separated model seeds")
    parser.add_argument("--samples", type=int)
    args = parser.parse_args()

    root = args.nanohunter_root.expanduser().resolve()
    model_name = MODEL_NAMES[args.model]
    constraint_model = model_name == CONSTRAINT_MODEL
    profile = "protenix_constraint" if constraint_model else "protenix"
    model_root = root / "models" / profile
    executable = root / "venvs" / f"NanoHunter_{profile}" / "bin" / "protenix"
    if not executable.is_file():
        die(f"environment is not installed at {executable.parent.parent}")
    if os.environ.get("PYTORCH_ENABLE_MPS_FALLBACK") == "1":
        die("PYTORCH_ENABLE_MPS_FALLBACK=1 is forbidden; this run must be native MPS")
    samples = args.samples if args.samples is not None else (1 if constraint_model else 5)
    if samples < 1:
        die("--samples must be at least 1")

    source = args.yaml or args.inputs
    yaml_paths = [source] if source.is_file() else sorted(source.glob("*.yaml"))
    if not yaml_paths:
        die(f"no YAML inputs found at {source}")
    converted = [convert_yaml(path.resolve(), constraint_model) for path in yaml_paths]
    jobs = [item[0] for item in converted]
    names = [job["name"] for job in jobs]
    if len(set(names)) != len(names):
        die("input YAML filenames must be unique")

    output = args.output.expanduser().resolve()
    output.mkdir(parents=True, exist_ok=True)
    materialize_single_sequence_msas(converted, output / "single_sequence_msas")
    input_json = output / "protenix_input.json"
    input_json.write_text(json.dumps(jobs, indent=2) + "\n")

    checkpoint = model_root / "checkpoint" / f"{model_name}.pt"
    if not checkpoint.is_file():
        die(f"requested checkpoint is missing: {checkpoint}")
    if constraint_model:
        audit_constraint_runtime(executable, checkpoint, model_root / "install_receipt.json")
        shutil.copyfile(model_root / "install_receipt.json", output / "install_receipt.json")

    try:
        seeds = [int(value) for value in args.seeds.split(",") if value.strip()]
    except ValueError:
        die("--seeds must be a comma-separated list of integers")
    if not seeds:
        die("--seeds must contain at least one integer")

    env = dict(os.environ)
    env.update({
        "PROTENIX_ROOT_DIR": str(model_root),
        "MPLCONFIGDIR": str(root / "matplotlib_cache"),
    })
    env.pop("PYTORCH_ENABLE_MPS_FALLBACK", None)
    # Protenix's use_msa switch is process-wide. Keep fully single-sequence jobs
    # separate from jobs that contain a real MSA so neither policy can override
    # the other inside a directory batch.
    groups = [(False, [item[0] for item in converted if not item[2]]),
              (True, [item[0] for item in converted if item[2]])]
    populated = [(use_msa, group) for use_msa, group in groups if group]
    for use_msa, group in populated:
        group_input = input_json
        if len(populated) > 1:
            suffix = "with_msa" if use_msa else "single_sequence"
            group_input = output / f"protenix_input_{suffix}.json"
            group_input.write_text(json.dumps(group, indent=2) + "\n")
        command = protenix_command(executable, group_input, output, model_name,
                                   args.seeds, samples, use_msa)
        completed = subprocess.run(command, cwd=root, env=env, text=True,
                                   stdout=subprocess.PIPE if constraint_model else None,
                                   stderr=subprocess.STDOUT if constraint_model else None)
        if constraint_model:
            log = completed.stdout or ""
            print(log, end="")
            missing = [item for item in REQUIRED_CONSTRAINT_LOG_MARKERS if item not in log]
            forbidden = [item for item in FORBIDDEN_CONSTRAINT_LOG_MARKERS if item in log]
            expected_pockets = [len((job.get("constraint") or {}).get("pocket", {}).get("contact_residues", [])) for job in group]
            loaded = [int(value) for value in re.findall(r"Loaded constraint feature: #atom contact:\d+ #contact:\d+ #pocket:(\d+)", log)]
            if missing or forbidden or sorted(expected_pockets) != sorted(loaded):
                die(f"constraint runtime proof failed: missing={missing}, forbidden={forbidden}, loaded_pockets={loaded}")
        if completed.returncode:
            raise SystemExit(completed.returncode)
    try:
        annotate_protenix(output, jobs)
    except (IPSAEError, OSError, ValueError, json.JSONDecodeError) as exc:
        die(f"ipSAE scoring failed: {exc}")
    normalize(output, names, len(seeds) * samples)
    if constraint_model:
        annotate_constraint_geometry(output, jobs)
    receipt = compact_detailed_confidence(output)
    if receipt["failures"]:
        print("WARNING: Protenix detailed-confidence compaction retained the original "
              f"for {len(receipt['failures'])} file(s).", file=sys.stderr)


if __name__ == "__main__":
    main()
