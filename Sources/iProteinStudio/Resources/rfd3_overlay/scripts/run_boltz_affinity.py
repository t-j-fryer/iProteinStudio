#!/usr/bin/env python3
"""Fold a directory of Boltz YAMLs (holo or apo) at throughput, chunked and resumable.

Reuses NanoHunter's ``nise_lib`` subprocess/sharding primitives
(``_boltz_cmd``, ``_run_parallel``/``run``, ``parse_prediction``) rather than
reimplementing Boltz invocation: each "shard" is one ``boltz predict
<yaml_dir> --out_dir <out_dir> --use_potentials`` process that loads the
model once and folds every YAML placed in its directory, and
``--parallel`` shards run those processes concurrently (NISE's own
model-reuse pattern -- see ``nise_lib.boltz_predict_batch``). This script
works directly off pre-written YAML files (from ``prepare_boltz_yaml.py``,
for both holo and apo) instead of ``boltz_predict_batch``'s own
sequence-to-YAML path, so the exact YAMLs on disk are what gets folded.

Because ``boltz predict --override`` has no per-file resume, this script
owns its own coarser-grained resumability: the input YAMLs are split into
fixed-size chunks, and a chunk is skipped once its manifest exists.

Boltz-2-with-affinity throughput on ligand workloads is NOT covered by
NanoHunter's shipped ``device_profile.json`` (protein-protein only), so
before the full run this script folds a small real shard at parallel=1 and
parallel=2 and keeps the faster -- pass --parallel explicitly to skip this
(e.g. for the much smaller apo re-fold, reusing holo's calibrated value).
"""

from __future__ import annotations

import argparse
import csv
import json
import sys
import time
import os
from pathlib import Path


def shard_and_predict(nise_lib, yaml_paths: list[Path], work_dir: Path, use_potentials: bool, parallel: int):
    work_dir.mkdir(parents=True, exist_ok=True)
    n_shards = max(1, min(parallel, len(yaml_paths)))
    shards: list[list[Path]] = [[] for _ in range(n_shards)]
    for i, path in enumerate(yaml_paths):
        shards[i % n_shards].append(path)

    cmds_and_logs = []
    shard_out_dirs = []
    for si, shard in enumerate(shards):
        if not shard:
            continue
        sdir = work_dir / (f"shard{si}" if n_shards > 1 else ".")
        yaml_dir, out_dir = sdir / "yaml", sdir / "out"
        yaml_dir.mkdir(parents=True, exist_ok=True)
        out_dir.mkdir(parents=True, exist_ok=True)
        for path in shard:
            link = yaml_dir / path.name
            if link.exists() or link.is_symlink():
                link.unlink()
            link.symlink_to(path.resolve())
        cmd = nise_lib._boltz_cmd(str(yaml_dir), str(out_dir), None, None, None, use_potentials=use_potentials)
        cmds_and_logs.append((cmd, sdir / "boltz.log"))
        shard_out_dirs.append((out_dir, [p.stem for p in shard]))

    if len(cmds_and_logs) == 1:
        cmd, log_path = cmds_and_logs[0]
        nise_lib.run(cmd, log_path=log_path)
    else:
        nise_lib._run_parallel(cmds_and_logs)

    results = {}
    for out_dir, names in shard_out_dirs:
        for name in names:
            pred = nise_lib.parse_prediction(out_dir, name)
            results[name] = pred
    return results


def prediction_row(name: str, pred, manifest_entry: dict, wall_sec: float) -> dict:
    row = {"name": name, "wall_sec": wall_sec, **manifest_entry}
    if pred is None:
        row["ok"] = False
        return row
    row["ok"] = True
    for field in ("complex_plddt", "iptm", "ligand_iptm", "ligand_plddt", "pbind", "pdb"):
        row[field] = getattr(pred, field, None)
    return row


def calibrate(nise_lib, yaml_paths: list[Path], calib_dir: Path, use_potentials: bool, calibrate_n: int) -> int:
    sample = yaml_paths[:calibrate_n]
    if len(sample) < 2:
        return 1
    best_parallel, best_rate = 1, 0.0
    for parallel in (1, 2):
        trial_dir = calib_dir / f"p{parallel}"
        started = time.time()
        shard_and_predict(nise_lib, sample, trial_dir, use_potentials, parallel)
        wall = time.time() - started
        rate = len(sample) / wall
        print(f"calibration parallel={parallel}: {wall:.1f}s for {len(sample)} designs ({wall/len(sample):.1f}s/design)")
        if rate > best_rate:
            best_parallel, best_rate = parallel, rate
    (calib_dir / "decision.json").write_text(
        json.dumps({"chosen_parallel": best_parallel, "designs_per_sec": best_rate}, indent=2) + "\n"
    )
    return best_parallel


def default_root() -> Path:
    """Where venvs/ and src/ live.

    From the environment the app sets, else this checkout's parent -- rfd3 is
    installed inside the pipeline root. Never a hard-coded home directory:
    that is one developer's machine, not the user's.
    """
    env = os.environ.get("NANOHUNTER_ROOT") or os.environ.get("IPROTEIN_ROOT")
    if env:
        return Path(env)
    # Installed layout is <root>/rfd3/scripts/, so the root is two levels up.
    # Verify rather than assume: a standalone checkout has no venvs/ above it,
    # and silently pointing at a home directory would be worse than saying so.
    candidate = Path(__file__).resolve().parents[2]
    if (candidate / "venvs").is_dir():
        return candidate
    raise SystemExit(
        "Cannot locate the pipeline root (no venvs/ found). "
        "Set NANOHUNTER_ROOT, or pass --nanohunter-root explicitly.")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--inputs", type=Path, required=True, help="dir of *.yaml + manifest.json")
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--chunk-size", type=int, default=50)
    parser.add_argument("--parallel", type=int, default=None, help="skip calibration and use this value")
    parser.add_argument("--calibrate-n", type=int, default=12)
    parser.add_argument("--use-potentials", action="store_true", default=True)
    parser.add_argument("--no-use-potentials", dest="use_potentials", action="store_false")
    parser.add_argument("--nanohunter-root", type=Path, default=default_root())
    args = parser.parse_args()

    nise_dir = args.nanohunter_root.resolve() / "scripts" / "nise"
    sys.path.insert(0, str(nise_dir))
    import nise_lib  # noqa: E402

    inputs = args.inputs.resolve()
    manifest_path = inputs / "manifest.json"
    manifest = json.loads(manifest_path.read_text()) if manifest_path.exists() else {}
    yaml_paths = sorted(inputs.glob("*.yaml"))
    if not yaml_paths:
        raise SystemExit(f"No YAML files in {inputs}")

    output = args.output.resolve()
    output.mkdir(parents=True, exist_ok=True)

    parallel = args.parallel
    if parallel is None:
        parallel = calibrate(nise_lib, yaml_paths, output / "_calibration", args.use_potentials, args.calibrate_n)
        print(f"calibration chose parallel={parallel}")

    chunks = [yaml_paths[i : i + args.chunk_size] for i in range(0, len(yaml_paths), args.chunk_size)]
    all_rows: list[dict] = []
    campaign_start = time.time()
    for ci, chunk in enumerate(chunks):
        chunk_dir = output / f"chunk_{ci:04d}"
        manifest_out = chunk_dir / "chunk_manifest.json"
        if manifest_out.exists():
            cached = json.loads(manifest_out.read_text())
            expected_names = {path.stem for path in chunk}
            cached_names = {row.get("name") for row in cached}
            if cached_names == expected_names and all(row.get("ok") for row in cached):
                all_rows.extend(cached)
                print(f"chunk {ci}: cached ({len(chunk)} successful designs)")
                continue
            print(f"chunk {ci}: incomplete/failed cache; rerunning")
        started = time.time()
        results = shard_and_predict(nise_lib, chunk, chunk_dir, args.use_potentials, parallel)
        wall = time.time() - started
        per_design = wall / len(chunk)
        rows = [
            prediction_row(path.stem, results.get(path.stem), manifest.get(path.stem, {}), per_design)
            for path in chunk
        ]
        manifest_out.write_text(json.dumps(rows, indent=2) + "\n")
        all_rows.extend(rows)
        failed = sum(1 for r in rows if not r["ok"])
        print(f"chunk {ci}: {len(chunk)} designs in {wall:.1f}s ({per_design:.1f}s/design), {failed} failed", flush=True)

    campaign_wall = time.time() - campaign_start
    fields = sorted({key for row in all_rows for key in row})
    with (output / "prediction_metrics.csv").open("w", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields)
        writer.writeheader()
        writer.writerows(all_rows)

    failures = sum(1 for row in all_rows if not row["ok"])
    run_manifest = {
        "num_designs": len(all_rows), "num_failures": failures, "parallel": parallel,
        "chunk_size": args.chunk_size, "use_potentials": args.use_potentials, "wall_sec": campaign_wall,
    }
    (output / "run_manifest.json").write_text(json.dumps(run_manifest, indent=2) + "\n")
    print(f"completed {len(all_rows)} predictions ({failures} failed) -> {output / 'prediction_metrics.csv'}")
    if failures:
        raise SystemExit(f"{failures} Boltz predictions failed; rerun to retry incomplete chunks")


if __name__ == "__main__":
    main()
