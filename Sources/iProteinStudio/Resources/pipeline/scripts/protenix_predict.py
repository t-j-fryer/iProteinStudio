#!/usr/bin/env python3
"""Run Protenix v2 or Mini from Studio's Boltz-YAML prediction contract.

The adapter is deliberately small: it translates entities and passes exact A3M
paths through to upstream Protenix. Explicit ``msa: empty`` remains a
single-sequence request and can never become an online search. It does not
provide a CPU escape hatch. Both the prediction tab and design pipelines call
this file, keeping their scientific behaviour identical.
"""

from __future__ import annotations

import argparse
import json
import os
import shutil
import subprocess
import sys
from pathlib import Path

import yaml

from ipsae_score import IPSAEError, annotate_protenix


MODEL_NAMES = {
    "v2": "protenix-v2",
    "protenix-v2": "protenix-v2",
    "mini": "protenix_mini_default_v0.5.0",
    "protenix-mini": "protenix_mini_default_v0.5.0",
}


def die(message: str) -> None:
    raise SystemExit(f"Protenix adapter: {message}")


def scalar_id(value, fallback: str) -> str:
    if isinstance(value, list):
        return str(value[0]) if value else fallback
    return str(value or fallback)


def convert_yaml(path: Path) -> tuple[dict, list[dict], bool]:
    try:
        document = yaml.safe_load(path.read_text()) or {}
    except (OSError, yaml.YAMLError) as exc:
        die(f"cannot read {path}: {exc}")

    entities = []
    explicit_empty = []
    has_real_msa = False
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
    return ({"name": path.stem, "sequences": entities, "covalent_bonds": []},
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
    return [
        str(executable), "pred", "-i", str(input_json), "-o", str(output),
        "-s", seeds, "-e", str(samples), "-n", model_name,
        "--use_default_params", "True", "--use_msa", str(use_msa),
        "--use_template", "False", "--use_rna_msa", "False",
        "--trimul_kernel", "torch", "--triatt_kernel", "torch",
        "--enable_cache", "False", "--enable_fusion", "False",
        # Protenix only writes token_pair_pae and token_asym_id when this is
        # enabled. Those are required for a real ipSAE calculation; summary
        # chain-pair PAE minima are not a substitute.
        "--enable_tf32", "False", "--need_atom_confidence", "True",
        "-d", "fp32",
    ]


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
    full_confidences = list(job_dir.rglob("*_full_data_sample_*.json"))
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
        shutil.copyfile(structure, pred_min / "model_0.cif")
        shutil.copyfile(confidence, pred_min / "confidence.json")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    inputs = parser.add_mutually_exclusive_group(required=True)
    inputs.add_argument("--yaml", type=Path)
    inputs.add_argument("--inputs", type=Path)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--nanohunter-root", type=Path, required=True)
    parser.add_argument("--model", choices=sorted(MODEL_NAMES), required=True)
    parser.add_argument("--seeds", default="42", help="comma-separated model seeds")
    parser.add_argument("--samples", type=int, default=5)
    args = parser.parse_args()

    root = args.nanohunter_root.expanduser().resolve()
    model_root = root / "models" / "protenix"
    executable = root / "venvs" / "NanoHunter_protenix" / "bin" / "protenix"
    if not executable.is_file():
        die(f"environment is not installed at {executable.parent.parent}")
    if os.environ.get("PYTORCH_ENABLE_MPS_FALLBACK") == "1":
        die("PYTORCH_ENABLE_MPS_FALLBACK=1 is forbidden; this run must be native MPS")
    if args.samples < 1:
        die("--samples must be at least 1")

    source = args.yaml or args.inputs
    yaml_paths = [source] if source.is_file() else sorted(source.glob("*.yaml"))
    if not yaml_paths:
        die(f"no YAML inputs found at {source}")
    converted = [convert_yaml(path.resolve()) for path in yaml_paths]
    jobs = [item[0] for item in converted]
    names = [job["name"] for job in jobs]
    if len(set(names)) != len(names):
        die("input YAML filenames must be unique")

    output = args.output.expanduser().resolve()
    output.mkdir(parents=True, exist_ok=True)
    materialize_single_sequence_msas(converted, output / "single_sequence_msas")
    input_json = output / "protenix_input.json"
    input_json.write_text(json.dumps(jobs, indent=2) + "\n")

    model_name = MODEL_NAMES[args.model]
    checkpoint = model_root / "checkpoint" / f"{model_name}.pt"
    if not checkpoint.is_file():
        die(f"requested checkpoint is missing: {checkpoint}")

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
                                   args.seeds, args.samples, use_msa)
        completed = subprocess.run(command, cwd=root, env=env)
        if completed.returncode:
            raise SystemExit(completed.returncode)
    try:
        annotate_protenix(output, jobs)
    except (IPSAEError, OSError, ValueError, json.JSONDecodeError) as exc:
        die(f"ipSAE scoring failed: {exc}")
    normalize(output, names, len(seeds) * args.samples)


if __name__ == "__main__":
    main()
