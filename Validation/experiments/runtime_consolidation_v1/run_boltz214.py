#!/usr/bin/env python3
"""Build and test an isolated Boltz 2.2.1 / PyTorch 2.14 environment."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
import platform
import re
import shutil
import statistics
import subprocess
import sys
import time


ROOT = Path(__file__).resolve().parents[3]
DEFAULT_OUTPUT = ROOT / "Validation/output/runtime_consolidation_v1/boltz214"
DEFAULT_UV = Path.home() / ".local/bin/uv"
DEFAULT_PYTHON = Path.home() / ".local/bin/python3.11"
CURRENT_PYTHON = Path.home() / ".iproteinstudio/venvs/NanoHunter_boltz/bin/python"
CURRENT_CACHE = Path.home() / ".iproteinstudio/models/boltz2"
LOCK = ROOT / "Sources/iProteinStudio/Resources/pipeline/locks/boltz.txt"
LAUNCHER = Path(__file__).with_name("boltz_no_reset.py")
VALIDATOR = ROOT / "Sources/iProteinStudio/Resources/pipeline/scripts/validate_prediction_geometry.py"
SCHEDULE = ("control", "candidate", "candidate", "control", "control", "candidate")
TORCH_214_CP311_MACOS_ARM64_SHA256 = (
    "1040f689e560ba6e02a0a147dfb9ec8dfdd3e4486ebec4b24dc8fdaa258fa9ba"
)
TORCH_214_CP311_MACOS_ARM64_URL = (
    "https://download.pytorch.org/whl/test/cpu/"
    "torch-2.14.0-cp311-cp311-macosx_14_0_arm64.whl"
    f"#sha256={TORCH_214_CP311_MACOS_ARM64_SHA256}"
)
sys.path.insert(0, str(ROOT))
from Validation.experiments.boltz_mps_allocator_v1.run import (  # noqa: E402
    aligned_rmsd,
    ca_coordinates,
)


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def run(command: list[str], *, env: dict[str, str] | None = None, log: Path | None = None) -> None:
    print("+ " + " ".join(command), flush=True)
    if log is None:
        completed = subprocess.run(command, env=env, text=True)
    else:
        with log.open("w") as handle:
            completed = subprocess.run(
                command, env=env, stdout=handle, stderr=subprocess.STDOUT, text=True
            )
    if completed.returncode:
        suffix = f"; see {log}" if log else ""
        raise SystemExit(f"command failed ({completed.returncode}){suffix}")


def capture(command: list[str], *, env: dict[str, str] | None = None) -> str:
    return subprocess.run(
        command, env=env, check=True, text=True, capture_output=True
    ).stdout.strip()


def atomic_json(path: Path, value: object) -> None:
    temporary = path.with_suffix(path.suffix + ".part")
    temporary.write_text(json.dumps(value, indent=2, sort_keys=True) + "\n")
    temporary.replace(path)


def assert_safe_output(path: Path) -> None:
    resolved = path.resolve()
    allowed = (ROOT / "Validation/output").resolve()
    if resolved == allowed or allowed not in resolved.parents:
        raise SystemExit(f"output must be a child of {allowed}: {resolved}")
    production = (Path.home() / ".iproteinstudio").resolve()
    if resolved == production or production in resolved.parents:
        raise SystemExit("refusing to create an experiment inside the production runtime")


def freeze(uv: Path, python: Path, environment: dict[str, str]) -> list[str]:
    text = capture([str(uv), "pip", "freeze", "--python", str(python)], env=environment)
    return sorted(line for line in text.splitlines() if line.strip())


def package_map(lines: list[str]) -> dict[str, str]:
    result: dict[str, str] = {}
    for line in lines:
        match = re.match(r"^([A-Za-z0-9_.-]+)==(.+)$", line)
        if match:
            result[re.sub(r"[-_.]+", "-", match.group(1)).lower()] = match.group(2)
    return result


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--input-yaml", type=Path, required=True)
    parser.add_argument("--msa", type=Path, required=True)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument("--uv", type=Path, default=DEFAULT_UV)
    parser.add_argument("--python", type=Path, default=DEFAULT_PYTHON)
    parser.add_argument(
        "--torch-wheel-url", default=TORCH_214_CP311_MACOS_ARM64_URL
    )
    arguments = parser.parse_args()

    output = arguments.output.resolve()
    assert_safe_output(output)
    if output.exists():
        raise SystemExit(f"refusing to alter existing experiment output: {output}")
    for required in (
        arguments.input_yaml, arguments.msa, arguments.uv, arguments.python,
        CURRENT_PYTHON, LOCK, LAUNCHER, VALIDATOR,
        CURRENT_CACHE / "boltz2_conf.ckpt", CURRENT_CACHE / "mols",
    ):
        if not required.exists():
            raise SystemExit(f"required input is missing: {required}")

    inputs = output / "input"
    inputs.mkdir(parents=True)
    msa = inputs / "query.a3m"
    shutil.copy2(arguments.msa.resolve(), msa)
    yaml = inputs / arguments.input_yaml.name
    yaml_text = arguments.input_yaml.read_text()
    yaml_text, count = re.subn(
        r"(^\s*msa:\s*).+$", lambda match: match.group(1) + str(msa), yaml_text,
        count=1, flags=re.MULTILINE,
    )
    if count != 1:
        raise SystemExit("input YAML must contain exactly one explicit MSA path")
    yaml.write_text(yaml_text)

    venv = output / "venv"
    candidate_python = venv / "bin/python"
    uv_cache = ROOT / "Validation/cache/runtime_consolidation_v1"
    install_env = {
        **os.environ,
        "UV_CACHE_DIR": str(uv_cache),
        "UV_LINK_MODE": "clone",
    }
    install_log = output / "install.log"
    run([str(arguments.uv), "venv", "--python", str(arguments.python), str(venv)], env=install_env)
    with install_log.open("w") as handle:
        completed = subprocess.run(
            [str(arguments.uv), "pip", "install", "--python", str(candidate_python),
             "--require-hashes", "-r", str(LOCK)],
            env=install_env, stdout=handle, stderr=subprocess.STDOUT, text=True,
        )
    if completed.returncode:
        raise SystemExit(f"baseline hash-lock installation failed; see {install_log}")
    before = freeze(arguments.uv, candidate_python, install_env)
    with install_log.open("a") as handle:
        completed = subprocess.run(
            [str(arguments.uv), "pip", "install", "--python", str(candidate_python),
             "--no-deps", "--reinstall", arguments.torch_wheel_url],
            env=install_env, stdout=handle, stderr=subprocess.STDOUT, text=True,
        )
    if completed.returncode:
        raise SystemExit(f"PyTorch candidate installation failed; see {install_log}")
    run([str(arguments.uv), "pip", "check", "--python", str(candidate_python)], env=install_env)
    after = freeze(arguments.uv, candidate_python, install_env)
    changed = {
        name: [package_map(before).get(name), package_map(after).get(name)]
        for name in sorted(set(package_map(before)) | set(package_map(after)))
        if package_map(before).get(name) != package_map(after).get(name)
    }
    if set(changed) != {"torch"}:
        raise SystemExit(f"candidate replacement changed packages other than torch: {changed}")

    probe = (
        "import numpy as np, torch; "
        "assert torch.backends.mps.is_available(); "
        "r=np.random.default_rng(0); n,p=50000,25; "
        "A=torch.tensor(r.standard_normal((n,p)),dtype=torch.float32); "
        "w=torch.tensor(r.random(n),dtype=torch.float32); Aw=A*w.unsqueeze(-1); "
        "ref=Aw.double().T@A.double(); "
        "err=lambda: float(((Aw.to('mps').T@A.to('mps')).cpu().double()-ref).abs().max()); "
        "print('fresh',err()); "
        "big=torch.tensor(r.standard_normal((200000,p)),dtype=torch.float32); "
        "wb=torch.tensor(r.random(200000),dtype=torch.float32); "
        "((big*wb.unsqueeze(-1)).to('mps').T@big.to('mps')).cpu(); "
        "print('triggered',err()); torch.mps.empty_cache(); print('cleared',err())"
    )
    probe_log = output / "allocator_probe.log"
    run([str(candidate_python), "-c", probe], env={**os.environ, "PYTORCH_ENABLE_MPS_FALLBACK": "0"}, log=probe_log)

    manifest: dict[str, object] = {
        "schema_version": 1,
        "created_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "git_commit": capture(["git", "rev-parse", "HEAD"]),
        "hardware": platform.platform(),
        "input_yaml_sha256": sha256(yaml),
        "msa_sha256": sha256(msa),
        "lock_sha256": sha256(LOCK),
        "launcher_sha256": sha256(LAUNCHER),
        "torch_wheel_url": arguments.torch_wheel_url,
        "torch_214_cp311_macos_arm64_sha256": TORCH_214_CP311_MACOS_ARM64_SHA256,
        "package_change": changed,
        "control": {
            "python": str(CURRENT_PYTHON),
            "torch": capture([str(CURRENT_PYTHON), "-c", "import torch; print(torch.__version__)"]),
        },
        "candidate": {
            "python": str(candidate_python),
            "torch": capture([str(candidate_python), "-c", "import torch; print(torch.__version__)"]),
            "freeze": after,
        },
        "schedule": list(SCHEDULE),
        "runs": [],
    }
    atomic_json(output / "manifest.json", manifest)

    pythons = {"control": CURRENT_PYTHON, "candidate": candidate_python}
    environment = {**os.environ, "PYTORCH_ENABLE_MPS_FALLBACK": "0"}
    common = [
        "predict", str(yaml), "--cache", str(CURRENT_CACHE), "--accelerator", "gpu",
        "--devices", "1", "--num_workers", "0", "--output_format", "mmcif",
        "--override", "--seed", "42",
    ]
    for index, mode in enumerate(SCHEDULE, start=1):
        run_dir = output / "runs" / f"{index:02d}_{mode}"
        run_dir.mkdir(parents=True)
        log = run_dir / "run.log"
        command = [str(pythons[mode]), str(LAUNCHER), *common, "--out_dir", str(run_dir)]
        started = time.monotonic()
        run(command, env=environment, log=log)
        wall_seconds = time.monotonic() - started
        run([str(pythons[mode]), str(VALIDATOR), str(run_dir)], env=environment)
        structures = sorted(run_dir.rglob("*.cif"))
        confidences = sorted(run_dir.rglob("confidence_*.json"))
        log_text = log.read_text(errors="replace")
        if len(structures) != 1 or len(confidences) != 1:
            raise SystemExit(f"wrong output cardinality for {mode} run {index}")
        if "GPU available: True (mps), used: True" not in log_text:
            raise SystemExit(f"MPS was not selected for {mode} run {index}")
        fallback = [line for line in log_text.splitlines() if "fall back" in line.lower()]
        unexpected = [line for line in fallback if "linalg_svd" not in line]
        if unexpected:
            raise SystemExit(f"unexpected CPU fallback in {mode} run {index}: {unexpected}")
        confidence = json.loads(confidences[0].read_text())
        timing_matches = re.findall(
            r"Predicting DataLoader 0: 100%[^\n]*?1/1 \[(\d+):(\d+)<", log_text
        )
        manifest["runs"].append({
            "index": index,
            "mode": mode,
            "wall_seconds": wall_seconds,
            "model_progress_seconds": (
                int(timing_matches[-1][0]) * 60 + int(timing_matches[-1][1])
                if timing_matches else None
            ),
            "structure": str(structures[0].relative_to(output)),
            "structure_sha256": sha256(structures[0]),
            "known_svd_fallback_lines": len(fallback),
            "confidence": {
                key: confidence.get(key)
                for key in ("confidence_score", "ptm", "complex_plddt", "complex_pde")
            },
        })
        atomic_json(output / "manifest.json", manifest)

    reference_path = output / manifest["runs"][0]["structure"]
    reference = ca_coordinates(reference_path)
    for record in manifest["runs"]:
        record["ca_rmsd_to_first_control"] = aligned_rmsd(
            reference, ca_coordinates(output / record["structure"])
        )
    summary: dict[str, object] = {}
    for mode in ("control", "candidate"):
        records = [record for record in manifest["runs"] if record["mode"] == mode]
        walls = [record["wall_seconds"] for record in records]
        summary[mode] = {
            "n": len(records),
            "wall_seconds_mean": statistics.mean(walls),
            "wall_seconds_sd": statistics.stdev(walls),
            "structure_hashes": sorted({record["structure_sha256"] for record in records}),
            "ptm_values": [record["confidence"]["ptm"] for record in records],
            "complex_plddt_values": [
                record["confidence"]["complex_plddt"] for record in records
            ],
            "ca_rmsd_to_first_control": [
                record["ca_rmsd_to_first_control"] for record in records
            ],
        }
        if mode == "candidate":
            warm_walls = walls[1:]
            summary[mode]["cold_first_wall_seconds"] = walls[0]
            summary[mode]["warm_n"] = len(warm_walls)
            summary[mode]["warm_wall_seconds_mean"] = statistics.mean(warm_walls)
            summary[mode]["warm_wall_seconds_sd"] = statistics.stdev(warm_walls)
    manifest["summary"] = summary
    manifest["status"] = "complete"
    atomic_json(output / "manifest.json", manifest)
    print(output / "manifest.json")


if __name__ == "__main__":
    main()
