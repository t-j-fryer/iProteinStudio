"""Shared validated prediction adapters. Scientific flags are ported unchanged.

The registry selects adapter families; adapters own engine-specific arguments.
No arbitrary plugin names or downloaded executable entry points are accepted.
"""
import os
from pathlib import Path
from engine_registry import descriptor

def command_for(predictor: str, yaml_path: Path, output: Path, root: Path,
                intellifold_model: str, adapters: Path):
    family = descriptor(predictor).get("command_family")
    env = os.environ.copy()
    if family == "boltz":
        venv = root / "venvs" / "NanoHunter_boltz"
        env.update({"PATH": f"{venv / 'bin'}:{env.get('PATH', '')}", "VIRTUAL_ENV": str(venv),
                    "BOLTZ_CACHE": str(root / "models" / "boltz2"),
                    "NUMBA_CACHE_DIR": str(root / "numba_cache")})
        command = [
            str(venv / "bin" / "python"), str(root / "scripts" / "boltz_mps.py"),
            "predict", str(yaml_path),
            "--out_dir", str(output), "--accelerator", "gpu", "--devices", "1",
            "--num_workers", "0", "--output_format", "mmcif", "--override",
        ]
    elif family == "intellifold":
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

    elif family == "protenix":
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

    elif family == "openfold3":
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


def resident_spec(predictor: str, root: Path, intellifold_model: str,
                  use_msa: bool) -> tuple[Path, dict, dict]:
    """Build the strict resident configuration used by iterative design."""
    env = os.environ.copy()
    env["PYTORCH_ENABLE_MPS_FALLBACK"] = "0"
    engine_args: list[str] = []
    model = "boltz2"
    samples = 1
    if predictor == "boltz":
        venv = root / "venvs" / "NanoHunter_boltz"
        env.update({
            "PATH": f"{venv / 'bin'}:{env.get('PATH', '')}",
            "VIRTUAL_ENV": str(venv),
            "BOLTZ_CACHE": str(root / "models" / "boltz2"),
            "NUMBA_CACHE_DIR": str(root / "numba_cache"),
        })
        engine_args = [
            "--accelerator", "gpu", "--devices", "1", "--num_workers", "0",
            "--output_format", "mmcif",
        ]
    elif predictor == "intellifold":
        venv = root / "venvs" / "NanoHunter_intellifold"
        model = intellifold_model
        env.update({
            "PATH": f"{venv / 'bin'}:{env.get('PATH', '')}",
            "VIRTUAL_ENV": str(venv),
            "KMP_USE_SHM": "0",
            "INTELLIFOLD_CACHE": str(root / "models" / "intellifold"),
            # This limit is the measured IntelliFold optimization. Applying it
            # to Protenix made Protenix slower in the governed comparison.
            "OMP_NUM_THREADS": env.get("NANOHUNTER_INTELLIFOLD_OMP_NUM_THREADS", "1"),
            "VECLIB_MAXIMUM_THREADS": env.get("NANOHUNTER_INTELLIFOLD_VECLIB_MAXIMUM_THREADS", "1"),
        })
        engine_args = [
            "--precision", "no", "--num_workers", "0", "--seed", "42",
            "--num_diffusion_samples", "1", "--model", model,
            "--cache", str(root / "models" / "intellifold"),
        ]
    elif predictor == "protenix-mini":
        venv = root / "venvs" / "NanoHunter_protenix"
        model = "mini"
        samples = 5
        env.update({
            "PATH": f"{venv / 'bin'}:{env.get('PATH', '')}",
            "VIRTUAL_ENV": str(venv),
            "PROTENIX_ROOT_DIR": str(root / "models" / "protenix"),
        })
    else:
        raise RuntimeError(f"no validated resident worker for {predictor}")
    python = venv / "bin" / "python"
    worker = root / "scripts" / "resident_predictor.py"
    if not python.is_file() or not worker.is_file():
        raise RuntimeError(f"resident runtime is incomplete for {predictor}: {python}, {worker}")
    config = {
        "schema": 1, "root": str(root), "engine": predictor, "model": model,
        "seed": "42", "samples": samples, "use_potentials": False,
        "use_msa": use_msa, "owner_pid": os.getpid(), "engine_args": engine_args,
    }
    return python, config, env


