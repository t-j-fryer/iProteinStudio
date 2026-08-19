#!/usr/bin/env python3
"""Run one or more MPNN sequences per RFD3 backbone in one model load."""

from __future__ import annotations

import argparse
import csv
import json
import os
import re
import subprocess
import time
from pathlib import Path


def chain_length(pdb: Path, chain: str = "A") -> int:
    residues = set()
    for line in pdb.read_text().splitlines():
        if line.startswith("ATOM") and line[21:22] == chain:
            residues.add((line[22:26], line[26:27]))
    return len(residues)


def parse_fasta(path: Path) -> list[tuple[str, dict[str, float]]]:
    records: list[tuple[str, str]] = []
    header = ""
    seq: list[str] = []
    for line in path.read_text().splitlines():
        if line.startswith(">"):
            if header:
                records.append((header, "".join(seq)))
            header, seq = line[1:], []
        elif line.strip():
            seq.append(line.strip())
    if header:
        records.append((header, "".join(seq)))
    if len(records) < 2:
        raise ValueError(f"Expected native and designed FASTA records in {path}")
    designs = []
    for header, full_sequence in records[1:]:
        binder = full_sequence.split(":", 1)[0]
        metrics: dict[str, float] = {}
        for key in ("overall_confidence", "ligand_confidence", "seq_rec"):
            match = re.search(rf"(?:^|, )({key})=([-+0-9.eE]+)", header)
            if match:
                metrics[key] = float(match.group(2))
        designs.append((binder, metrics))
    return designs


def write_csv(rows: list[dict], path: Path) -> None:
    fields = sorted({key for row in rows for key in row})
    with path.open("w", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields)
        writer.writeheader()
        writer.writerows(rows)


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
    parser = argparse.ArgumentParser()
    parser.add_argument("--backbones", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--model-type", choices=["soluble_mpnn", "protein_mpnn", "ligand_mpnn"], required=True)
    parser.add_argument("--nanohunter-root", type=Path)
    parser.add_argument("--temperature", type=float, default=0.1)
    parser.add_argument("--n-seqs", type=int, default=1)
    parser.add_argument("--seed", type=int, default=20260806)
    parser.add_argument("--omit-aa", default="C")
    parser.add_argument("--chain", default="A")
    parser.add_argument("--overwrite", action="store_true")
    args = parser.parse_args()
    args.nanohunter_root = args.nanohunter_root or default_root()
    if args.n_seqs < 1:
        raise SystemExit("--n-seqs must be at least 1")

    backbones = sorted(args.backbones.resolve().glob("*.pdb"))
    if not backbones:
        raise SystemExit(f"No PDB files found in {args.backbones}")
    output = args.output.resolve()
    output.mkdir(parents=True, exist_ok=True)
    seq_dir = output / "seqs"
    expected = [seq_dir / f"{p.stem}.fa" for p in backbones]

    root = args.nanohunter_root.resolve()
    repo = root / "src" / "LigandMPNN"
    python = root / "venvs" / "NanoHunter_ligandmpnn" / "bin" / "python"
    if not python.exists() or not (repo / "run.py").exists():
        raise SystemExit(f"NanoHunter LigandMPNN installation not found under {root}")

    path_map = {str(path): "" for path in backbones}
    map_path = output / "pdb_paths.json"
    map_path.write_text(json.dumps(path_map, indent=2) + "\n")
    command = [
        str(python),
        "run.py",
        "--pdb_path_multi", str(map_path),
        "--out_folder", str(output),
        "--model_type", args.model_type,
        "--chains_to_design", args.chain,
        "--batch_size", "1",
        "--number_of_batches", str(args.n_seqs),
        "--temperature", str(args.temperature),
        "--seed", str(args.seed),
        "--omit_AA", args.omit_aa,
        "--verbose", "0",
    ]
    command_path = output / "command.json"
    command_path.write_text(json.dumps(command, indent=2) + "\n")

    started = time.time()
    if args.overwrite or not all(path.exists() for path in expected):
        env = os.environ.copy()
        env.update({"KMP_USE_SHM": "0", "OMP_NUM_THREADS": "1", "MKL_NUM_THREADS": "1"})
        with (output / "mpnn.log").open("w") as log:
            result = subprocess.run(command, cwd=repo, env=env, stdout=log, stderr=subprocess.STDOUT)
        if result.returncode:
            raise SystemExit(f"MPNN failed with exit code {result.returncode}; see {output / 'mpnn.log'}")
    wall = time.time() - started

    rows: list[dict] = []
    for backbone, fasta in zip(backbones, expected, strict=True):
        if not fasta.exists():
            raise SystemExit(f"Missing MPNN output: {fasta}")
        designs = parse_fasta(fasta)
        if len(designs) != args.n_seqs:
            raise SystemExit(
                f"Expected {args.n_seqs} designed records in {fasta}, found {len(designs)}"
            )
        expected_length = chain_length(backbone, args.chain)
        for seq_index, (sequence, metrics) in enumerate(designs, 1):
            if len(sequence) != expected_length:
                raise SystemExit(
                    f"Sequence length mismatch for {backbone.name}: {len(sequence)} != {expected_length}"
                )
            rows.append(
                {
                    "design": backbone.stem,
                    "seq_index": seq_index,
                    "sequence": sequence,
                    "sequence_length": len(sequence),
                    "model_type": args.model_type,
                    "temperature": args.temperature,
                    "seed": args.seed,
                    "backbone_pdb": str(backbone),
                    "fasta": str(fasta),
                    **metrics,
                }
            )
    write_csv(rows, output / "sequences.csv")
    manifest = {
        "num_backbones": len(backbones),
        "sequences_per_backbone": args.n_seqs,
        "model_type": args.model_type,
        "temperature": args.temperature,
        "seed": args.seed,
        "omit_aa": args.omit_aa,
        "wall_sec": wall,
        "sec_per_design": wall / len(backbones),
        "command": command,
    }
    (output / "run_manifest.json").write_text(json.dumps(manifest, indent=2) + "\n")
    print(f"wrote {len(rows)} sequences in {wall:.2f}s -> {output / 'sequences.csv'}")


if __name__ == "__main__":
    main()
