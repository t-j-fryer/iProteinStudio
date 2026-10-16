#!/usr/bin/env python3
"""Batch CPU-only output reporting without changing predictor or sampling settings."""
from __future__ import annotations

import argparse
from concurrent.futures import ProcessPoolExecutor
from contextlib import redirect_stdout
import json
import multiprocessing
from pathlib import Path
import sys

from storage_policy import relative_symlink
from validate_prediction_geometry import report_and_validate


def confidence_metrics(path: Path) -> tuple[float, float]:
    """Preserve the shell runner's key precedence and missing-value convention."""
    try:
        with path.open() as handle:
            data = json.load(handle)
    except (OSError, ValueError):
        return float("nan"), float("nan")

    def get_any(obj, keys):
        if isinstance(obj, dict):
            for key, value in obj.items():
                if key.lower() in keys:
                    return value
            values = obj.values()
        elif isinstance(obj, list):
            values = obj
        else:
            return None
        for value in values:
            found = get_any(value, keys)
            if found is not None:
                return found
        return None

    def number(value):
        try:
            return float(value)
        except (ValueError, TypeError, OverflowError):
            return float("nan")

    return (number(get_any(data, {"iptm", "i_ptm", "iptm_score", "iptm+ptm"})),
            number(get_any(data, {"complex_plddt", "avg_plddt", "plddt"})))


def finalize_item(request: tuple) -> None:
    item, log, predictor, start, end, duration = request
    structure, confidence, normalized, predictor_directory = item
    source = Path(structure)
    pred_min, predictor_dir = Path(normalized), Path(predictor_directory)
    pred_min.mkdir(parents=True, exist_ok=True)
    predictor_dir.mkdir(parents=True, exist_ok=True)
    relative_symlink(Path(log), predictor_dir / "predict.log", replace=True)
    if confidence and Path(confidence) != pred_min / "confidence.json":
        relative_symlink(Path(confidence), pred_min / "confidence.json", replace=True)
    normalized_structure = pred_min / ("model_0.cif" if source.suffix == ".cif" else "model_0.pdb")
    if source != normalized_structure:
        relative_symlink(source, normalized_structure, replace=True)
    (pred_min / "predictor.txt").write_text(predictor + "\n")
    # Preserve CIF-first selection and report paths used by the shell contract.
    selected = pred_min / "model_0.cif"
    if not selected.is_file():
        selected = pred_min / "model_0.pdb"
    with redirect_stdout(sys.stderr):
        report_and_validate(selected, pred_min / "geometry_report.json")
    if (pred_min / "confidence.json").is_file():
        iptm, _ = confidence_metrics(pred_min / "confidence.json")
        (pred_min / "iptm.txt").write_text(f"{iptm}\n")
    # No timing/completion-related files for an item whose validation failed.
    for name, value in (("start", start), ("end", end), ("duration", duration)):
        (pred_min / f"wave_predict_{name}.txt").write_text(value + "\n")


def finalize(items, log, predictor, start, end, duration, workers=1):
    destinations = [str(Path(item[2]).resolve()) for item in items]
    if len(set(destinations)) != len(destinations):
        raise ValueError("duplicate normalized output destinations")
    requests = [(item, log, predictor, start, end, duration) for item in items]
    if workers == 1:
        for request in requests:
            finalize_item(request)
    else:
        # Spawn a bounded, CPU-only pool; never fork a loaded GPU interpreter.
        # Opt-in for offline qualification; the production runner uses one.
        with ProcessPoolExecutor(max_workers=min(workers, len(requests)),
                                 mp_context=multiprocessing.get_context("spawn")) as pool:
            list(pool.map(finalize_item, requests))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)
    metrics = commands.add_parser("metrics")
    metrics.add_argument("paths", nargs="+", type=Path)
    batch = commands.add_parser("finalize")
    batch.add_argument("--item", nargs=4, action="append", required=True,
                       metavar=("STRUCTURE", "CONFIDENCE", "PRED_MIN", "PREDICTOR_DIR"))
    for name in ("log", "predictor", "start", "end", "duration"):
        batch.add_argument("--" + name, required=True)
    batch.add_argument("--workers", type=int, choices=range(1, 5), default=1)
    args = parser.parse_args()
    if args.command == "metrics":
        for path in args.paths:
            print("%s,%s" % confidence_metrics(path))
    else:
        finalize(args.item, args.log, args.predictor, args.start, args.end,
                 args.duration, args.workers)


if __name__ == "__main__":
    main()
