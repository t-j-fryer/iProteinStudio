#!/usr/bin/env python3
"""Fold one Boltz-style YAML with IntelliFold's JAX/MPS backend.

IntelliFold ships two backends. The PyTorch one reads NanoHunter YAML directly
and is what the main runner uses. The JAX/MPS one reuses AlphaFold 3's inference
engine, so it reads **AF3
fold-input JSON** and lives in the AlphaFold 3 environment — which is why there
was no route to it from a YAML-driven pipeline.

This bridges the gap by reusing NanoHunter's own `alphafold3_adapter.py` for
both directions: YAML to AF3 JSON going in, and AF3-style output back to the
`model_0.cif` + confidence contract coming out. No new conversion logic.

The full-v2 JAX weights are upstream's release. The v2-flash route is the
validated NanoHunter conversion and graph patch. They live in separate model
directories and are selected explicitly; a missing selection fails rather than
silently falling back to the other architecture.
"""

from __future__ import annotations

import argparse
import os
import subprocess
import sys
from pathlib import Path


def die(message: str) -> None:
    print(f"error: {message}", file=sys.stderr)
    sys.exit(1)


def token_count(yaml_path: Path) -> int:
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
    parser.add_argument("--model", choices=("v2-flash", "v2"), default="v2-flash")
    args = parser.parse_args()

    root = args.nanohunter_root.resolve()
    venv = root / "venvs" / "NanoHunter_alphafold3"
    python = venv / "bin" / "python"
    cli = venv / "bin" / "intellifold"
    adapter = root / "scripts" / "alphafold3_adapter.py"
    default_dir = root / "models" / (
        "intellifold_jax_flash" if args.model == "v2-flash" else "intellifold_jax_v2"
    )
    model_dir = Path(os.environ.get("INTELLIFOLD_JAX_MODEL_DIR", default_dir))

    for path, what in ((python, "AlphaFold 3 environment"), (cli, "IntelliFold JAX CLI"),
                       (adapter, "AF3 adapter")):
        if not path.exists():
            die(f"{what} not found at {path}")
    expected = ("intellifold_v2_flash.bin.zst"
                if args.model == "v2-flash" else "intellifold_v2.bin.zst")
    if not (model_dir / expected).is_file():
        die(f"IntelliFold {args.model} JAX weights not found in {model_dir}. Run setup with the "
            f"IntelliFold JAX component selected.")

    args.output.mkdir(parents=True, exist_ok=True)
    name = args.yaml.stem
    json_dir = args.output / "input"
    json_dir.mkdir(parents=True, exist_ok=True)
    fold_json = json_dir / f"{name}.json"
    jax_out = args.output / "intellifold_jax"
    pred_min = args.output / "pred_min"
    jax_out.mkdir(parents=True, exist_ok=True)
    pred_min.mkdir(parents=True, exist_ok=True)

    convert = subprocess.run(
        [str(python), str(adapter), "to-json",
         "--in-yaml", str(args.yaml), "--out-json", str(fold_json), "--name", name],
        capture_output=True, text=True)
    if convert.returncode:
        die(f"input conversion failed: {convert.stderr.strip()[:400]}")

    cache = Path(os.environ.get("ALPHAFOLD3_COMPILATION_CACHE_DIR",
                                root / "output" / ".alphafold3_jax_cache"))
    cache.mkdir(parents=True, exist_ok=True)
    buckets = os.environ.get("INTELLIFOLD_JAX_BUCKETS") or choose_bucket(token_count(args.yaml))

    env = dict(os.environ)
    env.update({
        "PATH": f"{venv / 'bin'}:{env.get('PATH', '')}",
        "VIRTUAL_ENV": str(venv),
        # Async dispatch was measured clearly negative on this backend.
        "JAX_MPS_ASYNC_DISPATCH": "0",
    })

    log = args.output / "intellifold_jax.log"
    with log.open("w") as handle:
        command = [str(cli), "predict", str(fold_json)]
        if args.model == "v2-flash":
            command.append("--v2-flash")
        command += [
             "--model-dir", str(model_dir),
             "--output-dir", str(jax_out),
             "--flash", "xla",
             "--",
             "--norun_data_pipeline",
             "--jax_backend=mps",
             f"--buckets={buckets}",
             f"--jax_compilation_cache_dir={cache}"]
        predict = subprocess.run(
            command,
            env=env, stdout=handle, stderr=subprocess.STDOUT)
    if predict.returncode:
        tail = "\n".join(log.read_text(errors="replace").splitlines()[-25:])
        die(f"prediction failed (exit {predict.returncode}):\n{tail}")

    normalise = subprocess.run(
        [str(python), str(adapter), "from-output",
         "--af3-out", str(jax_out), "--pred-min", str(pred_min)],
        capture_output=True, text=True)
    if normalise.returncode:
        die(f"output normalisation failed: {normalise.stderr.strip()[:400]}")

    # Converted JAX CIFs can carry a NUL-padded model identifier; NanoHunter has
    # a repair that fixes the header without touching coordinates.
    repair = root / "scripts" / "repair_intellifold_jax_cifs.py"
    if repair.exists():
        subprocess.run([str(python), str(repair), str(pred_min)],
                       capture_output=True, text=True)

    if not (pred_min / "model_0.cif").exists():
        die("IntelliFold JAX produced no model_0.cif")

    # The adapter is AlphaFold 3's, so it stamps "alphafold3" on the metrics.
    # These predictions come from IntelliFold's weights running on AF3's engine;
    # leaving the label would credit the wrong model in every downstream table.
    import json as _json
    metrics = {}
    try:
        metrics = _json.loads(normalise.stdout.strip() or "{}")
    except Exception:
        metrics = {}
    metrics["predictor"] = "intellifold-jax"
    metrics["model"] = args.model
    conf_path = pred_min / "confidence.json"
    if conf_path.exists():
        try:
            conf = _json.loads(conf_path.read_text())
            conf["predictor"] = "intellifold-jax"
            conf["model"] = args.model
            conf_path.write_text(_json.dumps(conf, indent=2))
        except Exception:
            pass
    print(_json.dumps(metrics))


if __name__ == "__main__":
    main()
