#!/usr/bin/env python3
"""Design N LASErMPNN sequences per RFD3 backbone, using NISE's exact settings.

Reuses NanoHunter's ``scripts/nise/nise_lib.py`` by import rather than
reimplementing its LASErMPNN invocation: that module is a dependency-light
(stdlib + numpy), import-side-effect-free library already used in production
by the NISE campaign, so calling ``nise_lib.lasermpnn_design`` directly keeps
this pipeline's inverse-folding step bit-for-bit identical to NISE's own,
just with ``n_designs`` set to 4 (NISE's own default is 64/lineage/cycle).

The ligand pose LASErMPNN protonates comes straight from each RFD3 backbone's
own chain-B HETATM coordinates (``generate_backbones.py``'s ``Fixture.write_pdb``
bakes the fixed ligand token coordinates into every design) -- no separate
ligand-placement step is needed.

LASErMPNN is CPU-only and has no seed/RNG argument (not run-to-run
reproducible), so backbones are processed concurrently with a plain thread
pool -- safe alongside a live MPS campaign since this never touches the GPU.
"""

from __future__ import annotations

import argparse
import csv
import json
import sys
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path


def _read_fasta_count(fasta_path: Path) -> int:
    # LASErMPNN's designs.fasta has one ">...score=..." header per design
    # (verified: no separate native-sequence record, unlike LigandMPNN's output).
    if not fasta_path.exists():
        return 0
    return sum(1 for line in fasta_path.read_text().splitlines() if line.startswith(">"))


def design_one(nise_lib, backbone: Path, out_dir: Path, args) -> list[dict]:
    fasta = out_dir / "designs" / "designs.fasta"
    if not args.overwrite and _read_fasta_count(fasta) >= args.n_seqs:
        pairs = sorted(nise_lib._read_lasermpnn_fasta(fasta), key=lambda x: x[1], reverse=True)[: args.n_seqs]
    else:
        pairs = nise_lib.lasermpnn_design(
            str(backbone), out_dir, args.n_seqs, args.smiles,
            seq_temp=args.seq_temp, fs_temp=args.fs_temp, fs_distance=args.fs_distance,
            ala_budget=args.ala_budget, gly_budget=args.gly_budget,
            constrain_ss=not args.no_constrain_ss, designed="all", device="cpu",
        )
    return [
        {
            "design": backbone.stem, "seq_index": i, "sequence": seq,
            "sequence_length": len(seq), "laser_score": score, "backbone_pdb": str(backbone),
        }
        for i, (seq, score) in enumerate(pairs)
    ]


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--backbones", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--smiles", required=True)
    parser.add_argument("--n-seqs", type=int, default=4)
    parser.add_argument("--max-parallel", type=int, default=6)
    parser.add_argument("--nanohunter-root", type=Path, default=Path("/Users/thomasfryer/NanoHunter"))
    parser.add_argument("--seq-temp", type=float, default=0.5)
    parser.add_argument("--fs-temp", type=float, default=0.7)
    parser.add_argument("--fs-distance", type=float, default=10.0)
    parser.add_argument("--ala-budget", type=int, default=2)
    parser.add_argument("--gly-budget", type=int, default=0)
    parser.add_argument("--no-constrain-ss", action="store_true")
    parser.add_argument("--overwrite", action="store_true")
    args = parser.parse_args()

    nise_dir = args.nanohunter_root.resolve() / "scripts" / "nise"
    if not (nise_dir / "nise_lib.py").exists():
        raise SystemExit(f"nise_lib.py not found under {nise_dir}")
    sys.path.insert(0, str(nise_dir))
    import nise_lib  # noqa: E402

    backbones = sorted(args.backbones.resolve().glob("*.pdb"))
    if not backbones:
        raise SystemExit(f"No PDB files found in {args.backbones}")
    output = args.output.resolve()
    output.mkdir(parents=True, exist_ok=True)

    started = time.time()
    rows: list[dict] = []
    failures: list[str] = []
    with ThreadPoolExecutor(max_workers=args.max_parallel) as pool:
        futures = {
            pool.submit(design_one, nise_lib, backbone, output / backbone.stem, args): backbone
            for backbone in backbones
        }
        done = 0
        for future in as_completed(futures):
            backbone = futures[future]
            done += 1
            try:
                rows.extend(future.result())
            except Exception as exc:  # noqa: BLE001
                failures.append(f"{backbone.name}: {exc}")
            if done % 25 == 0 or done == len(backbones):
                print(f"{done}/{len(backbones)} backbones designed", flush=True)

    if failures:
        (output / "failures.json").write_text(json.dumps(failures, indent=2) + "\n")
        raise SystemExit(f"{len(failures)} backbones failed LASErMPNN design; see {output / 'failures.json'}")

    expected = len(backbones) * args.n_seqs
    if len(rows) != expected:
        raise SystemExit(f"Expected exactly {expected} LASErMPNN sequences, got {len(rows)}")
    bad_lengths = [r for r in rows if r["sequence_length"] < 1]
    if bad_lengths:
        raise SystemExit(f"LASErMPNN returned {len(bad_lengths)} empty sequences")

    rows.sort(key=lambda r: (r["design"], r["seq_index"]))
    fields = sorted({key for row in rows for key in row})
    with (output / "sequences.csv").open("w", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields)
        writer.writeheader()
        writer.writerows(rows)

    wall = time.time() - started
    manifest = {
        "num_backbones": len(backbones), "n_seqs": args.n_seqs, "num_sequences": len(rows),
        "seq_temp": args.seq_temp, "fs_temp": args.fs_temp, "fs_distance": args.fs_distance,
        "ala_budget": args.ala_budget, "gly_budget": args.gly_budget,
        "constrain_ss": not args.no_constrain_ss, "wall_sec": wall,
    }
    (output / "run_manifest.json").write_text(json.dumps(manifest, indent=2) + "\n")
    print(f"wrote {len(rows)} sequences ({len(backbones)} backbones x {args.n_seqs}) in {wall:.1f}s -> {output / 'sequences.csv'}")


if __name__ == "__main__":
    main()
