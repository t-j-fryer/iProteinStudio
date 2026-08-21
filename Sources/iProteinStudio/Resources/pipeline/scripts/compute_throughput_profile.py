#!/usr/bin/env python3
"""Build or query a conservative per-device predictor throughput profile.

The profile deliberately keeps workload topology explicit.  A 100+96 two-chain
complex is not treated as a 196-residue monomer, and potentials are a separate
Boltz feature class.  Recommendations maximize measured throughput subject to
a live unified-memory reserve and prefer the lower-memory setting when timing
differences are within three percent.
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import math
import platform
import re
import statistics
import subprocess
import time
from collections import defaultdict
from pathlib import Path
from typing import Any


REPO = Path(__file__).resolve().parent.parent


def capture(command: list[str]) -> str:
    try:
        return subprocess.run(
            command, capture_output=True, text=True, timeout=20
        ).stdout.strip()
    except (OSError, subprocess.TimeoutExpired):
        return ""


def machine_identity() -> dict[str, Any]:
    ram = capture(["sysctl", "-n", "hw.memsize"])
    identity = {
        "hostname": platform.node(),
        "platform": platform.platform(),
        "macos": capture(["sw_vers", "-productVersion"]),
        "chip": capture(["sysctl", "-n", "machdep.cpu.brand_string"]),
        "logical_cpus": capture(["sysctl", "-n", "hw.ncpu"]),
        "physical_memory_bytes": int(ram) if ram.isdigit() else None,
    }
    identity["fingerprint"] = hashlib.sha256(
        json.dumps(identity, sort_keys=True).encode()
    ).hexdigest()[:16]
    return identity


def machine_identity_compatible(
    calibrated: dict[str, Any], current: dict[str, Any]
) -> bool:
    """Allow unavailable sandboxed sysctl fields, but reject real conflicts."""
    for key in ("hostname", "platform", "macos"):
        if not calibrated.get(key) or not current.get(key):
            return False
        if calibrated[key] != current[key]:
            return False
    for key in ("chip", "logical_cpus", "physical_memory_bytes"):
        expected = calibrated.get(key)
        observed = current.get(key)
        if expected not in (None, "") and observed not in (None, ""):
            if expected != observed:
                return False
    return True


def file_digest(path: Path) -> str | None:
    if not path.is_file():
        return None
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def package_version(python: Path, package: str) -> str | None:
    if not python.is_file():
        return None
    value = capture(
        [
            str(python),
            "-c",
            f"import importlib.metadata as m; print(m.version({package!r}))",
        ]
    )
    return value or None


def software_identity() -> dict[str, Any]:
    venv = REPO / "venvs"
    packages = {
        "boltz": (venv / "NanoHunter_boltz/bin/python", "boltz"),
        "intellifold": (venv / "NanoHunter_intellifold/bin/python", "intellifold"),
        "openfold3_mlx": (venv / "NanoHunter_openfold3_mlx/bin/python", "openfold3-mlx"),
    }
    identity = {
        "packages": {
            label: package_version(python, package)
            for label, (python, package) in packages.items()
        },
        "runner_sha256": file_digest(REPO / "nanohunter_run.sh"),
        "benchmark_runner_sha256": file_digest(REPO / "scripts/benchmark_sumo_predictors.py"),
        "openfold_model": None,
    }
    for label, path in (
        ("openfold_model", REPO / "models/openfold3/of3_ft3_v1.pt"),
    ):
        if path.is_file():
            stat = path.stat()
            identity[label] = {"path": str(path), "size": stat.st_size, "mtime_ns": stat.st_mtime_ns}
    identity["fingerprint"] = hashlib.sha256(
        json.dumps(identity, sort_keys=True).encode()
    ).hexdigest()[:16]
    return identity


def as_float(row: dict[str, Any], key: str, default: float = 0.0) -> float:
    try:
        return float(row.get(key, default))
    except (TypeError, ValueError):
        return default


def as_int(row: dict[str, Any], key: str, default: int = 0) -> int:
    return int(round(as_float(row, key, default)))


def percentile(values: list[float], q: float) -> float:
    if not values:
        return math.nan
    ordered = sorted(values)
    position = (len(ordered) - 1) * q
    lo = math.floor(position)
    hi = math.ceil(position)
    if lo == hi:
        return ordered[lo]
    return ordered[lo] * (hi - position) + ordered[hi] * (position - lo)


def swap_used_mb(value: Any) -> float:
    match = re.search(r"used\s*=\s*([\d.]+)([MGT])", str(value or ""), re.I)
    if not match:
        return 0.0
    number = float(match.group(1))
    return number * {"M": 1.0, "G": 1024.0, "T": 1024.0**2}[match.group(2).upper()]


def summarize_rows(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    schema2_present = any(
        as_int(row, "calibration_schema_version") == 2 for row in rows
    )
    groups: dict[tuple[Any, ...], list[dict[str, Any]]] = defaultdict(list)
    for row in rows:
        if schema2_present and as_int(row, "calibration_schema_version") != 2:
            continue
        if row.get("phase") == "warmup" or str(row.get("stage", "")).startswith("warmup"):
            continue
        # Coarse/local native-batch screens are decision inputs, not profile
        # estimates. Only their replicated batch_confirm finalists and the
        # subsequent length/concurrency screens can become recommendations.
        if row.get("phase") in {"batch_screen", "batch_refine"}:
            continue
        if as_int(row, "failed_processes") or as_int(row, "n_completed") != as_int(row, "n_inputs"):
            continue
        if row.get("total_inputs") not in (None, "") and as_int(
            row, "n_inputs"
        ) != as_int(row, "total_inputs"):
            continue
        if swap_used_mb(row.get("swap_end")) - swap_used_mb(row.get("swap_start")) > 128:
            continue
        key = (
            row.get("predictor"),
            bool(str(row.get("potentials", "False")).lower() == "true"),
            as_int(row, "binder_length"),
            as_int(row, "target_length"),
            as_int(row, "ligand_atoms"),
            as_int(row, "binder_msa_depth", 1),
            as_int(row, "target_msa_depth"),
            as_int(row, "processes"),
            as_int(row, "native_batch_per_process", 1),
            as_int(row, "recycles"),
        )
        groups[key].append(row)

    summaries = []
    for key, group in sorted(groups.items()):
        seconds = [as_float(row, "sec_per_prediction") for row in group]
        memories = [as_float(row, "peak_effective_unified_memory_mb") for row in group]
        (
            predictor, potentials, binder, target, ligand, binder_msa_depth,
            target_msa_depth, processes, batch, recycles,
        ) = key
        median_seconds = statistics.median(seconds)
        summaries.append(
            {
                "predictor": predictor,
                "potentials": potentials,
                "workload_class": "binder_target" if target else "monomer",
                "binder_length": binder,
                "target_length": target,
                "total_polymer_tokens": binder + target,
                "ligand_atoms": ligand,
                "binder_msa_depth": binder_msa_depth,
                "target_msa_depth": target_msa_depth,
                "processes": processes,
                "native_batch_per_process": batch,
                "recycles": recycles,
                "replicates": len(group),
                "median_sec_per_prediction": round(median_seconds, 4),
                "p90_sec_per_prediction": round(percentile(seconds, 0.9), 4),
                "predictions_per_hour": round(3600.0 / median_seconds, 3),
                "observed_peak_memory_mb": round(max(memories), 2),
                "safe_peak_memory_mb": round(
                    max(memories) * 1.15 + max(512.0, 0.05 * max(memories)), 2
                ),
            }
        )
    return summaries


def select_schedule(
    summaries: list[dict[str, Any]],
    predictor: str,
    binder_length: int,
    target_length: int,
    potentials: bool,
    memory_budget_mb: float,
    ligand_atoms: int = 0,
    binder_msa_depth: int = 1,
    target_msa_depth: int = 0,
) -> dict[str, Any]:
    compatible = [
        row
        for row in summaries
        if row["predictor"] == predictor
        and bool(row["potentials"]) == potentials
        and int(row.get("ligand_atoms", 0)) == ligand_atoms
        and (int(row["target_length"]) > 0) == (target_length > 0)
    ]
    if not compatible:
        raise ValueError(f"No profile rows for {predictor}, potentials={potentials}")
    requested_total = binder_length + target_length
    shapes = sorted(
        {
            (
                int(row["binder_length"]), int(row["target_length"]),
                int(row.get("binder_msa_depth", 1)),
                int(row.get("target_msa_depth", 0)),
            )
            for row in compatible
        }
    )
    nearest_binder, nearest_target, nearest_binder_depth, nearest_target_depth = min(
        shapes,
        key=lambda shape: (
            abs(shape[0] + shape[1] - requested_total),
            abs(shape[1] - target_length),
            abs(shape[0] - binder_length),
            abs(math.log2((shape[3] + 1) / (target_msa_depth + 1)))
            if target_msa_depth else 0,
        ),
    )
    measured_totals = [shape[0] + shape[1] for shape in shapes]
    exact_lengths = any(
        shape[0] == binder_length and shape[1] == target_length for shape in shapes
    )
    exact_depth = (
        target_msa_depth <= 0
        or (
            nearest_binder_depth == binder_msa_depth
            and nearest_target_depth == target_msa_depth
        )
    )
    exact = exact_lengths and exact_depth
    within = min(measured_totals) <= requested_total <= max(measured_totals)
    target_shift = abs(nearest_target - target_length)
    depth_ratio = (
        max(nearest_target_depth, target_msa_depth)
        / max(1, min(nearest_target_depth, target_msa_depth))
        if target_msa_depth and nearest_target_depth else 1.0
    )
    confidence = "high" if exact else (
        "medium"
        if (
            within
            and target_shift <= max(50, int(0.25 * max(1, target_length)))
            and depth_ratio <= 4.0
        )
        else "low"
    )
    candidates = [
        row
        for row in compatible
        if row["binder_length"] == nearest_binder
        and row["target_length"] == nearest_target
        and int(row.get("binder_msa_depth", 1)) == nearest_binder_depth
        and int(row.get("target_msa_depth", 0)) == nearest_target_depth
        and row["safe_peak_memory_mb"] <= memory_budget_mb
    ]
    if not candidates:
        # Hard fallback; the caller should still perform its one-run memory
        # calibration before launching this unmeasured workload.
        return {
            "predictor": predictor,
            "potentials": potentials,
            "processes": 1,
            "native_batch_per_process": 1,
            "confidence": "low",
            "reason": "no measured schedule fits the live memory budget",
        }
    fastest = min(candidates, key=lambda row: row["median_sec_per_prediction"])
    near_fastest = [
        row
        for row in candidates
        if row["median_sec_per_prediction"]
        <= fastest["median_sec_per_prediction"] * 1.03
    ]
    chosen = min(
        near_fastest,
        key=lambda row: (
            row["safe_peak_memory_mb"], row["processes"], row["native_batch_per_process"]
        ),
    )
    return {
        **chosen,
        "requested_binder_length": binder_length,
        "requested_target_length": target_length,
        "requested_total_polymer_tokens": requested_total,
        "requested_binder_msa_depth": binder_msa_depth,
        "requested_target_msa_depth": target_msa_depth,
        "nearest_measured_binder_length": nearest_binder,
        "nearest_measured_target_length": nearest_target,
        "nearest_measured_total_polymer_tokens": nearest_binder + nearest_target,
        "nearest_measured_binder_msa_depth": nearest_binder_depth,
        "nearest_measured_target_msa_depth": nearest_target_depth,
        "confidence": confidence if chosen["replicates"] >= 2 else "medium",
        "memory_budget_mb": round(memory_budget_mb, 2),
        "selection_rule": "within 3% of fastest, choose lowest safe memory",
    }


def build_profile(results_csv: Path, output: Path, manifest: Path | None) -> dict[str, Any]:
    with results_csv.open(newline="") as handle:
        rows = list(csv.DictReader(handle))
    profile = {
        "schema_version": 1,
        "created": time.strftime("%Y-%m-%dT%H:%M:%S%z"),
        "machine": machine_identity(),
        "software": software_identity(),
        "source_results": str(results_csv.resolve()),
        "source_manifest": str(manifest.resolve()) if manifest else None,
        "method": {
            "memory_margin": "15% + max(512 MiB, 5%)",
            "tie_threshold_percent": 3,
            "workload_topology_is_explicit": True,
            "energy_monitoring": False,
        },
        "schedules": summarize_rows(rows),
    }
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(profile, indent=2) + "\n")
    return profile


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)
    build = sub.add_parser("build")
    build.add_argument("--results", required=True, type=Path)
    build.add_argument("--manifest", type=Path)
    build.add_argument("--output", required=True, type=Path)
    recommend = sub.add_parser("recommend")
    recommend.add_argument("--profile", required=True, type=Path)
    recommend.add_argument("--predictor", required=True)
    recommend.add_argument("--binder-length", required=True, type=int)
    recommend.add_argument("--target-length", required=True, type=int)
    recommend.add_argument("--potentials", action="store_true")
    recommend.add_argument("--ligand-atoms", type=int, default=0)
    recommend.add_argument("--binder-msa-depth", type=int, default=1)
    recommend.add_argument("--target-msa-depth", type=int, default=0)
    recommend.add_argument("--memory-budget-gb", required=True, type=float)
    args = parser.parse_args()

    if args.command == "build":
        profile = build_profile(args.results, args.output, args.manifest)
        print(json.dumps({"profile": str(args.output), "rows": len(profile["schedules"])}))
    else:
        profile = json.loads(args.profile.read_text())
        current = machine_identity()
        current_software = software_identity()
        calibrated = profile.get("machine", {})
        if not machine_identity_compatible(calibrated, current):
            raise SystemExit(
                "Throughput profile belongs to a different machine/runtime identity; "
                "run calibrate_device_throughput.py on this device."
            )
        if profile.get("software", {}).get("fingerprint") != current_software.get("fingerprint"):
            raise SystemExit(
                "Predictor/runtime files changed since calibration; rebuild the throughput profile."
            )
        choice = select_schedule(
            profile["schedules"],
            args.predictor,
            args.binder_length,
            args.target_length,
            args.potentials,
            args.memory_budget_gb * 1024,
            args.ligand_atoms,
            args.binder_msa_depth,
            args.target_msa_depth,
        )
        print(json.dumps(choice, indent=2))


if __name__ == "__main__":
    main()
