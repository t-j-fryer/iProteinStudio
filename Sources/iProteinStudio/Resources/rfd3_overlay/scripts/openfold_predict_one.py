#!/usr/bin/env python3
"""Fold one Boltz-style YAML with OpenFold-3, and normalise the output.

OpenFold-3 takes a query JSON and a runner YAML rather than a Boltz template, and
writes its results under a seed directory rather than as `model_0.cif`. Both
the shared conversions live in `scripts/openfold_query_json.py` and
`scripts/openfold_runner_yaml.py`. This script calls those same helpers, so the
standalone and iterative paths cannot drift.

The runner YAML enables the MLX attention, triangle and activation kernels, which
is what makes OpenFold-3 viable on Apple silicon.
"""

from __future__ import annotations

import argparse
import json
import os
import shutil
import subprocess
import sys
from pathlib import Path


def die(message: str) -> None:
    print(f"error: {message}", file=sys.stderr)
    sys.exit(1)


def binder_sequence(yaml_path: Path) -> str:
    """Chain A's sequence — the designed binder."""
    try:
        import yaml as pyyaml
        data = pyyaml.safe_load(yaml_path.read_text()) or {}
    except Exception as exc:
        die(f"could not read {yaml_path}: {exc}")
    for entry in data.get("sequences", []) or []:
        protein = entry.get("protein") if isinstance(entry, dict) else None
        if protein and str(protein.get("id", "")).strip() == "A":
            return "".join(str(protein.get("sequence", "")).split())
    die("no chain A protein sequence in the template")
    return ""


def chain_msa(yaml_path: Path, chain: str) -> str:
    """A usable MSA path named in the template for one chain, if any."""
    try:
        import yaml as pyyaml
        data = pyyaml.safe_load(yaml_path.read_text()) or {}
    except Exception:
        return ""
    for entry in data.get("sequences", []) or []:
        protein = entry.get("protein") if isinstance(entry, dict) else None
        if not protein or str(protein.get("id", "")).strip() != chain:
            continue
        msa = str(protein.get("msa", "")).strip()
        return "" if msa.lower() in {"", "empty", "none", "null"} else msa
    return ""


def target_msa(yaml_path: Path) -> str:
    """Any real MSA path already named in the template, for the target chain."""
    try:
        import yaml as pyyaml
        data = pyyaml.safe_load(yaml_path.read_text()) or {}
    except Exception:
        return ""
    for entry in data.get("sequences", []) or []:
        protein = entry.get("protein") if isinstance(entry, dict) else None
        if not protein or str(protein.get("id", "")).strip() == "A":
            continue
        msa = str(protein.get("msa", "")).strip()
        if msa and msa.lower() not in {"empty", "none", "null"}:
            return msa
    return ""


def normalize_openfold_msa_paths(query_json: Path, work_dir: Path) -> None:
    """Give raw alignments a basename OpenFold-3 actually parses.

    OpenFold-3 accepts arbitrary A3M/STO *paths* in its query schema, but its
    inference parser then filters raw files by a fixed set of source basenames
    (``colabfold_main``, ``uniref90_hits``, and so on). Studio's shared cache is
    deliberately content-addressed and prior runs use many human-readable
    names, so passing those paths through makes the upstream parser silently
    discard a valid alignment and eventually crash on an empty dictionary.

    Keep the cached source immutable. Each chain receives a private adapter-local
    copy named ``colabfold_main``; the sequence and depth validation has already
    happened in Studio's batch/design pipeline before this adapter is called.
    """
    try:
        payload = json.loads(query_json.read_text())
    except (OSError, json.JSONDecodeError) as exc:
        die(f"could not normalize OpenFold MSA paths: {exc}")

    for query_index, query in enumerate((payload.get("queries") or {}).values()):
        for chain_index, chain in enumerate(query.get("chains") or []):
            paths = chain.get("main_msa_file_paths") or []
            if not paths:
                continue
            if len(paths) != 1:
                die("OpenFold adapter expected one main MSA per chain, "
                    f"but received {len(paths)}")
            source = Path(paths[0]).expanduser()
            if not source.exists():
                die(f"OpenFold MSA does not exist: {source}")
            if source.is_dir() or source.suffix.lower() == ".npz":
                continue
            suffix = source.suffix.lower()
            if suffix not in {".a3m", ".sto"}:
                die(f"OpenFold does not support MSA file type {source.suffix}: {source}")
            chain_dir = work_dir / f"query_{query_index}" / f"chain_{chain_index}"
            chain_dir.mkdir(parents=True, exist_ok=True)
            normalized = chain_dir / f"colabfold_main{suffix}"
            shutil.copyfile(source, normalized)
            chain["main_msa_file_paths"] = [str(normalized)]

    query_json.write_text(json.dumps(payload, indent=2) + "\n")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--yaml", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--nanohunter-root", type=Path, required=True)
    parser.add_argument("--cpu", action="store_true")
    parser.add_argument("--seed", type=int, default=42)
    parser.add_argument("--num-seeds", type=int, default=1)
    parser.add_argument("--diffusion-samples", type=int, default=1)
    args = parser.parse_args()
    if args.num_seeds < 1 or args.diffusion_samples < 1:
        die("num-seeds and diffusion-samples must both be positive")

    root = args.nanohunter_root.resolve()
    venv = root / "venvs" / "NanoHunter_openfold3_mlx"
    cli = venv / "bin" / "run_openfold"
    query_builder = root / "scripts" / "openfold_query_json.py"
    yaml_builder = root / "scripts" / "openfold_runner_yaml.py"
    cache_dir = Path(os.environ.get("OPENFOLD_CACHE", root / "models" / "openfold3"))
    checkpoint = Path(os.environ.get("OPENFOLD_CHECKPOINT_PATH", cache_dir / "of3_ft3_v1.pt"))

    for path, what in ((cli, "OpenFold CLI"), (query_builder, "OpenFold query builder"),
                       (yaml_builder, "OpenFold runner-YAML builder"),
                       (checkpoint, "OpenFold checkpoint")):
        if not path.exists():
            die(f"{what} not found at {path}")

    args.output.mkdir(parents=True, exist_ok=True)
    name = args.yaml.stem
    query_json = args.output / f"{name}_query.json"
    runner_yaml = args.output / f"{name}_runner.yml"
    of_out = args.output / "openfold3"
    pred_min = args.output / "pred_min"
    of_out.mkdir(parents=True, exist_ok=True)
    pred_min.mkdir(parents=True, exist_ok=True)

    build = subprocess.run(
        # The binder's own MSA must be passed too. Omitting it makes the builder
        # fall back to the MSA server for chain A, which is both slow and wrong
        # for a de-novo binder -- and fails outright when the server is down.
        [sys.executable, str(query_builder), str(args.yaml), binder_sequence(args.yaml),
         name, str(query_json), target_msa(args.yaml), chain_msa(args.yaml, "A"),
         str(args.seed)],
        capture_output=True, text=True)
    if build.returncode:
        die(f"query JSON build failed: {build.stderr.strip()[:400]}")
    normalize_openfold_msa_paths(query_json, args.output / "_openfold_msas")
    # The builder prints "true" when a chain still has no MSA and the server is
    # needed. Passing that straight through preserves the runner's behaviour.
    use_server = build.stdout.strip() or "false"

    yaml_cmd = [sys.executable, str(yaml_builder), str(runner_yaml)]
    if args.cpu:
        yaml_cmd.append("--cpu")
    if subprocess.run(yaml_cmd).returncode:
        die("runner YAML build failed")

    env = dict(os.environ)
    env.update({
        "PATH": f"{venv / 'bin'}:{env.get('PATH', '')}",
        "VIRTUAL_ENV": str(venv),
        "OPENFOLD_CACHE": str(cache_dir),
        "KMP_USE_SHM": "0",
    })

    log = args.output / "openfold3.log"
    with log.open("w") as handle:
        predict = subprocess.run(
            [str(cli), "predict",
             "--query_json", str(query_json),
             "--output_dir", str(of_out),
             "--inference_ckpt_path", str(checkpoint),
             "--runner_yaml", str(runner_yaml),
             "--use_msa_server", use_server,
             "--num_diffusion_samples", str(args.diffusion_samples),
             "--num_model_seeds", str(args.num_seeds)],
            env=env, stdout=handle, stderr=subprocess.STDOUT)
    if predict.returncode:
        tail = "\n".join(log.read_text(errors="replace").splitlines()[-20:])
        die(f"prediction failed (exit {predict.returncode}):\n{tail}")

    # OpenFold writes under <query>/seed_NN; normalise to the model_0 contract
    # every other backend satisfies.
    leaf = of_out / name / "seed_42"
    if not leaf.is_dir():
        candidates = sorted(p for p in of_out.rglob("seed_*") if p.is_dir())
        if not candidates:
            die(f"no seed output directory under {of_out}")
        leaf = candidates[0]

    confidences = sorted(leaf.glob("*_confidences_aggregated.json"))
    structures = sorted(list(leaf.glob("*_model.cif")) + list(leaf.glob("*_model.pdb")))
    if not structures:
        die(f"no structure written in {leaf}")

    if confidences:
        shutil.copyfile(confidences[0], pred_min / "confidence.json")
    structure = structures[0]
    shutil.copyfile(structure, pred_min / ("model_0.cif" if structure.suffix == ".cif" else "model_0.pdb"))

    iptm = plddt = None
    if (pred_min / "confidence.json").exists():
        try:
            data = json.loads((pred_min / "confidence.json").read_text())
            iptm = data.get("iptm")
            plddt = data.get("complex_plddt", data.get("plddt"))
        except Exception:
            pass
    print(json.dumps({"structure": str(structure), "iptm": iptm, "plddt": plddt}))


if __name__ == "__main__":
    main()
