#!/usr/bin/env python3
"""Audit manifest-declared secondary-structure campaign outputs.

The audit is read-only with respect to campaign and durable job state. It writes
only derived CSV/JSON files below ``--output-dir``. An arm is analyzed only when
its durable job state is completed and every declared trajectory passes the
cardinality, sequence, coordinate, confidence, and P-SEA checks.
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import itertools
import json
import math
import os
import re
import statistics
from collections import Counter
from pathlib import Path
from typing import Any, Iterable

import biotite
import numpy as np
from biotite.sequence import ProteinSequence
from biotite.structure import annotate_sse
from biotite.structure.io.pdbx import CIFFile, get_structure


METRICS = (
    "helix_fraction",
    "sheet_fraction",
    "coil_fraction",
    "iptm",
    "ipsae_min",
    "complex_plddt",
    "binder_plddt",
)


class AuditError(RuntimeError):
    """A declared completed arm failed a raw-output invariant."""


def require(condition: bool, message: str) -> None:
    if not condition:
        raise AuditError(message)


def load_json(path: Path) -> Any:
    try:
        return json.loads(path.read_text())
    except (OSError, json.JSONDecodeError) as error:
        raise AuditError(f"cannot read JSON {path}: {error}") from error


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def finite_number(value: Any, label: str) -> float:
    try:
        result = float(value)
    except (TypeError, ValueError) as error:
        raise AuditError(f"{label} is not numeric: {value!r}") from error
    require(math.isfinite(result), f"{label} is not finite")
    return result


def mean_or_none(values: Iterable[float]) -> float | None:
    values = list(values)
    return statistics.mean(values) if values else None


def pairwise_identity(first: str, second: str) -> float:
    require(len(first) == len(second), "cannot compare unequal-length sequences")
    return sum(a == b for a, b in zip(first, second)) / len(first)


def diversity(sequences: list[str]) -> dict[str, Any]:
    pairs = [pairwise_identity(a, b) for a, b in itertools.combinations(sequences, 2)]
    unique = len(set(sequences))
    return {
        "sequences": len(sequences),
        "unique_sequences": unique,
        "unique_fraction": unique / len(sequences) if sequences else None,
        "mean_pairwise_identity": mean_or_none(pairs),
        "min_pairwise_identity": min(pairs) if pairs else None,
        "max_pairwise_identity": max(pairs) if pairs else None,
    }


def relative_label(path: Path, root: Path) -> str:
    try:
        return str(path.relative_to(root))
    except ValueError:
        return f"external/{path.parent.name}/{path.name}"


def hash_file(path: Path, root: Path, checksums: dict[str, str]) -> None:
    label = relative_label(path, root)
    require(label not in checksums, f"duplicate checksum label: {label}")
    checksums[label] = sha256(path)


def structure_record(
    path: Path,
    expected_sequence: str,
    expected_length: int,
    binder_chain: str,
) -> dict[str, Any]:
    try:
        atoms = get_structure(CIFFile.read(path), model=1, extra_fields=["b_factor"])
    except Exception as error:
        raise AuditError(f"cannot parse coordinate file {path}: {error}") from error
    require(len(atoms) > 0, f"empty coordinate array: {path}")
    require(bool(np.isfinite(atoms.coord).all()), f"nonfinite coordinates: {path}")

    chain_atoms = atoms[atoms.chain_id == binder_chain]
    ca = chain_atoms[chain_atoms.atom_name == "CA"]
    require(len(ca) == expected_length, f"expected {expected_length} binder CA atoms, got {len(ca)}: {path}")
    try:
        sequence = "".join(
            "X" if name == "UNK" else ProteinSequence.convert_letter_3to1(name)
            for name in ca.res_name
        )
    except Exception as error:
        raise AuditError(f"cannot derive binder sequence from {path}: {error}") from error
    require(sequence == expected_sequence, f"coordinate/requested sequence mismatch: {path}")

    try:
        codes = "".join(annotate_sse(chain_atoms))
    except Exception as error:
        raise AuditError(f"P-SEA failed for {path}: {error}") from error
    require(len(codes) == expected_length, f"P-SEA returned {len(codes)} residues, expected {expected_length}: {path}")
    require(set(codes) <= {"a", "b", "c"}, f"unexpected P-SEA code in {path}: {set(codes)}")
    counts = Counter(codes)

    b_factors = np.asarray(ca.b_factor, dtype=float)
    require(bool(np.isfinite(b_factors).all()), f"nonfinite binder pLDDT values: {path}")
    binder_plddt = float(np.mean(b_factors)) / 100.0
    require(0.0 <= binder_plddt <= 1.0, f"binder pLDDT outside 0-1 after scaling: {path}")

    distances = np.linalg.norm(np.diff(ca.coord, axis=0), axis=1)
    require(bool(np.isfinite(distances).all()), f"nonfinite adjacent CA distances: {path}")
    return {
        "sequence": sequence,
        "coordinate_x_count": sequence.count("X"),
        "psea": codes,
        "helix_fraction": counts["a"] / expected_length,
        "sheet_fraction": counts["b"] / expected_length,
        "coil_fraction": counts["c"] / expected_length,
        "binder_plddt": binder_plddt,
        "ca_distance_outliers": int(np.sum((distances < 2.5) | (distances > 4.5))),
    }


def read_metrics(path: Path, expected_cycles: set[int]) -> dict[int, dict[str, str]]:
    try:
        rows = list(csv.DictReader(path.open()))
    except OSError as error:
        raise AuditError(f"cannot read metrics CSV {path}: {error}") from error
    require(bool(rows), f"empty metrics CSV: {path}")
    required = {"cycle", "iptm", "complex_plddt", "binder_sequence"}
    require(required <= set(rows[0]), f"metrics CSV lacks {sorted(required - set(rows[0]))}: {path}")
    by_cycle: dict[int, dict[str, str]] = {}
    for row in rows:
        try:
            cycle = int(row["cycle"])
        except (TypeError, ValueError) as error:
            raise AuditError(f"invalid cycle in {path}: {row.get('cycle')!r}") from error
        require(cycle not in by_cycle, f"duplicate cycle {cycle} in {path}")
        by_cycle[cycle] = row
    require(set(by_cycle) == expected_cycles, f"metrics cycles {sorted(by_cycle)} do not equal {sorted(expected_cycles)}: {path}")
    return by_cycle


def check_cardinality_files(
    campaign: Path,
    expected_runs: list[str],
    expected_cycles: set[int],
    root: Path,
    checksums: dict[str, str],
) -> None:
    trajectories = len(expected_runs)
    cycles = len(expected_cycles) - 1
    receipt_path = campaign / "design_cardinality_receipt.json"
    index_path = campaign / "results_index.json"
    require(receipt_path.is_file(), f"missing cardinality receipt: {receipt_path}")
    require(index_path.is_file(), f"missing results index: {index_path}")
    receipt = load_json(receipt_path)
    expected_receipt = {
        "status": "complete",
        "expected_trajectories": trajectories,
        "actual_trajectory_directories": trajectories,
        "expected_starting_structures": trajectories,
        "actual_starting_structures": trajectories,
        "expected_optimized_designs": trajectories * cycles,
        "actual_optimized_designs": trajectories * cycles,
        "expected_total_checkpoints": trajectories * (cycles + 1),
        "actual_total_checkpoints": trajectories * (cycles + 1),
        "cycle_00_counts_as_design": False,
        "missing": [],
    }
    for field, expected in expected_receipt.items():
        require(receipt.get(field) == expected, f"cardinality receipt {field}={receipt.get(field)!r}, expected {expected!r}: {receipt_path}")

    index = load_json(index_path)
    results = index.get("results")
    require(isinstance(results, list), f"results index has no result list: {index_path}")
    expected_keys = {(run, f"cycle_{cycle:02d}") for run in expected_runs for cycle in expected_cycles}
    actual_keys = {(item.get("run"), item.get("cycle")) for item in results}
    require(len(results) == len(expected_keys), f"results index cardinality mismatch: {index_path}")
    require(actual_keys == expected_keys, f"results index run/cycle set mismatch: {index_path}")
    for item in results:
        cycle = int(str(item["cycle"]).split("_")[-1])
        require(bool(item.get("counts_as_design")) == (cycle > 0), f"results index design flag mismatch: {item}")
    hash_file(receipt_path, root, checksums)
    hash_file(index_path, root, checksums)


def audit_device_logs(campaign: Path) -> dict[str, Any]:
    allowed_svd = 0
    mps_lines = 0
    unexpected: list[str] = []
    files = 0
    for path in campaign.rglob("*.log"):
        if ".studio_runtime" in path.parts:
            continue
        files += 1
        for line in path.read_text(errors="replace").splitlines():
            if "MPS" in line or "mps" in line:
                mps_lines += 1
            if re.search(r"fall.?back", line, re.IGNORECASE):
                if "aten::linalg_svd" in line:
                    allowed_svd += 1
                else:
                    unexpected.append(line[-500:])
    require(mps_lines > 0, f"no MPS evidence in logs: {campaign}")
    require(not unexpected, f"unexpected CPU fallback evidence in {campaign}: {unexpected[:3]}")
    return {
        "log_files_scanned": files,
        "mps_log_lines": mps_lines,
        "allowed_svd_warning_occurrences_across_duplicated_logs": allowed_svd,
        "other_fallback_messages": 0,
    }


def audit_launch_provenance(
    arm: str,
    campaign: Path,
    phase: str,
    manifest: dict[str, Any],
    job: dict[str, Any],
    state: dict[str, Any],
    root: Path,
    checksums: dict[str, str],
) -> dict[str, Any]:
    plans = manifest.get("plans", {})
    runtime = manifest.get("runtime", {})
    require(arm in plans, f"launch manifest has no immutable plan for {arm}")
    expected_plan = plans[arm]
    plan_path = root / "plans" / phase / f"{arm}.json"
    require(plan_path.is_file(), f"missing saved immutable plan: {plan_path}")
    plan = load_json(plan_path)
    for field in ("id", "sha256"):
        require(plan.get(field) == expected_plan.get(field), f"saved plan {field} does not match launch manifest: {arm}")
    require(state.get("plan_id") == expected_plan.get("id"), f"durable state plan ID mismatch: {arm}")
    require(state.get("plan_sha256") == expected_plan.get("sha256"), f"durable state plan digest mismatch: {arm}")
    require(job.get("id") == state.get("id"), f"declared/durable job ID mismatch: {arm}")
    require(state.get("exit_code") == 0 and state.get("error") is None, f"completed durable job state records a failure: {arm}")
    output_root = state.get("output_root")
    require(isinstance(output_root, str) and Path(output_root).resolve() == campaign.resolve(), f"durable job output root mismatch: {arm}")

    arguments = plan.get("normalized_request", {}).get("arguments", [])
    require(isinstance(arguments, list), f"saved plan arguments are invalid: {arm}")
    forbidden_initial = {"--initial-structure", "--initial-confidence-json"}
    initial_binder_input_absent = not any(argument in forbidden_initial for argument in arguments)
    require(initial_binder_input_absent, f"pilot unexpectedly imports an initial binder: {arm}")
    require("--random-binder" in arguments, f"pilot does not declare random masked binder initialization: {arm}")

    runner_expected = runtime.get("runner_sha256")
    helper_expected = runtime.get("secondary_helper_sha256")
    require(isinstance(runner_expected, str) and isinstance(helper_expected, str), "launch manifest lacks scientific runtime hashes")
    snapshot = campaign / ".studio_runtime" / "pipeline"
    runner = snapshot / "nanohunter_run.sh"
    helper = snapshot / "scripts" / "secondary_structure_control.py"
    require(runner.is_file() and helper.is_file(), f"scientific pipeline snapshot is incomplete: {campaign}")
    runner_actual = sha256(runner)
    helper_actual = sha256(helper)
    require(runner_actual == runner_expected, f"runner snapshot differs from launch manifest: {arm}")
    require(helper_actual == helper_expected, f"secondary helper snapshot differs from launch manifest: {arm}")
    provenance = plan.get("provenance", [])
    require(any(item.get("sha256") == runner_expected for item in provenance), f"immutable plan lacks launch runner provenance: {arm}")
    hash_file(plan_path, root, checksums)
    hash_file(runner, root, checksums)
    hash_file(helper, root, checksums)
    return {
        "immutable_plan_id": expected_plan["id"],
        "immutable_plan_digest": expected_plan["sha256"],
        "initial_binder_input_absent": initial_binder_input_absent,
        "random_masked_binder_declared": True,
        "snapshot_runner_sha256": runner_actual,
        "snapshot_secondary_helper_sha256": helper_actual,
        "scientific_snapshots_match_launch_manifest": True,
    }


def audit_arm(
    arm: str,
    campaign: Path,
    trajectories: int,
    design_cycles: int,
    binder_length: int,
    binder_chain: str,
    root: Path,
    phase: str,
    manifest: dict[str, Any],
    job: dict[str, Any],
    state: dict[str, Any],
) -> tuple[list[dict[str, Any]], dict[str, str], dict[str, Any]]:
    expected_runs = [f"run_{number:03d}" for number in range(1, trajectories + 1)]
    actual_runs = sorted(path.name for path in campaign.glob("run_*") if path.is_dir())
    require(actual_runs == expected_runs, f"trajectory directories {actual_runs} do not equal declared {expected_runs}: {campaign}")
    expected_cycles = set(range(design_cycles + 1))
    checksums: dict[str, str] = {}
    provenance = audit_launch_provenance(arm, campaign, phase, manifest, job, state, root, checksums)
    check_cardinality_files(campaign, expected_runs, expected_cycles, root, checksums)

    audited: list[dict[str, Any]] = []
    for run in expected_runs:
        run_root = campaign / run
        actual_cycle_dirs = {
            int(path.name.split("_")[-1])
            for path in run_root.glob("cycle_*")
            if path.is_dir() and path.name.split("_")[-1].isdigit()
        }
        require(actual_cycle_dirs == expected_cycles, f"cycle directories {sorted(actual_cycle_dirs)} do not equal declared {sorted(expected_cycles)}: {run_root}")
        metrics_path = run_root / "metrics_per_cycle.csv"
        require(metrics_path.is_file(), f"missing metrics CSV: {metrics_path}")
        metrics = read_metrics(metrics_path, expected_cycles)
        hash_file(metrics_path, root, checksums)
        for cycle in sorted(expected_cycles):
            raw = metrics[cycle]
            sequence = str(raw["binder_sequence"]).strip()
            require(len(sequence) == binder_length, f"requested binder length is {len(sequence)}, expected {binder_length}: {run} cycle {cycle}")
            require(set(sequence) <= set("ACDEFGHIKLMNPQRSTVWYX"), f"invalid binder sequence characters: {run} cycle {cycle}")
            if cycle > 0:
                require("X" not in sequence, f"optimized sequence contains X: {run} cycle {cycle}")
            structure_path = run_root / f"cycle_{cycle:02d}" / "pred_min" / "model_0.cif"
            confidence_path = structure_path.with_name("confidence.json")
            require(structure_path.is_file(), f"missing coordinate output: {structure_path}")
            require(confidence_path.is_file(), f"missing confidence output: {confidence_path}")
            structural = structure_record(structure_path, sequence, binder_length, binder_chain)
            confidence = load_json(confidence_path)
            values = {
                name: finite_number(confidence.get(name), f"{name}: {confidence_path}")
                for name in ("iptm", "ipsae_min", "complex_plddt")
            }
            for name in ("iptm", "complex_plddt"):
                csv_value = finite_number(raw[name], f"metrics {name}: {metrics_path}")
                require(abs(csv_value - values[name]) < 1e-6, f"metrics/confidence {name} mismatch: {run} cycle {cycle}")
            for name, value in values.items():
                require(0.0 <= value <= 1.0, f"{name} outside 0-1: {confidence_path}")
            hash_file(structure_path, root, checksums)
            hash_file(confidence_path, root, checksums)
            audited.append(
                {
                    "arm": arm,
                    "run": run,
                    "cycle": cycle,
                    "is_design": cycle > 0,
                    "requested_sequence": sequence,
                    "requested_x_count": sequence.count("X"),
                    **structural,
                    **values,
                    "structure": str(structure_path.relative_to(root)),
                    "confidence": str(confidence_path.relative_to(root)),
                }
            )
    details = {
        "declared_trajectories": trajectories,
        "declared_design_cycles": design_cycles,
        "expected_structures": trajectories * (design_cycles + 1),
        "audited_structures": len(audited),
        "initial_structures": trajectories,
        "optimized_structures": trajectories * design_cycles,
        "sequence_coordinate_confidence_cardinality_checks": "passed",
        "device_log_audit": audit_device_logs(campaign),
        "launch_provenance": provenance,
    }
    return audited, checksums, details


def progress_snapshot(campaign: Path, trajectories: int, design_cycles: int) -> dict[str, Any]:
    """Count only artifact presence for a noncompleted job; do not audit partial data."""
    progress = []
    for number in range(1, trajectories + 1):
        run = f"run_{number:03d}"
        present = []
        for cycle in range(design_cycles + 1):
            base = campaign / run / f"cycle_{cycle:02d}" / "pred_min"
            if (base / "model_0.cif").is_file() and (base / "confidence.json").is_file():
                present.append(cycle)
        progress.append({"run": run, "coordinate_confidence_cycles_present": present})
    return {
        "artifact_presence_only": True,
        "audited_trajectories": 0,
        "declared_trajectories": trajectories,
        "trajectories": progress,
    }


def summarize_rows(
    rows: list[dict[str, Any]],
    design_cycles: int,
    hit_threshold: float,
    min_sheet: float,
    max_helix: float,
) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    runs = sorted({row["run"] for row in rows})
    cycles: dict[str, Any] = {}
    for cycle in range(design_cycles + 1):
        selected = [row for row in rows if row["cycle"] == cycle]
        values = {name: statistics.mean(row[name] for row in selected) for name in METRICS}
        values.update(
            structures=len(selected),
            iptm_ge_threshold=sum(row["iptm"] >= hit_threshold for row in selected),
            structural_target_count=sum(row["sheet_fraction"] >= min_sheet and row["helix_fraction"] < max_helix for row in selected),
            ca_distance_outliers=sum(row["ca_distance_outliers"] for row in selected),
        )
        cycles[f"cycle_{cycle:02d}"] = values

    endpoint_cycles = {
        "initial": {0},
        "optimized_cycle_mean": set(range(1, design_cycles + 1)),
        "final_cycle": {design_cycles},
    }
    endpoints: dict[str, Any] = {}
    for label, included in endpoint_cycles.items():
        selected = [row for row in rows if row["cycle"] in included]
        endpoint = {name: statistics.mean(row[name] for row in selected) for name in METRICS}
        endpoint.update(
            structures=len(selected),
            trajectories=len(runs),
            iptm_ge_threshold=sum(row["iptm"] >= hit_threshold for row in selected),
            structural_target_count=sum(row["sheet_fraction"] >= min_sheet and row["helix_fraction"] < max_helix for row in selected),
            ca_distance_outliers=sum(row["ca_distance_outliers"] for row in selected),
        )
        endpoints[label] = endpoint

    trajectory_rows: list[dict[str, Any]] = []
    for run in runs:
        per_run = [row for row in rows if row["run"] == run]
        initial = next(row for row in per_run if row["cycle"] == 0)
        optimized = [row for row in per_run if row["cycle"] > 0]
        final = next(row for row in optimized if row["cycle"] == design_cycles)
        ordered_sequences = [row["sequence"] for row in sorted(optimized, key=lambda item: item["cycle"])]
        adjacent = [pairwise_identity(a, b) for a, b in zip(ordered_sequences, ordered_sequences[1:])]
        result: dict[str, Any] = {
            "arm": initial["arm"],
            "run": run,
            "cycle_00_x_count": initial["requested_x_count"],
            "optimized_unique_sequences": len(set(ordered_sequences)),
            "optimized_mean_adjacent_cycle_identity": mean_or_none(adjacent),
            "final_sequence": final["sequence"],
            "final_meets_structural_target": final["sheet_fraction"] >= min_sheet and final["helix_fraction"] < max_helix,
        }
        for name in METRICS:
            result[f"optimized_mean_{name}"] = statistics.mean(row[name] for row in optimized)
            result[f"final_{name}"] = final[name]
        trajectory_rows.append(result)

    optimized_sequences = [row["sequence"] for row in rows if row["cycle"] > 0]
    final_sequences = [row["sequence"] for row in rows if row["cycle"] == design_cycles]
    original_x = [row["requested_x_count"] for row in rows if row["cycle"] == 0]
    summary = {
        "per_cycle": cycles,
        "endpoints": endpoints,
        "original_cycle_00_x_counts": dict(zip(runs, original_x)),
        "sequence_diversity": {
            "all_optimized_cycles": diversity(optimized_sequences),
            "final_cycle_across_trajectories": diversity(final_sequences),
        },
    }
    return summary, trajectory_rows


def write_csv(path: Path, rows: list[dict[str, Any]]) -> None:
    if not rows:
        path.write_text("")
        return
    with path.open("w", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)


def infer_path(root: Path, explicit: Path | None, name: str) -> Path:
    return explicit.resolve() if explicit else root / name


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, required=True, help="Campaign output root")
    parser.add_argument("--phase", default="smoke")
    parser.add_argument("--manifest", type=Path)
    parser.add_argument("--jobs", type=Path)
    parser.add_argument("--job-state-root", type=Path)
    parser.add_argument("--output-dir", type=Path)
    parser.add_argument("--binder-chain", default="A")
    parser.add_argument("--trajectories", type=int, help="Fallback if the manifest declares no trajectory count")
    parser.add_argument("--min-sheet-fraction", type=float, default=0.25)
    parser.add_argument("--max-helix-fraction", type=float, default=0.40)
    args = parser.parse_args()

    root = args.root.resolve()
    manifest_path = infer_path(root, args.manifest, f"manifest_{args.phase}.json")
    jobs_path = infer_path(root, args.jobs, f"jobs_{args.phase}.json")
    output_dir = args.output_dir.resolve() if args.output_dir else root / "analysis"
    runtime_root = Path(os.environ.get("NANOHUNTER_ROOT", str(Path.home() / ".iproteinstudio")))
    state_root = args.job_state_root.resolve() if args.job_state_root else runtime_root / "agent/jobs"

    manifest = load_json(manifest_path)
    config = manifest.get("config", manifest)
    arms = config.get("arms")
    campaign_config = config.get("campaign", {})
    require(isinstance(arms, dict) and arms, f"manifest has no declared arms: {manifest_path}")
    require(jobs_path.is_file(), f"missing arm-to-job declaration: {jobs_path}")
    jobs = load_json(jobs_path)
    require(set(jobs) == set(arms), f"job arms {sorted(jobs)} do not equal manifest arms {sorted(arms)}")

    design_cycles = int(campaign_config["design_cycles"])
    binder_length = int(campaign_config["binder_length"])
    hit_threshold = finite_number(campaign_config.get("hit_threshold", 0.7), "hit threshold")
    require(design_cycles >= 1 and binder_length >= 1, "design cycles and binder length must be positive")
    require(0 <= args.min_sheet_fraction <= 1 and 0 <= args.max_helix_fraction <= 1, "structural thresholds must be in 0-1")

    all_rows: list[dict[str, Any]] = []
    trajectory_rows: list[dict[str, Any]] = []
    raw_sha256: dict[str, str] = {}
    arm_reports: dict[str, Any] = {}
    arm_summaries: dict[str, Any] = {}
    job_states: dict[str, Any] = {}
    declared_expected_structures = 0
    hash_file(manifest_path, root, raw_sha256)
    hash_file(jobs_path, root, raw_sha256)

    for arm, arm_config in arms.items():
        trajectories_value = arm_config.get(
            f"{args.phase}_trajectories",
            arm_config.get(
                "trajectories",
                campaign_config.get(f"{args.phase}_trajectories", campaign_config.get("trajectories", args.trajectories)),
            ),
        )
        require(trajectories_value is not None, f"no trajectory count declared for {arm}")
        trajectories = int(trajectories_value)
        require(trajectories >= 1, f"trajectory count must be positive for {arm}")
        declared_expected_structures += trajectories * (design_cycles + 1)
        job_id = jobs[arm].get("id")
        require(isinstance(job_id, str) and job_id, f"missing job id for {arm}")
        state_path = state_root / job_id / "state.json"
        state = load_json(state_path) if state_path.is_file() else {"status": "state-missing"}
        job_states[arm] = {
            key: state.get(key)
            for key in ("id", "status", "stage", "exit_code", "created_at", "started_at", "finished_at", "updated_at", "error")
        }
        campaign = root / "campaigns" / f"{args.phase}__{arm}"
        if state.get("status") != "completed":
            arm_reports[arm] = {
                "audit_status": "not_audited_job_incomplete",
                "job_status": state.get("status"),
                "job_id": job_id,
                "progress": progress_snapshot(campaign, trajectories, design_cycles),
            }
            continue
        try:
            rows, checksums, details = audit_arm(
                arm,
                campaign,
                trajectories,
                design_cycles,
                binder_length,
                args.binder_chain,
                root,
                args.phase,
                manifest,
                jobs[arm],
                state,
            )
        except AuditError as error:
            arm_reports[arm] = {
                "audit_status": "audit_failed",
                "job_status": "completed",
                "job_id": job_id,
                "error": str(error),
            }
            continue
        state_label = f"job_state/{job_id}.json"
        require(state_label not in raw_sha256, f"duplicate state checksum label: {state_label}")
        raw_sha256[state_label] = sha256(state_path)
        overlap = set(raw_sha256) & set(checksums)
        require(not overlap, f"duplicate raw checksum labels: {sorted(overlap)}")
        raw_sha256.update(checksums)
        summary, per_trajectory = summarize_rows(
            rows,
            design_cycles,
            hit_threshold,
            args.min_sheet_fraction,
            args.max_helix_fraction,
        )
        arm_reports[arm] = {
            "audit_status": "audited_complete",
            "job_status": "completed",
            "job_id": job_id,
            **details,
        }
        arm_summaries[arm] = summary
        all_rows.extend(rows)
        trajectory_rows.extend(per_trajectory)

    paired_initial: dict[str, Any] = {}
    grouped: dict[tuple[Any, ...], list[str]] = {}
    for arm, arm_config in arms.items():
        group_key = tuple((key, value) for key, value in sorted(arm_config.items()) if key != "scope")
        grouped.setdefault(group_key, []).append(arm)
    for group_arms in grouped.values():
        seed = next((arm for arm in group_arms if arms[arm].get("scope") == "seed-only"), None)
        sustained = next((arm for arm in group_arms if arms[arm].get("scope") == "seed-and-cycles"), None)
        if seed in arm_summaries and sustained in arm_summaries:
            seed_rows = {(row["run"], row["cycle"]): row for row in all_rows if row["arm"] == seed}
            sustained_rows = {(row["run"], row["cycle"]): row for row in all_rows if row["arm"] == sustained}
            runs = sorted({run for run, cycle in seed_rows if cycle == 0})
            identities = [pairwise_identity(seed_rows[run, 0]["sequence"], sustained_rows[run, 0]["sequence"]) for run in runs]
            equal = all(identity == 1.0 for identity in identities)
            paired_initial[f"{seed}__vs__{sustained}"] = {
                "trajectories": len(runs),
                "cycle_00_sequences_equal": equal,
                "cycle_00_sequence_identities": dict(zip(runs, identities)),
            }

    candidates = [
        row
        for row in all_rows
        if row["cycle"] > 0
        and row["sheet_fraction"] >= args.min_sheet_fraction
        and row["helix_fraction"] < args.max_helix_fraction
    ]
    ranked = sorted(
        candidates,
        key=lambda row: (
            row["sheet_fraction"],
            -row["helix_fraction"],
            row["iptm"],
            row["ipsae_min"],
            row["binder_plddt"],
        ),
        reverse=True,
    )
    candidate_ranking = [
        {
            key: row[key]
            for key in ("arm", "run", "cycle", "sequence", "sheet_fraction", "helix_fraction", "coil_fraction", "iptm", "ipsae_min", "binder_plddt", "structure")
        }
        for row in ranked
    ]

    declared_rule = config.get("decision_rule")
    decision_evaluation: dict[str, Any] | None = None
    if declared_rule is not None:
        require(isinstance(declared_rule, dict), "declared decision_rule must be an object")
        rule_sheet = finite_number(declared_rule.get("sheet_mean_at_least"), "decision-rule sheet threshold")
        rule_helix = finite_number(declared_rule.get("helix_mean_below"), "decision-rule helix threshold")
        required_trajectories = int(declared_rule.get("require_complete_audited_trajectories", 0))
        require(0 <= rule_sheet <= 1 and 0 <= rule_helix <= 1, "declared decision-rule fractions must be in 0-1")
        require(required_trajectories >= 1, "declared decision rule must require at least one audited trajectory")
        arm_decisions = {}
        for arm in arms:
            endpoint = arm_summaries.get(arm, {}).get("endpoints", {}).get("optimized_cycle_mean")
            meets = bool(
                endpoint
                and endpoint["trajectories"] == required_trajectories
                and endpoint["sheet_fraction"] >= rule_sheet
                and endpoint["helix_fraction"] < rule_helix
            )
            arm_decisions[arm] = {
                "audited_trajectories": endpoint["trajectories"] if endpoint else 0,
                "sheet_mean": endpoint["sheet_fraction"] if endpoint else None,
                "helix_mean": endpoint["helix_fraction"] if endpoint else None,
                "meets_declared_rule": meets,
            }
        decision_evaluation = {
            "statistical_unit": "trajectory; cycles 01-design_cycles averaged within each complete trajectory",
            "sheet_mean_at_least": rule_sheet,
            "helix_mean_below": rule_helix,
            "required_complete_audited_trajectories": required_trajectories,
            "arms": arm_decisions,
            "at_least_one_arm_meets_declared_rule": any(value["meets_declared_rule"] for value in arm_decisions.values()),
        }

    report = {
        "schema": 1,
        "method": {
            "cycle_00_is_design": False,
            "secondary_structure": "Biotite P-SEA on predicted binder-chain coordinates",
            "binder_plddt_scale": "0-1 (mean binder-chain CA B factor divided by 100)",
            "optimized_cycle_mean": f"cycles 01-{design_cycles:02d}, balanced within every fully audited trajectory",
            "structural_target": {
                "sheet_fraction_greater_than_or_equal": args.min_sheet_fraction,
                "helix_fraction_strictly_less_than": args.max_helix_fraction,
            },
            "candidate_ranking": "structural-target pass, then sheet descending, helix ascending, iPTM, ipSAE, binder pLDDT",
            "candidate_ranking_is_exploratory": True,
            "biotite_version": biotite.__version__,
            "numpy_version": np.__version__,
        },
        "job_states": job_states,
        "arm_audits": arm_reports,
        "arms": arm_summaries,
        "paired_initial_sequences": paired_initial,
        "candidate_ranking": candidate_ranking,
        "strongest_structural_candidate": candidate_ranking[0] if candidate_ranking else None,
        "decision_rule_evaluation": decision_evaluation,
        "raw_sha256": dict(sorted(raw_sha256.items())),
    }
    audited_arm_names = [arm for arm, value in arm_reports.items() if value["audit_status"] == "audited_complete"]
    all_complete = len(audited_arm_names) == len(arms)
    expected_structures = declared_expected_structures
    cycle_00_x_counts = {
        arm: summary["original_cycle_00_x_counts"]
        for arm, summary in arm_summaries.items()
    }
    flat_x_counts = [count for by_run in cycle_00_x_counts.values() for count in by_run.values()]
    half_mask_preserved = bool(flat_x_counts) and all(count * 2 == binder_length for count in flat_x_counts)
    paired_equal = all(item["cycle_00_sequences_equal"] for item in paired_initial.values())
    provenance_passed = all(
        arm_reports[arm]["launch_provenance"]["scientific_snapshots_match_launch_manifest"]
        and arm_reports[arm]["launch_provenance"]["initial_binder_input_absent"]
        for arm in audited_arm_names
    )
    scientific_gate_name = "declared_balanced_trajectory_mean_rule_met" if decision_evaluation else "structural_target_candidate_present"
    scientific_gate_passed = (
        decision_evaluation["at_least_one_arm_meets_declared_rule"]
        if decision_evaluation
        else bool(candidate_ranking)
    )
    gate_checks = {
        "all_jobs_completed_and_declared_arms_audited": all_complete,
        "audited_structure_count_matches_declaration": len(all_rows) == expected_structures,
        "sequence_coordinate_confidence_cardinality_checks_passed": all_complete,
        "paired_cycle_00_sequences_equal": paired_equal,
        "cycle_00_half_x_mask_preserved": half_mask_preserved,
        "no_initial_binder_input": provenance_passed,
        "immutable_plan_and_scientific_snapshot_provenance_passed": provenance_passed,
        scientific_gate_name: scientific_gate_passed,
    }
    smoke_gate = {
        "schema": 1,
        "phase": args.phase,
        "passed": all(gate_checks.values()),
        "all_complete": all_complete,
        "checks": gate_checks,
        "declared_arms": list(arms),
        "audited_arms": audited_arm_names,
        "audited_structures": len(all_rows),
        "expected_structures": expected_structures,
        "binder_length": binder_length,
        "observed_cycle_00_x_counts": cycle_00_x_counts,
        "observed_cycle_00_x_fraction": {
            arm: {run: count / binder_length for run, count in by_run.items()}
            for arm, by_run in cycle_00_x_counts.items()
        },
        "paired_initial_sequences": paired_initial,
        "strongest_structural_candidate": report["strongest_structural_candidate"],
        "decision_rule_evaluation": decision_evaluation,
        "audit_report": "audit.json",
    }
    report.update(
        passed=smoke_gate["passed"],
        all_complete=all_complete,
        gate_checks=gate_checks,
        audited_structures=len(all_rows),
        expected_structures=expected_structures,
    )
    output_dir.mkdir(parents=True, exist_ok=True)
    report_path = output_dir / "audit.json"
    gate_path = output_dir / "smoke_passed.json"
    structure_path = output_dir / "audited_per_structure.csv"
    trajectory_path = output_dir / "audited_per_trajectory.csv"
    report_path.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n")
    gate_path.write_text(json.dumps(smoke_gate, indent=2, sort_keys=True) + "\n")
    write_csv(structure_path, all_rows)
    write_csv(trajectory_path, trajectory_rows)
    print(
        json.dumps(
            {
                "report": str(report_path),
                "gate": str(gate_path),
                "passed": smoke_gate["passed"],
                "audited_arms": audited_arm_names,
                "not_audited_or_failed_arms": {
                    arm: value["audit_status"]
                    for arm, value in arm_reports.items()
                    if value["audit_status"] != "audited_complete"
                },
                "audited_structures": len(all_rows),
                "strongest_structural_candidate": report["strongest_structural_candidate"],
            },
            indent=2,
        )
    )


if __name__ == "__main__":
    main()
