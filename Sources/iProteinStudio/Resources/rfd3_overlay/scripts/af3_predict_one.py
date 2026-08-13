#!/usr/bin/env python3
"""Fold one Boltz-style YAML with AlphaFold 3, and normalise the output.

AlphaFold 3 cannot read a Boltz YAML and does not write Boltz's output layout,
so this wraps NanoHunter's existing `scripts/alphafold3_adapter.py` — the same
converter the main runner uses — around a single prediction. Reusing that
adapter rather than writing another one keeps a single definition of how a
NanoHunter input becomes AF3 JSON, and of how AF3's confidences map onto the
iPTM/pLDDT fields everything downstream reads.

Driven with `--norun_data_pipeline` and whatever MSAs the YAML already carries,
so none of AF3's ~1 TB of genetic databases are required.

Optimisation settings are not invented here; they are the measured ones:
  * `--buckets` from the actual token count, not a padded default
  * a persistent JAX compilation cache, so a new token shape is compiled once
    for the whole campaign instead of once per design
  * `--jax_backend=mps` with the portable XLA attention implementation, which
    the MPS backend requires
  * async dispatch off
"""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
from pathlib import Path


def die(message: str) -> None:
    print(f"error: {message}", file=sys.stderr)
    sys.exit(1)


def token_count(yaml_path: Path) -> int:
    """Total polymer tokens, for choosing the smallest sufficient bucket.

    Padding a 196-token input up to 512 does avoidable work on every prediction
    of a campaign; this is the single largest measured AlphaFold 3 win.
    """
    try:
        import yaml as pyyaml
        data = pyyaml.safe_load(yaml_path.read_text()) or {}
    except Exception:
        return 0
    total = 0
    for entry in data.get("sequences", []) or []:
        if "protein" in entry:
            total += len("".join(str(entry["protein"].get("sequence", "")).split()))
        elif "ligand" in entry:
            # Ligand atoms are tokenised individually; a rough allowance is
            # enough to pick a bucket, and picking the next one up is safe.
            total += 40
    return total


def choose_bucket(tokens: int) -> str:
    for bucket in (128, 256, 384, 512, 768, 1024, 1536, 2048):
        if tokens <= bucket:
            return str(bucket)
    return "4096"


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--yaml", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--nanohunter-root", type=Path, required=True)
    parser.add_argument("--recycles", type=int,
                        default=int(os.environ.get("ALPHAFOLD3_NUM_RECYCLES", "10")))
    parser.add_argument("--diffusion-samples", type=int,
                        default=int(os.environ.get("ALPHAFOLD3_NUM_DIFFUSION_SAMPLES", "1")))
    args = parser.parse_args()

    root = args.nanohunter_root.resolve()
    venv_python = root / "venvs" / "NanoHunter_alphafold3" / "bin" / "python"
    adapter = root / "scripts" / "alphafold3_adapter.py"
    runner = root / "src" / "alphafold3" / "run_alphafold.py"
    model_dir = Path(os.environ.get("ALPHAFOLD3_MODEL_DIR", root / "models" / "alphafold3"))

    for path, what in ((venv_python, "AlphaFold 3 environment"), (adapter, "AF3 adapter"),
                       (runner, "AF3 runner")):
        if not path.exists():
            die(f"{what} not found at {path}")
    if not (model_dir / "af3.bin").exists():
        die(f"AlphaFold 3 weights not found at {model_dir / 'af3.bin'}. They are governed by "
            f"Google's terms and must be obtained separately.")

    args.output.mkdir(parents=True, exist_ok=True)
    name = args.yaml.stem
    af3_json = args.output / f"{name}.json"
    af3_out = args.output / "af3"
    pred_min = args.output / "pred_min"
    af3_out.mkdir(parents=True, exist_ok=True)
    pred_min.mkdir(parents=True, exist_ok=True)

    convert = subprocess.run(
        [str(venv_python), str(adapter), "to-json",
         "--in-yaml", str(args.yaml), "--out-json", str(af3_json), "--name", name],
        capture_output=True, text=True)
    if convert.returncode:
        die(f"input conversion failed: {convert.stderr.strip()[:400]}")

    cache = Path(os.environ.get("ALPHAFOLD3_COMPILATION_CACHE_DIR",
                                root / "output" / ".alphafold3_jax_cache"))
    cache.mkdir(parents=True, exist_ok=True)
    backend = os.environ.get("ALPHAFOLD3_BACKEND", "mps")
    buckets = os.environ.get("ALPHAFOLD3_BUCKETS") or choose_bucket(token_count(args.yaml))

    log = args.output / "alphafold3.log"
    with log.open("w") as handle:
        predict = subprocess.run(
            [str(venv_python), str(runner),
             f"--json_path={af3_json}",
             f"--output_dir={af3_out}",
             f"--model_dir={model_dir}",
             "--norun_data_pipeline",
             f"--jax_backend={backend}",
             # cpu and mps both need the portable XLA attention implementation.
             f"--flash_attention_implementation={'xla' if backend in ('cpu', 'mps') else 'triton'}",
             f"--num_recycles={args.recycles}",
             f"--num_diffusion_samples={args.diffusion_samples}",
             f"--buckets={buckets}",
             f"--jax_compilation_cache_dir={cache}"],
            cwd=str(root / "src" / "alphafold3"),
            stdout=handle, stderr=subprocess.STDOUT)
    if predict.returncode:
        tail = "\n".join(log.read_text(errors="replace").splitlines()[-20:])
        die(f"prediction failed (exit {predict.returncode}):\n{tail}")

    normalise = subprocess.run(
        [str(venv_python), str(adapter), "from-output",
         "--af3-out", str(af3_out), "--pred-min", str(pred_min)],
        capture_output=True, text=True)
    if normalise.returncode:
        die(f"output normalisation failed: {normalise.stderr.strip()[:400]}")

    if not (pred_min / "model_0.cif").exists():
        die("AlphaFold 3 produced no model_0.cif")
    print(normalise.stdout.strip())


if __name__ == "__main__":
    main()
