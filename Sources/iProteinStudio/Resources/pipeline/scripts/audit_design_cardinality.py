#!/usr/bin/env python3
"""Verify that an iterative campaign produced its requested design budget.

Cycle 00 is an unoptimized starting structure. It is reported separately and
never included in ``actual_optimized_designs``.
"""

from __future__ import annotations

import argparse
import json
import os
import re
import sys
import tempfile
from pathlib import Path


RUN_PATTERN = re.compile(r"run_[0-9]{3}$")


def prediction_complete(cycle_dir: Path) -> bool:
    pred_min = cycle_dir / "pred_min"
    return (pred_min / "model_0.cif").is_file() or (pred_min / "model_0.pdb").is_file()


def audit(root: Path, trajectories: int, cycles: int) -> dict[str, object]:
    if trajectories < 1:
        raise ValueError("trajectories must be at least 1")
    if cycles < 0:
        raise ValueError("cycles cannot be negative")

    actual_runs = sum(path.is_dir() and RUN_PATTERN.fullmatch(path.name) is not None
                      for path in root.iterdir()) if root.is_dir() else 0
    actual_starts = 0
    actual_designs = 0
    missing: list[str] = []
    for run_index in range(1, trajectories + 1):
        run_tag = f"run_{run_index:03d}"
        for cycle in range(cycles + 1):
            relative = Path(run_tag) / f"cycle_{cycle:02d}"
            if prediction_complete(root / relative):
                if cycle == 0:
                    actual_starts += 1
                else:
                    actual_designs += 1
            else:
                missing.append(relative.as_posix())

    expected_starts = trajectories
    expected_designs = trajectories * cycles
    expected_total = trajectories * (cycles + 1)
    actual_total = actual_starts + actual_designs
    complete = (
        actual_runs == trajectories
        and actual_starts == expected_starts
        and actual_designs == expected_designs
        and actual_total == expected_total
    )
    return {
        "schema_version": 1,
        "status": "complete" if complete else "failed",
        "cycle_00_counts_as_design": False,
        "expected_trajectories": trajectories,
        "expected_starting_structures": expected_starts,
        "expected_optimized_designs": expected_designs,
        "expected_total_checkpoints": expected_total,
        "actual_trajectory_directories": actual_runs,
        "actual_starting_structures": actual_starts,
        "actual_optimized_designs": actual_designs,
        "actual_total_checkpoints": actual_total,
        "missing": missing,
    }


def write_atomic(path: Path, payload: dict[str, object]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, temporary = tempfile.mkstemp(prefix=f".{path.name}.", dir=path.parent)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            json.dump(payload, handle, indent=2, sort_keys=True)
            handle.write("\n")
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary, path)
    except BaseException:
        try:
            os.unlink(temporary)
        except FileNotFoundError:
            pass
        raise


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", type=Path, required=True)
    parser.add_argument("--trajectories", type=int, required=True)
    parser.add_argument("--cycles", type=int, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    try:
        result = audit(args.root, args.trajectories, args.cycles)
        write_atomic(args.output, result)
    except (OSError, ValueError) as error:
        parser.error(str(error))
    if result["status"] != "complete":
        print(
            "Design cardinality audit failed: "
            f"requested {result['expected_trajectories']} trajectories x "
            f"{args.cycles} optimized cycles "
            f"({result['expected_optimized_designs']} designs, cycle 00 excluded), "
            f"found {result['actual_trajectory_directories']} trajectory directories "
            f"and {result['actual_optimized_designs']} optimized structures. "
            f"See {args.output}.",
            file=sys.stderr,
        )
        return 1
    print(
        f">>> Cardinality verified: {result['actual_optimized_designs']}/"
        f"{result['expected_optimized_designs']} optimized designs plus "
        f"{result['actual_starting_structures']}/"
        f"{result['expected_starting_structures']} cycle-00 starts"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
