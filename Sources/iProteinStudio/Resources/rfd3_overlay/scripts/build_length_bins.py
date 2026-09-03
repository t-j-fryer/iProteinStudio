#!/usr/bin/env python3
"""Build one RFD3 fixture per length bin spanning a binder length range.

RFD3's MLX sampler natively batches many trajectories from ONE fixture, but a
fixture is frozen at a single binder length -- "different lengths cannot
share a native tensor batch" (see README "Apple-Silicon performance"). To
cover a length range with a fixed total design budget, this script slices
the range into evenly spaced discrete bins, writes one per-bin
DesignInputSpecification JSON (the shared ligand-conditioning fragment from
``prepare_ligand_target.py`` plus that bin's ``length``), and calls
``milestone0_oracle.py`` once per bin to export its fixture. This is also the
fail-fast validation point for the conditioning spec: a bad atom name/chain
key raises immediately here, before any GPU time is spent sampling.
"""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def bin_lengths(min_length: int, max_length: int, num_bins: int) -> list[int]:
    if num_bins < 1:
        raise SystemExit("--num-bins must be >= 1")
    if num_bins == 1:
        return [min_length]
    step = (max_length - min_length) / (num_bins - 1)
    lengths = sorted({round(min_length + step * i) for i in range(num_bins)})
    return lengths


def allocate_quota(num_designs: int, num_bins: int) -> list[int]:
    base, remainder = divmod(num_designs, num_bins)
    return [base + (1 if i < remainder else 0) for i in range(num_bins)]


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--base-json", type=Path, required=True, help="from prepare_ligand_target.py")
    parser.add_argument("--design-name", default="dtf401", help="top-level key inside --base-json")
    parser.add_argument("--ligand-manifest", type=Path, required=True, help="atom_selections.json, for ccd_mirror")
    parser.add_argument("--output", type=Path, required=True, help="campaign root, e.g. campaigns/dTF401")
    parser.add_argument("--min-length", type=int, default=65)
    parser.add_argument("--max-length", type=int, default=150)
    parser.add_argument("--num-bins", type=int, default=10)
    parser.add_argument("--num-designs", type=int, default=1000)
    parser.add_argument("--timesteps", type=int, default=200)
    parser.add_argument("--n-recycle", type=int, default=2)
    parser.add_argument("--seed-base", type=int, default=0)
    parser.add_argument("--overwrite", action="store_true")
    args = parser.parse_args()

    base = json.loads(args.base_json.read_text())
    if args.design_name not in base:
        raise SystemExit(f"{args.design_name!r} not found in {args.base_json} (keys: {list(base)})")
    design_input = base[args.design_name]

    ligand_manifest = json.loads(args.ligand_manifest.read_text())
    ccd_mirror = ligand_manifest["ccd_mirror"]

    lengths = bin_lengths(args.min_length, args.max_length, args.num_bins)
    quotas = allocate_quota(args.num_designs, len(lengths))

    output = args.output.resolve()
    rfd3_dir = output / "rfd3"
    rfd3_dir.mkdir(parents=True, exist_ok=True)
    oracle_dir = rfd3_dir / "fixtures"
    oracle_dir.mkdir(parents=True, exist_ok=True)

    env = os.environ.copy()
    env.update({"DEBUG": "false", "TOKENIZERS_PARALLELISM": "false", "CCD_MIRROR_PATH": ccd_mirror})

    bins = []
    for i, (length, quota) in enumerate(zip(lengths, quotas, strict=True)):
        name = f"{args.design_name}_L{length}"
        input_json_path = oracle_dir / f"input_{name}.json"
        fixture_path = oracle_dir / f"oracle_{name}.npz"
        spec = dict(design_input)
        spec["length"] = f"{length}-{length}"
        input_json_path.write_text(json.dumps({name: spec}, indent=2) + "\n")

        if fixture_path.exists() and not args.overwrite:
            print(f"bin {i} (L={length}): fixture cached -> {fixture_path}")
        else:
            cmd = [
                sys.executable, str(ROOT / "milestone0_oracle.py"),
                "--name", name, "--input_json", str(input_json_path),
                "--timesteps", str(args.timesteps), "--n_recycle", str(args.n_recycle),
                "--seed", str(args.seed_base + i),
                "--output-dir", str(oracle_dir),
            ]
            started = time.time()
            log_path = rfd3_dir / f"fixture_{name}.log"
            with log_path.open("w") as handle:
                result = subprocess.run(cmd, cwd=ROOT, env=env, stdout=handle, stderr=subprocess.STDOUT)
            if result.returncode:
                raise SystemExit(f"milestone0_oracle.py failed for bin {i} (L={length}); see {log_path}")
            print(f"bin {i} (L={length}): fixture built in {time.time() - started:.1f}s -> {fixture_path}")

        bins.append(
            {
                "bin_index": i,
                "length": length,
                "quota": quota,
                "name": name,
                "input_json": str(input_json_path),
                "fixture": str(fixture_path),
                "seed": args.seed_base + i,
            }
        )

    manifest = {
        "design_name": args.design_name,
        "component_id": design_input.get("ligand"),
        "ccd_mirror": ccd_mirror,
        "num_designs": args.num_designs,
        "min_length": args.min_length,
        "max_length": args.max_length,
        "timesteps": args.timesteps,
        "n_recycle": args.n_recycle,
        "bins": bins,
    }
    (rfd3_dir / "bin_manifest.json").write_text(json.dumps(manifest, indent=2) + "\n")
    print(f"wrote {len(bins)} bins ({sum(quotas)} designs total) -> {rfd3_dir / 'bin_manifest.json'}")


if __name__ == "__main__":
    main()
