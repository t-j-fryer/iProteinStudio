#!/usr/bin/env python3
"""Test Protenix Constraint through the ordinary Protenix dependency runtime."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import sys
import time


ROOT = Path(__file__).resolve().parents[3]
DEFAULT_OUTPUT = ROOT / "Validation/output/runtime_consolidation_v1/protenix_shared"
RUNTIME = Path.home() / ".iproteinstudio"
SOURCE = RUNTIME / "src/ProtenixConstraint"
MODEL_ROOT = RUNTIME / "models/protenix_constraint"
CONTROL = RUNTIME / "venvs/NanoHunter_protenix_constraint/bin/protenix"
CANDIDATE = RUNTIME / "venvs/NanoHunter_protenix/bin/protenix"
VALIDATOR = ROOT / "Sources/iProteinStudio/Resources/pipeline/scripts/validate_prediction_geometry.py"
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


def tree_sha256(path: Path) -> str:
    digest = hashlib.sha256()
    for item in sorted(path.rglob("*.py")):
        digest.update(str(item.relative_to(path)).encode())
        digest.update(b"\0")
        digest.update(item.read_bytes())
        digest.update(b"\0")
    return digest.hexdigest()


def capture(command: list[str], environment: dict[str, str] | None = None) -> str:
    return subprocess.run(
        command, env=environment, text=True, check=True, capture_output=True
    ).stdout.strip()


def atomic_json(path: Path, value: object) -> None:
    temporary = path.with_suffix(path.suffix + ".part")
    temporary.write_text(json.dumps(value, indent=2, sort_keys=True) + "\n")
    temporary.replace(path)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--input-json", type=Path, required=True)
    parser.add_argument("--target-msa", type=Path, required=True)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    args = parser.parse_args()
    output = args.output.resolve()
    allowed = (ROOT / "Validation/output").resolve()
    if output == allowed or allowed not in output.parents:
        raise SystemExit(f"output must be below {allowed}")
    if output.exists():
        raise SystemExit(f"refusing to overwrite experiment output: {output}")
    for required in (
        args.input_json, args.target_msa, SOURCE, MODEL_ROOT, CONTROL, CANDIDATE, VALIDATOR
    ):
        if not required.exists():
            raise SystemExit(f"required input is missing: {required}")

    inputs = output / "input"
    inputs.mkdir(parents=True)
    jobs = json.loads(args.input_json.read_text())
    if len(jobs) != 1 or len(jobs[0].get("sequences", [])) != 2:
        raise SystemExit("this controlled smoke requires one two-chain input")
    for index, sequence_record in enumerate(jobs[0]["sequences"]):
        protein = sequence_record["proteinChain"]
        msa = inputs / f"chain_{index + 1}.a3m"
        if index == 0:
            msa.write_text(f">query\n{protein['sequence']}\n")
        else:
            shutil.copy2(args.target_msa.resolve(), msa)
        protein["unpairedMsaPath"] = str(msa)
    input_json = inputs / "input.json"
    input_json.write_text(json.dumps(jobs, indent=2) + "\n")

    checkpoint = MODEL_ROOT / "checkpoint/protenix_base_constraint_v0.5.0.pt"
    manifest: dict[str, object] = {
        "schema_version": 1,
        "git_commit": capture(["git", "rev-parse", "HEAD"]),
        "source_commit": capture(["git", "-C", str(SOURCE), "rev-parse", "HEAD"]),
        "source_python_tree_sha256": tree_sha256(SOURCE),
        "checkpoint_sha256": sha256(checkpoint),
        "input_sha256": sha256(input_json),
        "msa_sha256": [sha256(inputs / "chain_1.a3m"), sha256(inputs / "chain_2.a3m")],
        "runs": [],
    }
    atomic_json(output / "manifest.json", manifest)

    common = [
        "pred", "-i", str(input_json), "-s", "42", "-e", "1", "-n",
        "protenix_base_constraint_v0.5.0", "--use_default_params", "False",
        "--use_msa", "True", "--use_template", "False", "--use_rna_msa", "False",
        "--trimul_kernel", "torch", "--triatt_kernel", "torch",
        "--enable_cache", "False", "--enable_fusion", "False",
        "--enable_tf32", "False", "--need_atom_confidence", "True", "-d", "fp32",
        "-c", "10", "-p", "200", "--use_tfg_guidance", "False",
    ]
    environments = {
        "control": CONTROL,
        "shared": CANDIDATE,
    }
    for mode, executable in environments.items():
        run_dir = output / mode
        run_dir.mkdir()
        log = run_dir / "run.log"
        environment = {
            **os.environ,
            "PYTHONPATH": str(SOURCE),
            "PROTENIX_ROOT_DIR": str(MODEL_ROOT),
            "MPLCONFIGDIR": str(output / "matplotlib"),
            "PYTORCH_ENABLE_MPS_FALLBACK": "0",
        }
        command = [str(executable), *common, "-o", str(run_dir)]
        print("+ " + " ".join(command), flush=True)
        started = time.monotonic()
        with log.open("w") as handle:
            completed = subprocess.run(
                command, cwd=RUNTIME, env=environment,
                stdout=handle, stderr=subprocess.STDOUT, text=True,
            )
        wall_seconds = time.monotonic() - started
        if completed.returncode:
            raise SystemExit(f"{mode} failed; see {log}")
        log_text = log.read_text(errors="replace")
        required_markers = (
            "Using Apple Metal Performance Shaders (MPS).",
            "Checkpoint strict load succeeded with no incompatible keys.",
            "Inference by Protenix: model_size: base, with_feature: constraint",
        )
        if any(marker not in log_text for marker in required_markers):
            raise SystemExit(f"{mode} did not prove the native-MPS constraint path")
        forbidden = [
            line for line in log_text.splitlines()
            if "fall back" in line.lower() or "cpu fallback" in line.lower()
        ]
        if forbidden:
            raise SystemExit(f"{mode} reported a forbidden fallback: {forbidden}")
        subprocess.run([sys.executable, str(VALIDATOR), str(run_dir)], check=True)
        structures = sorted(run_dir.rglob("*.cif"))
        confidence_files = sorted(run_dir.rglob("*_summary_confidence_sample_0.json"))
        if len(structures) != 1 or len(confidence_files) != 1:
            raise SystemExit(
                f"{mode} produced {len(structures)} structures and "
                f"{len(confidence_files)} confidence files"
            )
        confidence = json.loads(confidence_files[0].read_text())
        forward = re.findall(r"Model forward time: ([0-9.]+)s", log_text)
        python = Path(executable).resolve().parents[1] / "bin/python"
        manifest["runs"].append({
            "mode": mode,
            "python": capture([str(python), "-c", "import sys; print(sys.version.split()[0])"]),
            "torch": capture([str(python), "-c", "import torch; print(torch.__version__)"]),
            "wall_seconds": wall_seconds,
            "forward_seconds": float(forward[-1]) if forward else None,
            "structure": str(structures[0].relative_to(output)),
            "structure_sha256": sha256(structures[0]),
            "confidence": confidence,
        })
        atomic_json(output / "manifest.json", manifest)

    control_path = output / manifest["runs"][0]["structure"]
    shared_path = output / manifest["runs"][1]["structure"]
    manifest["comparison"] = {
        "ca_rmsd_angstrom": aligned_rmsd(
            ca_coordinates(control_path), ca_coordinates(shared_path)
        ),
        "structure_hash_equal": manifest["runs"][0]["structure_sha256"]
        == manifest["runs"][1]["structure_sha256"],
    }
    manifest["status"] = "complete"
    atomic_json(output / "manifest.json", manifest)
    print(output / "manifest.json")


if __name__ == "__main__":
    main()
