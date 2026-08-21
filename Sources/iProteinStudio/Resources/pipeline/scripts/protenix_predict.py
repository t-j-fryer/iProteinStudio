#!/usr/bin/env python3
"""Run Protenix v2 or Mini from Studio's Boltz-YAML prediction contract.

The adapter is deliberately small: it translates entities and passes exact A3M
paths through to upstream Protenix. It does not search alignments, change model
defaults, or provide a CPU escape hatch. Both the prediction tab and design
pipelines call this file, keeping their scientific behaviour identical.
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


def convert_yaml(path: Path) -> dict:
    try:
        document = yaml.safe_load(path.read_text()) or {}
    except (OSError, yaml.YAMLError) as exc:
        die(f"cannot read {path}: {exc}")

    entities = []
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
            # `empty` is an explicit scientific choice. Omitting the field is
            # Protenix's documented single-sequence input; a real file is
            # passed byte-for-byte as the unpaired alignment.
            if msa and str(msa).lower() not in {"empty", "none", "null"}:
                msa_path = Path(str(msa)).expanduser().resolve()
                if not msa_path.is_file():
                    die(f"MSA for chain {chain_id} does not exist: {msa_path}")
                protein["unpairedMsaPath"] = str(msa_path)
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
    return {"name": path.stem, "sequences": entities, "covalent_bonds": []}


def best_prediction(job_dir: Path) -> tuple[Path, Path]:
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
    if not candidates:
        die(f"no complete Protenix prediction under {job_dir}")
    _score, structure, confidence = max(candidates, key=lambda item: item[0])
    return structure, confidence


def normalize(output: Path, names: list[str]) -> None:
    for name in names:
        source_root = output / name
        structure, confidence = best_prediction(source_root)
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
    jobs = [convert_yaml(path.resolve()) for path in yaml_paths]
    names = [job["name"] for job in jobs]
    if len(set(names)) != len(names):
        die("input YAML filenames must be unique")

    output = args.output.expanduser().resolve()
    output.mkdir(parents=True, exist_ok=True)
    input_json = output / "protenix_input.json"
    input_json.write_text(json.dumps(jobs, indent=2) + "\n")

    model_name = MODEL_NAMES[args.model]
    checkpoint = model_root / "checkpoint" / f"{model_name}.pt"
    if not checkpoint.is_file():
        die(f"requested checkpoint is missing: {checkpoint}")

    env = dict(os.environ)
    env.update({
        "PROTENIX_ROOT_DIR": str(model_root),
        "MPLCONFIGDIR": str(root / "matplotlib_cache"),
    })
    env.pop("PYTORCH_ENABLE_MPS_FALLBACK", None)
    command = [
        str(executable), "pred", "-i", str(input_json), "-o", str(output),
        "-s", args.seeds, "-e", str(args.samples), "-n", model_name,
        "--use_default_params", "True", "--trimul_kernel", "torch",
        "--triatt_kernel", "torch", "--enable_cache", "False",
        "--enable_fusion", "False", "--enable_tf32", "False", "-d", "fp32",
    ]
    completed = subprocess.run(command, cwd=root, env=env)
    if completed.returncode:
        raise SystemExit(completed.returncode)
    normalize(output, names)


if __name__ == "__main__":
    main()
