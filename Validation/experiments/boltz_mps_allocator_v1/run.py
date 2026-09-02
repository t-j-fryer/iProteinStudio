#!/usr/bin/env python3
"""Paired fresh-process Boltz control for the MPS allocator boundary."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
import platform
import re
import shutil
import subprocess
import time

import numpy as np


ROOT = Path(__file__).resolve().parents[3]
DEFAULT_OUTPUT = ROOT / "Validation/output/boltz_mps_allocator_v1"
SCHEDULE = ("control", "candidate", "candidate", "control", "control", "candidate")


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def atomic_json(path: Path, value: object) -> None:
    temporary = path.with_suffix(path.suffix + ".part")
    temporary.write_text(json.dumps(value, indent=2, sort_keys=True) + "\n")
    temporary.replace(path)


def ca_coordinates(path: Path) -> np.ndarray:
    lines = path.read_text(errors="replace").splitlines()
    columns: list[str] = []
    rows: list[list[str]] = []
    for index, line in enumerate(lines):
        if line.strip() != "loop_":
            continue
        cursor = index + 1
        current: list[str] = []
        while cursor < len(lines) and lines[cursor].strip().startswith("_atom_site."):
            current.append(lines[cursor].strip().removeprefix("_atom_site."))
            cursor += 1
        if current:
            columns = current
            pending: list[str] = []
            import shlex
            while cursor < len(lines):
                stripped = lines[cursor].strip()
                if not stripped or stripped.startswith("#"):
                    break
                pending.extend(shlex.split(stripped, comments=False, posix=True))
                while len(pending) >= len(columns):
                    rows.append(pending[:len(columns)])
                    pending = pending[len(columns):]
                cursor += 1
            break
    lookup = {name: index for index, name in enumerate(columns)}
    required = ("label_atom_id", "Cartn_x", "Cartn_y", "Cartn_z")
    if not rows or any(name not in lookup for name in required):
        raise RuntimeError(f"could not read atom coordinates from {path}")
    result = [
        [float(row[lookup["Cartn_x"]]), float(row[lookup["Cartn_y"]]), float(row[lookup["Cartn_z"]])]
        for row in rows if row[lookup["label_atom_id"]].upper() == "CA"
    ]
    return np.asarray(result, dtype=np.float64)


def aligned_rmsd(reference: np.ndarray, mobile: np.ndarray) -> float:
    if reference.shape != mobile.shape or reference.shape[0] == 0:
        raise RuntimeError(f"incompatible CA arrays: {reference.shape} versus {mobile.shape}")
    left = reference - reference.mean(axis=0)
    right = mobile - mobile.mean(axis=0)
    u, _, vt = np.linalg.svd(left.T @ right)
    rotation = u @ vt
    if np.linalg.det(rotation) < 0:
        u[:, -1] *= -1
        rotation = u @ vt
    difference = left @ rotation - right
    return float(np.sqrt(np.mean(np.sum(difference * difference, axis=1))))


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--input-yaml", type=Path, required=True)
    parser.add_argument("--msa", type=Path, required=True)
    parser.add_argument("--control-wrapper", type=Path, required=True)
    parser.add_argument("--candidate-wrapper", type=Path, required=True)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    arguments = parser.parse_args()

    source_yaml = arguments.input_yaml.resolve()
    source_msa = arguments.msa.resolve()
    wrappers = {
        "control": arguments.control_wrapper.resolve(),
        "candidate": arguments.candidate_wrapper.resolve(),
    }
    output = arguments.output.resolve()
    if output.exists():
        raise SystemExit(f"refusing to alter existing validation output: {output}")
    input_dir = output / "input"
    input_dir.mkdir(parents=True)
    msa = input_dir / "query.a3m"
    shutil.copy2(source_msa, msa)
    yaml = input_dir / source_yaml.name
    yaml_text = source_yaml.read_text()
    yaml_text, replacements = re.subn(
        r"(^\s*msa:\s*).+$", lambda match: match.group(1) + str(msa), yaml_text,
        count=1, flags=re.MULTILINE,
    )
    if replacements != 1:
        raise SystemExit("input YAML must contain exactly one explicit MSA path")
    yaml.write_text(yaml_text)

    support = Path.home() / ".iproteinstudio"
    python = support / "venvs/NanoHunter_boltz/bin/python"
    cache = support / "models/boltz2"
    common = [
        "predict", str(yaml), "--cache", str(cache), "--accelerator", "gpu",
        "--devices", "1", "--num_workers", "0", "--output_format", "mmcif",
        "--override", "--seed", "42",
    ]
    commands = []
    for index, mode in enumerate(SCHEDULE, start=1):
        run_dir = output / "runs" / f"{index:02d}_{mode}"
        commands.append([str(python), str(wrappers[mode]), *common,
                         "--out_dir", str(run_dir)])
    manifest = {
        "schema_version": 1,
        "created_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "hardware": platform.platform(),
        "git_commit": subprocess.run(
            ["git", "rev-parse", "HEAD"], cwd=ROOT, check=True,
            text=True, capture_output=True,
        ).stdout.strip(),
        "torch": subprocess.run(
            [str(python), "-c", "import torch; print(torch.__version__)"],
            check=True, text=True, capture_output=True,
        ).stdout.strip(),
        "boltz": subprocess.run(
            [str(python), "-c", "import importlib.metadata; print(importlib.metadata.version('boltz'))"],
            check=True, text=True, capture_output=True,
        ).stdout.strip(),
        "input_yaml_sha256": sha256(yaml),
        "msa_sha256": sha256(msa),
        "wrappers": {mode: {"path": str(path), "sha256": sha256(path)}
                     for mode, path in wrappers.items()},
        "schedule": list(SCHEDULE),
        "commands": commands,
        "runs": [],
    }
    atomic_json(output / "manifest.json", manifest)

    environment = {**os.environ, "NANOHUNTER_ROOT": str(support),
                   "PYTORCH_ENABLE_MPS_FALLBACK": "0"}
    for index, (mode, command) in enumerate(zip(SCHEDULE, commands), start=1):
        run_dir = output / "runs" / f"{index:02d}_{mode}"
        run_dir.mkdir(parents=True)
        log = run_dir / "run.log"
        print(f"[{index}/{len(SCHEDULE)}] {mode}", flush=True)
        started = time.monotonic()
        with log.open("w") as handle:
            completed = subprocess.run(command, env=environment, stdout=handle,
                                       stderr=subprocess.STDOUT, text=True)
        wall = time.monotonic() - started
        log_text = log.read_text(errors="replace")
        structures = sorted(run_dir.rglob("*.cif"))
        confidences = sorted(run_dir.rglob("confidence_*.json"))
        required_markers = (
            "GPU available: True (mps), used: True",
            "IPROTEINSTUDIO_GEOMETRY_OK|structures=1",
        )
        if completed.returncode or len(structures) != 1 or len(confidences) != 1:
            raise SystemExit(f"{mode} run {index} failed cardinality/exit audit; see {log}")
        if any(marker not in log_text for marker in required_markers):
            raise SystemExit(f"{mode} run {index} failed MPS/geometry audit; see {log}")
        reset_count = log_text.count("IPROTEINSTUDIO_MPS_ALLOCATOR_RESET")
        if reset_count != (1 if mode == "candidate" else 0):
            raise SystemExit(f"{mode} run {index} has wrong reset count {reset_count}")
        fallback_lines = [line for line in log_text.splitlines() if "fall back" in line.lower()]
        unexpected = [line for line in fallback_lines if "linalg_svd" not in line]
        if unexpected:
            raise SystemExit(f"{mode} run {index} used an unexpected fallback: {unexpected}")
        timing_matches = re.findall(
            r"Predicting DataLoader 0: 100%[^\n]*?1/1 \[(\d+):(\d+)<", log_text
        )
        confidence = json.loads(confidences[0].read_text())
        record = {
            "index": index,
            "mode": mode,
            "returncode": completed.returncode,
            "wall_seconds": wall,
            "model_progress_seconds": (
                int(timing_matches[-1][0]) * 60 + int(timing_matches[-1][1])
                if timing_matches else None
            ),
            "structure": str(structures[0].relative_to(output)),
            "structure_sha256": sha256(structures[0]),
            "confidence": {name: confidence.get(name) for name in
                           ("confidence_score", "ptm", "complex_plddt", "complex_pde")},
            "known_svd_fallback_lines": len(fallback_lines),
            "allocator_reset_count": reset_count,
        }
        manifest["runs"].append(record)
        atomic_json(output / "manifest.json", manifest)

    reference_path = output / manifest["runs"][0]["structure"]
    reference = ca_coordinates(reference_path)
    for record in manifest["runs"]:
        coordinates = ca_coordinates(output / record["structure"])
        record["ca_rmsd_to_first_control"] = aligned_rmsd(reference, coordinates)
    by_mode = {
        mode: [record for record in manifest["runs"] if record["mode"] == mode]
        for mode in ("control", "candidate")
    }
    manifest["summary"] = {
        mode: {
            "n": len(records),
            "wall_seconds_mean": float(np.mean([row["wall_seconds"] for row in records])),
            "wall_seconds_sd": float(np.std([row["wall_seconds"] for row in records], ddof=1)),
            "model_progress_seconds_mean": float(np.mean(
                [row["model_progress_seconds"] for row in records]
            )),
            "ptm_mean": float(np.mean([row["confidence"]["ptm"] for row in records])),
            "plddt_mean": float(np.mean(
                [row["confidence"]["complex_plddt"] for row in records]
            )),
            "rmsd_to_first_control_mean": float(np.mean(
                [row["ca_rmsd_to_first_control"] for row in records]
            )),
        } for mode, records in by_mode.items()
    }
    manifest["status"] = "complete"
    atomic_json(output / "manifest.json", manifest)
    atomic_json(output / "audit.json", {
        "status": "pass", "completed_runs": len(manifest["runs"]),
        "expected_runs": len(SCHEDULE), "all_geometry_valid": True,
        "unexpected_cpu_fallbacks": 0,
    })
    print(json.dumps(manifest["summary"], indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
