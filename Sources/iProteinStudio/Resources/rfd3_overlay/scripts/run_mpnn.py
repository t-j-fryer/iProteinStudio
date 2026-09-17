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
import uuid
from pathlib import Path
from rfd3_resume import bind_inputs, save_receipt, verify_receipt, sha256


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
        writer.writerows([
            {key: json.dumps(value, sort_keys=True) if isinstance(value, (dict, list)) else value
             for key, value in row.items()}
            for row in rows
        ])


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
    backbone_metadata = {}
    metrics_path = args.backbones.resolve().parent / "backbone_metrics.csv"
    if metrics_path.exists():
        backbone_metadata = {
            row.get("design", ""): row for row in csv.DictReader(metrics_path.open())
            if row.get("design")
        }
    seq_dir = output / "seqs"
    expected = [seq_dir / f"{p.stem}.fa" for p in backbones]
    specification = {"backbones": {p.name: sha256(p) for p in backbones},
                     "model": args.model_type, "temperature": args.temperature,
                     "n_seqs": args.n_seqs, "seed": args.seed, "omit_aa": args.omit_aa,
                     "chain": args.chain}
    specification["metadata_sha256"] = sha256(metrics_path) if metrics_path.exists() else None
    fixed_input = args.backbones.resolve().parent / "fixed_residues_multi.json"
    specification["fixed_residues_sha256"] = sha256(fixed_input) if fixed_input.exists() else None
    bind_inputs(output / "studio_sequence_request.json", specification)
    request_sha256 = sha256(output / "studio_sequence_request.json")
    complete = verify_receipt(output / "studio_sequence_receipt.json", specification)
    if complete and not args.overwrite:
        print(f"reused {len(backbones)} verified sequence batches -> {output / 'sequences.csv'}")
        return

    root = args.nanohunter_root.resolve()
    repo = root / "src" / "LigandMPNN"
    python = root / "venvs" / "NanoHunter_ligandmpnn" / "bin" / "python"
    if not python.exists() or not (repo / "run.py").exists():
        raise SystemExit(f"NanoHunter LigandMPNN installation not found under {root}")

    # Preserve already completed backbone sequences on interruption. Checkpoint
    # each valid FASTA; one upstream invocation handles the remaining set.
    pending = []
    for backbone, fasta in zip(backbones, expected, strict=True):
        identity = {"request_sha256": request_sha256, "backbone": backbone.name}
        receipt = output / "receipts" / (backbone.stem + ".json")
        if args.overwrite or not verify_receipt(receipt, identity):
            pending.append(backbone)
            if fasta.exists():
                archive = output / "interrupted" / uuid.uuid4().hex
                archive.mkdir(parents=True)
                fasta.rename(archive / fasta.name)
    path_map = {str(path): "" for path in pending}
    attempt_dir = output / "attempts" / uuid.uuid4().hex
    attempt_dir.mkdir(parents=True)
    map_path = attempt_dir / "pdb_paths.json"
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
    fixed_map = args.backbones.resolve().parent / "fixed_residues_multi.json"
    if fixed_map.exists():
        command += ["--fixed_residues_multi", str(fixed_map)]
    command_path = attempt_dir / "command.json"
    command_path.write_text(json.dumps(command, indent=2) + "\n")

    started = time.time()
    if pending:
        env = os.environ.copy()
        env.update({"KMP_USE_SHM": "0", "OMP_NUM_THREADS": "1", "MKL_NUM_THREADS": "1"})
        checkpointed = set()

        def checkpoint_completed():
            # Upstream writes the FASTA after sampling all requested sequences
            # for a backbone. Capture it while the resident process proceeds to
            # the next backbone, so terminating the parent preserves progress.
            for backbone in pending:
                if backbone.name in checkpointed:
                    continue
                fasta = seq_dir / f"{backbone.stem}.fa"
                if not fasta.is_file():
                    continue
                try:
                    designs = parse_fasta(fasta)
                    if len(designs) != args.n_seqs or any(len(seq) != chain_length(backbone, args.chain)
                        or set(seq) - set("ACDEFGHIKLMNPQRSTVWY") for seq, _ in designs):
                        continue
                    save_receipt(output / "receipts" / (backbone.stem + ".json"),
                                 {"request_sha256": request_sha256, "backbone": backbone.name}, [fasta])
                    checkpointed.add(backbone.name)
                except ValueError:
                    continue

        with (output / "mpnn.log").open("a") as log:
            process = subprocess.Popen(command, cwd=repo, env=env, stdout=log, stderr=subprocess.STDOUT)
            try:
                while process.poll() is None:
                    checkpoint_completed()
                    time.sleep(0.25)
                checkpoint_completed()
            finally:
                if process.poll() is None:
                    process.terminate()
                    try:
                        process.wait(timeout=10)
                    except subprocess.TimeoutExpired:
                        process.kill(); process.wait()
        if process.returncode:
            raise SystemExit(f"MPNN failed with exit code {process.returncode}; see {output / 'mpnn.log'}")
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
            if len(sequence) != expected_length or set(sequence) - set("ACDEFGHIKLMNPQRSTVWY"):
                raise SystemExit(
                    f"Sequence length mismatch for {backbone.name}: {len(sequence)} != {expected_length}"
                )
            rows.append(
                {
                    **backbone_metadata.get(backbone.stem, {}),
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
    save_receipt(output / "studio_sequence_receipt.json", specification,
                 expected + [output / "sequences.csv"])
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
