#!/usr/bin/env python3
"""Run Boltz/IntelliFold YAMLs with bounded process parallelism and metrics."""

from __future__ import annotations

import argparse
import csv
import json
import os
import subprocess
import time
from pathlib import Path


SUPPORTED = {"boltz", "intellifold", "protenix-v2", "protenix-mini", "openfold-3-mlx"}
RETIRED = {"alphafold3", "intellifold-jax"}


def command_for(predictor: str, yaml_path: Path, output: Path, root: Path,
                intellifold_model: str):
    env = os.environ.copy()
    adapters = Path(__file__).resolve().parent
    if predictor == "boltz":
        venv = root / "venvs" / "NanoHunter_boltz"
        env.update({"PATH": f"{venv / 'bin'}:{env.get('PATH', '')}", "VIRTUAL_ENV": str(venv),
                    "BOLTZ_CACHE": str(root / "models" / "boltz2"),
                    "NUMBA_CACHE_DIR": str(root / "numba_cache")})
        command = [
            str(venv / "bin" / "boltz"), "predict", str(yaml_path),
            "--out_dir", str(output), "--accelerator", "gpu", "--devices", "1",
            "--num_workers", "0", "--output_format", "mmcif", "--override",
        ]
    elif predictor == "intellifold":
        venv = root / "venvs" / "NanoHunter_intellifold"
        env.update(
            {
                "PATH": f"{venv / 'bin'}:{env.get('PATH', '')}",
                "VIRTUAL_ENV": str(venv),
                "KMP_USE_SHM": "0",
                "INTELLIFOLD_CACHE": str(root / "models" / "intellifold"),
                # Host BLAS/OpenMP contends with MPS submission. One thread was
                # measured ~1.3x faster with byte-identical structures, and this
                # is IntelliFold-specific: the same setting makes Boltz slower.
                "OMP_NUM_THREADS": env.get("NANOHUNTER_INTELLIFOLD_OMP_NUM_THREADS", "1"),
                "VECLIB_MAXIMUM_THREADS": env.get("NANOHUNTER_INTELLIFOLD_VECLIB_MAXIMUM_THREADS", "1"),
                "PYTORCH_ENABLE_MPS_FALLBACK": "0",
            }
        )
        command = [
            str(venv / "bin" / "python"), str(root / "scripts" / "intellifold_predict.py"),
            str(yaml_path), "--out_dir", str(output), "--precision", "no", "--num_workers", "0",
            "--seed", "42", "--num_diffusion_samples", "1", "--override", "--model", intellifold_model,
            "--cache", str(root / "models" / "intellifold"),
        ]

    elif predictor in ("protenix-v2", "protenix-mini"):
        venv = root / "venvs" / "NanoHunter_protenix"
        env.update({
            "PATH": f"{venv / 'bin'}:{env.get('PATH', '')}",
            "VIRTUAL_ENV": str(venv),
            "PROTENIX_ROOT_DIR": str(root / "models" / "protenix"),
        })
        env.pop("PYTORCH_ENABLE_MPS_FALLBACK", None)
        command = [
            str(venv / "bin" / "python"),
            str(root / "scripts" / "protenix_predict.py"),
            "--yaml", str(yaml_path), "--output", str(output),
            "--nanohunter-root", str(root),
            "--model", "v2" if predictor == "protenix-v2" else "mini",
        ]

    elif predictor in ("openfold-3-mlx", "openfold3", "openfold"):
        venv = root / "venvs" / "NanoHunter_openfold3_mlx"
        env.update({
            "PATH": f"{venv / 'bin'}:{env.get('PATH', '')}",
            "VIRTUAL_ENV": str(venv),
            "KMP_USE_SHM": "0",
        })
        command = [
            str(venv / "bin" / "python"), str(adapters / "openfold_predict_one.py"),
            "--yaml", str(yaml_path), "--output", str(output),
            "--nanohunter-root", str(root),
        ]

    else:
        raise SystemExit(f"unsupported predictor: {predictor}")

    return command, env


def parse_metrics(output: Path) -> dict:
    # Boltz prefixes confidence_ while IntelliFold suffixes
    # _summary_confidences. Prefer summary files over per-atom confidence data.
    confidence_files = sorted(output.rglob("*summary_confidences.json"))
    if not confidence_files:
        confidence_files = sorted(output.rglob("confidence*.json"))
    cifs = sorted(output.rglob("*.cif"))
    metrics: dict = {}
    confidence_path = confidence_files[0] if confidence_files else None
    if confidence_path:
        data = json.loads(confidence_path.read_text())
        for key in (
            "iptm", "ptm", "plddt", "complex_plddt", "confidence_score", "ranking_score",
            "ligand_iptm", "protein_iptm", "has_clash", "complex_iplddt", "complex_ipde",
            "ipsae_min",
        ):
            value = data.get(key)
            if isinstance(value, (int, float)):
                metrics[key] = value
    metrics["confidence_json"] = str(confidence_path) if confidence_path else ""
    metrics["structure"] = str(cifs[0]) if cifs else ""
    return metrics


def ensure_ipsae(predictor: str, yaml_path: Path, output: Path, root: Path,
                  log_path: Path) -> None:
    """Boltz needs a post-run adapter; other engines annotate in their launchers."""
    if predictor != "boltz":
        return
    command = [
        str(root / "venvs" / "NanoHunter_boltz" / "bin" / "python"),
        str(root / "scripts" / "ipsae_score.py"), "boltz",
        "--yaml", str(yaml_path), "--output", str(output),
    ]
    with log_path.open("a") as handle:
        completed = subprocess.run(command, stdout=handle, stderr=subprocess.STDOUT)
    if completed.returncode:
        raise SystemExit(
            f"{predictor} produced a structure but ipSAE scoring failed for {yaml_path}; "
            f"see {log_path}"
        )


def write_csv(rows: list[dict], path: Path) -> None:
    fields = sorted({key for row in rows for key in row})
    with path.open("w", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields)
        writer.writeheader()
        writer.writerows(rows)


def default_root() -> Path:
    """Where venvs/ and src/ live.

    From the environment the app sets, else this checkout's parent -- rfd3 is
    installed inside the pipeline root. Never a hard-coded home directory:
    that is one developer's machine, not the user's.
    """
    env = os.environ.get("NANOHUNTER_ROOT") or os.environ.get("IPROTEIN_ROOT")
    if env:
        return Path(env)
    # Installed layout is <root>/rfd3/scripts/, so the root is two levels up.
    # Verify rather than assume: a standalone checkout has no venvs/ above it,
    # and silently pointing at a home directory would be worse than saying so.
    candidate = Path(__file__).resolve().parents[2]
    if (candidate / "venvs").is_dir():
        return candidate
    raise SystemExit(
        "Cannot locate the pipeline root (no venvs/ found). "
        "Set NANOHUNTER_ROOT, or pass --nanohunter-root explicitly.")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--inputs", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--predictors", default="boltz,intellifold")
    parser.add_argument("--max-parallel", type=int, default=4)
    parser.add_argument("--intellifold-model", choices=("v2-flash", "v2"), default="v2-flash")
    parser.add_argument("--nanohunter-root", type=Path)
    parser.add_argument("--resume", action="store_true")
    args = parser.parse_args()
    args.nanohunter_root = args.nanohunter_root or default_root()
    predictors = [value.strip() for value in args.predictors.split(",") if value.strip()]
    retired = [value for value in predictors if value in RETIRED]
    if retired:
        raise SystemExit(f"retired predictors cannot run: {', '.join(retired)}")
    unknown = [v for v in predictors if v not in SUPPORTED]
    if not predictors or unknown:
        raise SystemExit(f"--predictors must be drawn from {sorted(SUPPORTED)}; got {unknown}")
    if any(value.startswith("protenix-") for value in predictors):
        args.max_parallel = 1
    yamls = sorted(args.inputs.resolve().glob("*.yaml"))
    if not yamls:
        raise SystemExit(f"No YAML inputs in {args.inputs}")

    root = args.nanohunter_root.resolve()
    output = args.output.resolve()
    output.mkdir(parents=True, exist_ok=True)
    previous: dict[tuple[str, str], dict] = {}
    previous_csv = output / "prediction_metrics.csv"
    if previous_csv.exists():
        for row in csv.DictReader(previous_csv.open()):
            previous[(row.get("predictor", ""), row.get("design", ""))] = dict(row)
    rows: list[dict] = []
    queue = []
    for predictor in predictors:
        for yaml_path in yamls:
            job_out = output / predictor / yaml_path.stem
            job_out.mkdir(parents=True, exist_ok=True)
            if args.resume and any(job_out.rglob("*.cif")):
                ensure_ipsae(predictor, yaml_path, job_out, root,
                             job_out / "predict.log")
            cached = parse_metrics(job_out)
            if args.resume and cached["structure"] and cached["confidence_json"]:
                prior = previous.get((predictor, yaml_path.stem), {})
                rows.append({
                    **prior, "design": yaml_path.stem, "predictor": predictor, "exit_code": 0,
                    "wall_sec": prior.get("wall_sec", 0.0), "reused": 1,
                    "input_yaml": str(yaml_path), "output_dir": str(job_out),
                    "log": str(job_out / "predict.log"), **cached,
                })
                continue
            command, env = command_for(
                predictor, yaml_path, job_out, root, args.intellifold_model)
            queue.append((predictor, yaml_path, job_out, command, env))

    running = []
    campaign_start = time.time()
    while queue or running:
        while queue and len(running) < args.max_parallel:
            predictor, yaml_path, job_out, command, env = queue.pop(0)
            log_path = job_out / "predict.log"
            handle = log_path.open("w")
            started = time.time()
            proc = subprocess.Popen(command, cwd=root, env=env, stdout=handle, stderr=subprocess.STDOUT)
            running.append((proc, handle, started, predictor, yaml_path, job_out, log_path, command))
        time.sleep(0.25)
        for job in list(running):
            proc, handle, started, predictor, yaml_path, job_out, log_path, command = job
            if proc.poll() is None:
                continue
            handle.close()
            wall = time.time() - started
            if proc.returncode == 0:
                ensure_ipsae(predictor, yaml_path, job_out, root, log_path)
            rows.append(
                {
                    "design": yaml_path.stem, "predictor": predictor, "exit_code": proc.returncode,
                    "wall_sec": wall, "reused": 0, "input_yaml": str(yaml_path),
                    "output_dir": str(job_out), "log": str(log_path),
                    "command": json.dumps(command), **parse_metrics(job_out),
                }
            )
            write_csv(rows, output / "prediction_metrics.csv")
            print(f"{predictor} {yaml_path.stem}: rc={proc.returncode}, {wall:.1f}s", flush=True)
            running.remove(job)

    campaign_wall = time.time() - campaign_start
    write_csv(rows, output / "prediction_metrics.csv")
    failures = sum(row["exit_code"] != 0 for row in rows)
    manifest = {
        "num_designs": len(yamls), "predictors": predictors, "max_parallel": args.max_parallel,
        "num_jobs": len(rows), "num_failures": failures, "wall_sec": campaign_wall,
        "predictions_per_min": len(rows) / (campaign_wall / 60) if campaign_wall else None,
    }
    (output / "run_manifest.json").write_text(json.dumps(manifest, indent=2) + "\n")
    if failures:
        raise SystemExit(f"{failures} predictor jobs failed; see {output / 'prediction_metrics.csv'}")
    print(f"completed {len(rows)} predictions in {campaign_wall:.1f}s")


if __name__ == "__main__":
    main()
