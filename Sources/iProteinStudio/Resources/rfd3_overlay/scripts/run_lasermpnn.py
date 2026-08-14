#!/usr/bin/env python3
"""Design N LASErMPNN sequences per RFD3 backbone.

The invocation below is the validated LASErMPNN path from NanoHunter's NISE
implementation, ported here without importing NISE itself. iProteinStudio does
not ship ``scripts/nise``; depending on it made a clean install fail before the
first sequence was designed. Keep these arguments aligned with
``NanoHunter/scripts/nise/nise_lib.py::lasermpnn_design``.

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
import re
import shlex
import subprocess
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
import os
from pathlib import Path


def _read_fasta_count(fasta_path: Path) -> int:
    # LASErMPNN's designs.fasta has one ">...score=..." header per design
    # (verified: no separate native-sequence record, unlike LigandMPNN's output).
    if not fasta_path.exists():
        return 0
    return sum(1 for line in fasta_path.read_text().splitlines() if line.startswith(">"))


def _read_lasermpnn_fasta(fasta_path: Path) -> list[tuple[str, float]]:
    """Return (sequence, score) pairs using NanoHunter's validated parser."""
    pairs: list[tuple[str, float]] = []
    header: str | None = None
    sequence: list[str] = []
    for line in fasta_path.read_text().splitlines():
        if line.startswith(">"):
            if header is not None and sequence:
                match = re.search(r"score=(-?\d+(?:\.\d+)?)", header)
                pairs.append(("".join(sequence), float(match.group(1)) if match else float("-inf")))
            header, sequence = line, []
        elif line.strip():
            sequence.append(line.strip())
    if header is not None and sequence:
        match = re.search(r"score=(-?\d+(?:\.\d+)?)", header)
        pairs.append(("".join(sequence), float(match.group(1)) if match else float("-inf")))
    return pairs


def _run(command: list[Path | str], *, cwd: Path | None, log: Path, env: dict[str, str]) -> None:
    merged_env = dict(os.environ)
    merged_env.update(env)
    result = subprocess.run(
        [str(item) for item in command], cwd=cwd, env=merged_env,
        stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True)
    log.parent.mkdir(parents=True, exist_ok=True)
    log.write_text(f"$ {shlex.join([str(item) for item in command])}\n{result.stdout or ''}")
    if result.returncode:
        tail = "\n".join((result.stdout or "").splitlines()[-40:])
        raise RuntimeError(f"command failed ({result.returncode}); see {log}\n{tail}")


def _design(backbone: Path, out_dir: Path, args) -> list[tuple[str, float]]:
    root = args.nanohunter_root.resolve()
    python = root / "venvs" / "NanoHunter_lasermpnn" / "bin" / "python"
    repo = root / "src" / "LASErMPNN"
    weights = repo / "model_weights" / "laser_weights_0p1A_nothing_heldout.pt"
    prepare = root / "scripts" / "lasermpnn_prepare_input.py"
    for path, label in ((python, "LASErMPNN Python"), (weights, "LASErMPNN weights"),
                        (prepare, "LASErMPNN input helper")):
        if not path.exists():
            raise RuntimeError(f"{label} not found at {path}")

    out_dir.mkdir(parents=True, exist_ok=True)
    prepared = out_dir / "prepared.pdb"
    _run(
        [python, prepare, "--in-pdb", backbone, "--out-pdb", prepared,
         "--smiles", args.smiles, "--designed-positions", "all"],
        cwd=None, log=out_dir / "prepare.log", env={})

    designs = out_dir / "designs"
    designs.mkdir(exist_ok=True)
    command: list[Path | str] = [
        python, "-m", "LASErMPNN.run_batch_inference", prepared, designs, str(args.n_seqs),
        "--device", "cpu",
        "--model_weights_path", weights,
        "--sequence_temp", str(args.seq_temp),
        "--first_shell_sequence_temp", str(args.fs_temp),
        "--fs_calc_ca_distance", str(args.fs_distance),
        "--disabled_residues", "X,C",
        "--output_fasta_only", "--silent",
    ]
    if not args.no_constrain_ss:
        command += ["-c", "--ala_budget", str(args.ala_budget),
                    "--gly_budget", str(args.gly_budget)]
    _run(command, cwd=repo.parent, log=out_dir / "lasermpnn.log", env={
        "KMP_USE_SHM": "0", "OMP_NUM_THREADS": "1", "MKL_NUM_THREADS": "1",
    })
    fasta = designs / "designs.fasta"
    if not fasta.exists():
        raise RuntimeError(f"LASErMPNN produced no {fasta}")
    return sorted(_read_lasermpnn_fasta(fasta), key=lambda item: item[1], reverse=True)


def design_one(backbone: Path, out_dir: Path, args) -> list[dict]:
    fasta = out_dir / "designs" / "designs.fasta"
    if not args.overwrite and _read_fasta_count(fasta) >= args.n_seqs:
        pairs = sorted(_read_lasermpnn_fasta(fasta), key=lambda x: x[1], reverse=True)[: args.n_seqs]
    else:
        pairs = _design(backbone, out_dir, args)
    return [
        {
            "design": backbone.stem, "seq_index": i, "sequence": seq,
            "sequence_length": len(seq), "laser_score": score, "backbone_pdb": str(backbone),
        }
        for i, (seq, score) in enumerate(pairs)
    ]


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
    parser.add_argument("--backbones", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--smiles", required=True)
    parser.add_argument("--n-seqs", type=int, default=4)
    parser.add_argument("--max-parallel", type=int, default=6)
    parser.add_argument("--nanohunter-root", type=Path, default=default_root())
    parser.add_argument("--seq-temp", type=float, default=0.5)
    parser.add_argument("--fs-temp", type=float, default=0.7)
    parser.add_argument("--fs-distance", type=float, default=10.0)
    parser.add_argument("--ala-budget", type=int, default=2)
    parser.add_argument("--gly-budget", type=int, default=0)
    parser.add_argument("--no-constrain-ss", action="store_true")
    parser.add_argument("--overwrite", action="store_true")
    args = parser.parse_args()

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
            pool.submit(design_one, backbone, output / backbone.stem, args): backbone
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
