#!/usr/bin/env python3
"""Select checkpointed post-prediction tasks from an iterative summary."""

from __future__ import annotations

import argparse
import csv
from pathlib import Path


MODES = ("none", "all", "iptm", "final", "final-iptm")


def select_rows(summary: Path, mode: str, threshold: float, include_cycle00: bool):
    parsed: list[tuple[dict[str, str], int, int]] = []
    with summary.open(newline="") as handle:
        for row in csv.DictReader(handle):
            try:
                run = int(row["run"])
                cycle = int(row["cycle"])
            except (KeyError, TypeError, ValueError):
                continue
            if cycle == 0 and not include_cycle00:
                continue
            parsed.append((row, run, cycle))

    final_cycle: dict[int, int] = {}
    for _, run, cycle in parsed:
        final_cycle[run] = max(final_cycle.get(run, cycle), cycle)

    selected: list[tuple[int, int, str]] = []
    for row, run, cycle in parsed:
        if mode in {"final", "final-iptm"} and cycle != final_cycle[run]:
            continue
        if mode in {"iptm", "final-iptm"}:
            try:
                if float(row.get("iptm", "nan")) < threshold:
                    continue
            except (TypeError, ValueError):
                continue
        selected.append((run, cycle, row.get("binder_sequence", "")))
    return sorted(selected)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--summary", required=True, type=Path)
    parser.add_argument("--mode", required=True, choices=MODES)
    parser.add_argument("--threshold", required=True, type=float)
    parser.add_argument("--include-cycle00", choices=("0", "1"), default="0")
    parser.add_argument("--output", required=True, type=Path)
    args = parser.parse_args()

    rows = select_rows(args.summary, args.mode, args.threshold,
                       args.include_cycle00 == "1")
    args.output.parent.mkdir(parents=True, exist_ok=True)
    with args.output.open("w") as handle:
        for run, cycle, sequence in rows:
            handle.write(f"{run}\t{cycle}\t{sequence}\n")
    print(len(rows))


if __name__ == "__main__":
    main()
