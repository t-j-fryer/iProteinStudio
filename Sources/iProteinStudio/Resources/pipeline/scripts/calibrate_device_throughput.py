#!/usr/bin/env python3
"""User-invoked, no-energy throughput calibration for NanoHunter predictors.

The default campaign measures asymmetric two-chain complexes (an unaligned
binder plus a cached-MSA SUMO target) at several binder lengths.  At the exact
requested length it first learns a one-process native-batch plateau, then
searches process concurrency at that batch size, stopping when throughput no
longer improves or conservative unified-memory headroom is insufficient.  The
exact requested length is finally confirmed in two additional interleaved
blocks against its nearest process-count competitor.

No predictor arms overlap.  ``caffeinate -dimsu`` remains attached for the
campaign lifetime.  The script never invokes powermetrics or requests a sudo
password.
"""

from __future__ import annotations

import argparse
import json
import os
import random
import signal
import statistics
import subprocess
import time
from pathlib import Path
from typing import Any

import benchmark_sumo_predictors as base
import compute_throughput_profile as profile


REPO = Path(__file__).resolve().parent.parent
DEFAULT_ROOT = REPO / "output/device_throughput_calibration_20260808"
PROFILE_BUILDER = REPO / "scripts/compute_throughput_profile.py"
DEFAULT_STRATEGIES = (
    "boltz",
    "boltz_potentials",
    "intellifold",
    "alphafold3",
    "openfold",
)
DEFAULT_RECYCLES = {"boltz": 3, "intellifold": 10, "alphafold3": 10, "openfold": 3}


def deterministic_binder(length: int) -> str:
    # Standard residues only: every predictor receives the same valid sequence.
    alphabet = "ANGHFSYQDEKRTVILPMWC"
    return (alphabet * (length // len(alphabet) + 1))[:length]


def parse_ints(raw: str) -> list[int]:
    values = sorted({int(value.strip()) for value in raw.split(",") if value.strip()})
    if not values or min(values) < 1:
        raise argparse.ArgumentTypeError("lengths must be positive comma-separated integers")
    return values


def resolve_target_msa(requested: Path | None, target_sequence: str) -> Path:
    candidates = []
    if requested is not None:
        candidates.append(requested.expanduser().resolve())
    candidates.append(base.SUMO_MSA.resolve())
    candidates.extend(
        sorted(
            (REPO / "output").glob("**/target_full_msa.a3m"),
            key=lambda path: path.stat().st_mtime if path.exists() else 0,
            reverse=True,
        )
    )
    seen = set()
    for path in candidates:
        if path in seen or not path.is_file():
            continue
        seen.add(path)
        query, records = base.read_a3m_query(path)
        if query == target_sequence and records > 1:
            return path.resolve()
    raise SystemExit(
        "No cached full SUMO MSA was found. Generate it once with NanoHunter's "
        "native target-MSA calibration, then pass --target-msa PATH."
    )


def strategy_arm(
    strategy: str,
    stage: str,
    processes: int,
    length: int,
    batch: int,
    total_polymer_tokens: int,
) -> base.Arm:
    predictor = "boltz" if strategy == "boltz_potentials" else strategy
    return base.Arm(
        stage=stage,
        predictor=predictor,
        label=f"{strategy}_binder{length}_p{processes}_b{batch}",
        processes=processes,
        recycles=DEFAULT_RECYCLES[predictor],
        potentials=strategy == "boltz_potentials",
        af3_bucket=str(total_polymer_tokens),
        af3_async=False,
        intellifold_buckets=str(total_polymer_tokens),
        openfold_mlx=True,
    )


def annotate(
    root: Path,
    arm: base.Arm,
    row: dict[str, Any],
    strategy: str,
    binder_length: int,
    target_length: int,
    target_msa: Path,
    batch_per_process: int,
    phase: str,
    block: int,
) -> None:
    row.update(
        {
            "strategy": strategy,
            "workload_class": "binder_target",
            "binder_length": binder_length,
            "target_length": target_length,
            "total_polymer_tokens": binder_length + target_length,
            "ligand_atoms": 0,
            "chain_count": 2,
            "binder_msa_depth": 1,
            "target_msa_depth": base.read_a3m_query(target_msa)[1],
            "native_batch_per_process": batch_per_process,
            "total_inputs": arm.processes * batch_per_process,
            "phase": phase,
            "block": block,
            "energy_monitored": False,
            "calibration_schema_version": 2,
        }
    )
    base.append_row(root / "benchmark_results.csv", row)
    base.atomic_json(root / "arms" / arm.key / "complete.json", row)
    base.atomic_json(root / "arms" / arm.key / row["attempt"] / "result.json", row)


def memory_allows(
    observed_rows: list[dict[str, Any]],
    processes: int,
    reserve_gb: float,
) -> bool:
    """Project only the next unmeasured process from observed memory growth.

    The previous implementation multiplied the p1 peak (plus a 20% margin) by
    the full requested process count.  That repeatedly charged fixed model and
    framework memory and could reject p2 without measuring it.  Instead, retain
    the observed peak and apply the safety margin only to the next incremental
    process.  Once p2 exists, its measured growth informs p3, and so on.
    """
    valid = sorted(
        (
            row for row in observed_rows
            if int(row.get("processes") or 0) > 0
            and float(row.get("peak_effective_unified_memory_mb") or 0) > 0
        ),
        key=lambda row: int(row["processes"]),
    )
    if not valid:
        return False
    latest = valid[-1]
    latest_processes = int(latest["processes"])
    if processes <= latest_processes:
        return True
    latest_peak = float(latest["peak_effective_unified_memory_mb"])
    average_increment = latest_peak / latest_processes
    observed_increment = average_increment
    if len(valid) >= 2:
        previous = valid[-2]
        process_delta = latest_processes - int(previous["processes"])
        if process_delta > 0:
            observed_increment = max(
                0.0,
                (latest_peak - float(previous["peak_effective_unified_memory_mb"]))
                / process_delta,
            )
    # Avoid trusting a spuriously small marginal measurement: fixed overhead
    # may be shared, but each extra process still receives at least the measured
    # average-per-process allowance before the 20% next-step margin.
    incremental = max(observed_increment, average_increment)
    projected = latest_peak + incremental * (processes - latest_processes) * 1.20
    live_mb = base.available_kb() / 1024
    return projected + reserve_gb * 1024 <= live_mb


def row_is_memory_safe(row: dict[str, Any], reserve_gb: float) -> bool:
    """Reject settings that swapped or consumed the user's live reserve."""
    swap_growth = profile.swap_used_mb(row.get("swap_end")) - profile.swap_used_mb(
        row.get("swap_start")
    )
    if swap_growth > 128:
        return False
    peak = float(row.get("peak_effective_unified_memory_mb") or 0)
    live_mb = base.available_kb() / 1024
    return peak + reserve_gb * 1024 <= live_mb


def choose_native_batch(rows: list[dict[str, Any]]) -> int:
    """Choose the lowest-memory native batch within 3% of best throughput."""
    valid = [row for row in rows if float(row.get("sec_per_prediction") or 0) > 0]
    if not valid:
        raise RuntimeError("Native-batch screening produced no valid rows")
    grouped: dict[int, list[dict[str, Any]]] = {}
    for row in valid:
        grouped.setdefault(int(row["native_batch_per_process"]), []).append(row)
    summaries = [
        {
            "native_batch_per_process": batch,
            "sec_per_prediction": statistics.median(
                float(row["sec_per_prediction"]) for row in group
            ),
            "peak_effective_unified_memory_mb": max(
                float(row.get("peak_effective_unified_memory_mb") or 0)
                for row in group
            ),
        }
        for batch, group in grouped.items()
    ]
    fastest = min(summaries, key=lambda row: float(row["sec_per_prediction"]))
    near = [
        row
        for row in summaries
        if float(row["sec_per_prediction"])
        <= float(fastest["sec_per_prediction"]) * 1.03
    ]
    chosen = min(
        near,
        key=lambda row: (
            float(row.get("peak_effective_unified_memory_mb") or float("inf")),
            int(row["native_batch_per_process"]),
        ),
    )
    return int(chosen["native_batch_per_process"])


def run_setting(
    root: Path,
    sources: dict[tuple[int, int], dict[str, Path]],
    target_sequence: str,
    target_msa: Path,
    strategy: str,
    binder_length: int,
    processes: int,
    batch: int,
    phase: str,
    block: int,
    allow_contention: bool,
) -> dict[str, Any]:
    total = processes * batch
    arm = strategy_arm(
        strategy,
        f"{phase}_{strategy}_l{binder_length}_b{block:02d}",
        processes,
        binder_length,
        batch,
        binder_length + len(target_sequence),
    )
    row = base.run_arm(
        root,
        arm,
        sources[(binder_length, total)],
        target_sequence,
        target_msa,
        total,
        allow_contention,
    )
    annotate(
        root,
        arm,
        row,
        strategy,
        binder_length,
        len(target_sequence),
        target_msa,
        batch,
        phase,
        block,
    )
    return row


def speed_gain(reference: dict[str, Any], candidate: dict[str, Any]) -> float:
    if (
        profile.swap_used_mb(candidate.get("swap_end"))
        - profile.swap_used_mb(candidate.get("swap_start"))
        > 128
    ):
        return float("-inf")
    return 100.0 * (
        float(reference["sec_per_prediction"]) / float(candidate["sec_per_prediction"])
        - 1.0
    )


def write_manifest(
    root: Path,
    args: argparse.Namespace,
    lengths: list[int],
    target_sequence: str,
    target_msa: Path,
) -> None:
    base.atomic_json(
        root / "benchmark_manifest.json",
        {
            "purpose": "per-device adaptive throughput calibration",
            "energy_monitoring": False,
            "workload_class": "binder_target",
            "binder_lengths": lengths,
            "largest_length_is_p1_memory_probe_only": max(lengths) != args.exact_length,
            "exact_binder_length": args.exact_length,
            "target": "SUMO",
            "target_length": len(target_sequence),
            "target_msa": str(target_msa),
            "target_msa_records": base.read_a3m_query(target_msa)[1],
            "strategies": list(args.strategies),
            "native_batch_candidates": list(args.native_batches),
            "fixed_native_batch": args.native_batch,
            "maximum_processes": args.max_processes,
            "expansion_gain_percent": args.expansion_gain_percent,
            "confirmation_blocks": args.confirm_blocks,
            "native_batch_confirmation_blocks": args.batch_confirm_blocks,
            "memory_reserve_gb": args.memory_reserve_gb,
            "fixed_defaults": {
                "recycles": DEFAULT_RECYCLES,
                "sampling_steps": 200,
                "diffusion_samples": 1,
                "bucket_policy": "exact total-polymer length per calibration workload",
                "af3_async_dispatch": False,
                "af3_compilation_cache": True,
                "intellifold_omp_threads": 1,
                "openfold_mlx_kernels": True,
            },
            "machine": base.machine_state(),
            "git_head": base.run_capture(["git", "rev-parse", "HEAD"], cwd=REPO),
        },
    )


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out-dir", type=Path, default=DEFAULT_ROOT)
    parser.add_argument("--target-msa", type=Path)
    parser.add_argument("--lengths", default="50,100,200,400")
    parser.add_argument("--exact-length", type=int, default=100)
    parser.add_argument("--strategies", default=",".join(DEFAULT_STRATEGIES))
    parser.add_argument(
        "--native-batches",
        default="1,2,4,8,16",
        help="candidate one-process native batches; searched adaptively",
    )
    parser.add_argument(
        "--native-batch",
        type=int,
        help="fix native batch instead of calibrating it (advanced/compatibility)",
    )
    parser.add_argument("--max-processes", type=int, default=4)
    parser.add_argument("--expansion-gain-percent", type=float, default=3.0)
    parser.add_argument("--confirm-blocks", type=int, default=2)
    parser.add_argument("--batch-confirm-blocks", type=int, default=1)
    parser.add_argument(
        "--memory-reserve-gb",
        type=float,
        default=8.0,
        help=(
            "live unified-memory reserve (default: 8 GiB; 4 GiB is an "
            "aggressive dedicated-machine setting)"
        ),
    )
    parser.add_argument("--cooldown", type=int, default=20)
    parser.add_argument("--allow-contention", action="store_true")
    args = parser.parse_args()
    lengths = parse_ints(args.lengths)
    if args.exact_length not in lengths:
        lengths.append(args.exact_length)
        lengths.sort()
    native_batches = parse_ints(args.native_batches)
    if args.native_batch is not None:
        if args.native_batch < 1:
            raise SystemExit("native batch must be positive")
        native_batches = [args.native_batch]
    args.native_batches = tuple(native_batches)
    args.strategies = tuple(
        value.strip() for value in str(args.strategies).split(",") if value.strip()
    )
    unknown = set(args.strategies) - set(DEFAULT_STRATEGIES)
    if unknown:
        raise SystemExit(f"Unknown strategies: {sorted(unknown)}")
    if args.max_processes < 1:
        raise SystemExit("max processes must be positive")
    if args.confirm_blocks < 1 or args.batch_confirm_blocks < 1:
        raise SystemExit("confirmation block counts must be positive")

    root = args.out_dir.resolve()
    root.mkdir(parents=True, exist_ok=True)
    base.atomic_text(root / "campaign.pid", f"{os.getpid()}\n")
    base.PLOTTER = root / "disabled_incremental_plotter"
    base.COOLDOWN_SEC = args.cooldown
    target_sequence = base.read_sumo_sequence()
    target_msa = resolve_target_msa(args.target_msa, target_sequence)
    query, _ = base.read_a3m_query(target_msa)
    if query != target_sequence:
        raise SystemExit("Cached target MSA query does not match SUMO target")
    write_manifest(root, args, lengths, target_sequence, target_msa)

    # Include local neighbours around powers of two so an observed plateau can
    # be refined without rebuilding inputs.  The largest candidate is only
    # reached when each preceding doubling materially improves throughput.
    candidate_batches = sorted(
        set(native_batches)
        | {value - 1 for value in native_batches if value > 2}
        | {value + 1 for value in native_batches if value < max(native_batches)}
    )
    totals = {
        processes * batch
        for processes in range(1, args.max_processes + 1)
        for batch in candidate_batches
    }
    sources = {
        (length, total): base.make_complex_inputs(
            root / f"source_binder{length}_n{total}",
            deterministic_binder(length),
            target_sequence,
            target_msa,
            total,
        )
        for length in lengths
        for total in totals
    }

    def interrupted(signum: int, _frame: Any) -> None:
        raise KeyboardInterrupt(f"received signal {signum}")

    signal.signal(signal.SIGTERM, interrupted)
    signal.signal(signal.SIGINT, interrupted)
    caffeinate = subprocess.Popen(
        ["caffeinate", "-dimsu", "-w", str(os.getpid())],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
    base.atomic_text(root / "caffeinate.pid", f"{caffeinate.pid}\n")

    decisions: dict[str, Any] = {}
    try:
        for strategy in args.strategies:
            print(f"=== calibrating {strategy} (no overlapping predictors) ===", flush=True)
            # One excluded p1/b1 warmup populates model/JIT caches without
            # making a scheduling decision from cold-start behavior.
            old_cooldown = base.COOLDOWN_SEC
            base.COOLDOWN_SEC = 0
            run_setting(
                root,
                sources,
                target_sequence,
                target_msa,
                strategy,
                args.exact_length,
                1,
                1,
                "warmup",
                0,
                args.allow_contention,
            )
            base.COOLDOWN_SEC = old_cooldown

            batch_rows: list[dict[str, Any]] = []
            if args.native_batch is not None:
                batches_to_run = [args.native_batch]
                batch_rows.append(
                    run_setting(
                        root, sources, target_sequence, target_msa, strategy,
                        args.exact_length, 1, args.native_batch, "batch_screen", 1,
                        args.allow_contention,
                    )
                )
            else:
                # Coarse powers-of-two search.  Always establish 1/2/4, then
                # continue doubling only while the previous step gains >=3%.
                batches_to_run = []
                previous: dict[str, Any] | None = None
                for batch in native_batches:
                    if batch > 4 and previous is not None and len(batch_rows) >= 2:
                        if speed_gain(batch_rows[-2], batch_rows[-1]) < args.expansion_gain_percent:
                            break
                    row = run_setting(
                        root, sources, target_sequence, target_msa, strategy,
                        args.exact_length, 1, batch, "batch_screen", 1,
                        args.allow_contention,
                    )
                    batch_rows.append(row)
                    batches_to_run.append(batch)
                    previous = row

                coarse_choice = choose_native_batch(batch_rows)
                measured = set(batches_to_run)
                neighbours = [
                    value
                    for value in (coarse_choice - 1, coarse_choice + 1)
                    if value >= 1 and value in candidate_batches and value not in measured
                ]
                for batch in neighbours:
                    batch_rows.append(
                        run_setting(
                            root, sources, target_sequence, target_msa, strategy,
                            args.exact_length, 1, batch, "batch_refine", 1,
                            args.allow_contention,
                        )
                    )

            safe_batch_rows = [
                row for row in batch_rows if row_is_memory_safe(row, args.memory_reserve_gb)
            ]
            preliminary_batch = choose_native_batch(safe_batch_rows or batch_rows)
            alternatives = [
                row for row in (safe_batch_rows or batch_rows)
                if int(row["native_batch_per_process"]) != preliminary_batch
            ]
            batch_confirmation = [preliminary_batch]
            if alternatives:
                batch_confirmation.append(choose_native_batch(alternatives))
            batch_confirmation = sorted(set(batch_confirmation))
            for block in range(1, args.batch_confirm_blocks + 1):
                order = batch_confirmation.copy()
                random.Random(20260880 + block).shuffle(order)
                for batch in order:
                    batch_rows.append(
                        run_setting(
                            root, sources, target_sequence, target_msa, strategy,
                            args.exact_length, 1, batch, "batch_confirm", block,
                            args.allow_contention,
                        )
                    )
            safe_batch_rows = [
                row for row in batch_rows if row_is_memory_safe(row, args.memory_reserve_gb)
            ]
            selected_batch = choose_native_batch(safe_batch_rows or batch_rows)
            print(
                f"=== {strategy}: selected native batch {selected_batch} for concurrency search ===",
                flush=True,
            )

            screened: dict[int, list[dict[str, Any]]] = {}
            largest = max(lengths)
            screen_lengths = [length for length in lengths if length != largest]
            random.Random(20260920 + list(args.strategies).index(strategy)).shuffle(screen_lengths)
            screen_lengths.append(largest)
            for length in screen_lengths:
                rows = []
                p1 = run_setting(
                    root, sources, target_sequence, target_msa, strategy,
                    length, 1,
                    1 if length == largest and length != args.exact_length else selected_batch,
                    "screen", 1,
                    args.allow_contention,
                )
                rows.append(p1)
                # The largest shape is an upper-memory/scaling probe. Searching
                # multiple processes there is disproportionately expensive and
                # unsafe; 50/100/200-aa probes still map length-dependent optima.
                search_concurrency = length != largest or length == args.exact_length
                if (
                    search_concurrency
                    and args.max_processes >= 2
                    and memory_allows(rows, 2, args.memory_reserve_gb)
                ):
                    previous = run_setting(
                        root, sources, target_sequence, target_msa, strategy,
                        length, 2, selected_batch, "screen", 1,
                        args.allow_contention,
                    )
                    rows.append(previous)
                    processes = 3
                    while processes <= args.max_processes:
                        # At the exact requested design length, map every safe
                        # process count through p4.  This guards against a flat
                        # p3 followed by a p4 recovery (seen in earlier
                        # IntelliFold measurements). Other lengths retain the
                        # efficient >=3% adaptive expansion rule.
                        if (
                            length != args.exact_length
                            and speed_gain(rows[-2], rows[-1])
                            < args.expansion_gain_percent
                        ):
                            break
                        if not memory_allows(rows, processes, args.memory_reserve_gb):
                            break
                        candidate = run_setting(
                            root, sources, target_sequence, target_msa, strategy,
                            length, processes, selected_batch, "screen", 1,
                            args.allow_contention,
                        )
                        rows.append(candidate)
                        if not row_is_memory_safe(candidate, args.memory_reserve_gb):
                            break
                        previous = candidate
                        processes += 1
                screened[length] = rows

            exact_rows = screened[args.exact_length]
            safe_exact_rows = [
                row
                for row in exact_rows
                if profile.swap_used_mb(row.get("swap_end"))
                - profile.swap_used_mb(row.get("swap_start"))
                <= 128
            ]
            ordered = sorted(
                safe_exact_rows or exact_rows,
                key=lambda row: float(row["sec_per_prediction"]),
            )
            winner = ordered[0]
            competitor = ordered[1] if len(ordered) > 1 else ordered[0]
            confirmation_settings = sorted(
                {int(winner["processes"]), int(competitor["processes"])}
            )
            for block in range(1, args.confirm_blocks + 1):
                order = confirmation_settings.copy()
                random.Random(20260900 + block).shuffle(order)
                for processes in order:
                    run_setting(
                        root, sources, target_sequence, target_msa, strategy,
                        args.exact_length, processes, selected_batch,
                        "confirm", block, args.allow_contention,
                    )
            decisions[strategy] = {
                "native_batch_rows": [
                    {
                        "batch": int(row["native_batch_per_process"]),
                        "seconds_per_prediction": float(row["sec_per_prediction"]),
                        "peak_memory_mb": float(row["peak_effective_unified_memory_mb"]),
                    }
                    for row in batch_rows
                ],
                "selected_native_batch": selected_batch,
                "native_batch_confirmation_candidates": batch_confirmation,
                "screened_processes_by_length": {
                    str(length): [int(row["processes"]) for row in rows]
                    for length, rows in screened.items()
                },
                "exact_screen_winner_processes": int(winner["processes"]),
                "confirmation_processes": confirmation_settings,
            }
            base.atomic_json(root / "decisions.json", decisions)

        profile_path = root / "device_profile.json"
        built = profile.build_profile(
            root / "benchmark_results.csv",
            profile_path,
            root / "benchmark_manifest.json",
        )
        base.atomic_json(
            root / "campaign_complete.json",
            {
                "completed": time.strftime("%Y-%m-%dT%H:%M:%S%z"),
                "profile": str(profile_path),
                "profile_schedule_rows": len(built["schedules"]),
            },
        )
        print(f"Device calibration complete: {profile_path}", flush=True)
    finally:
        if caffeinate.poll() is None:
            caffeinate.terminate()


if __name__ == "__main__":
    main()
