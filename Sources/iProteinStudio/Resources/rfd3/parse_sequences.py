#!/usr/bin/env python3
"""Turn a FASTA or CSV of sequences into fold jobs.

Three shapes of batch cover almost everything people actually want:

  monomer   fold each sequence on its own
  shared    fold each sequence against one common partner (a screen against a
            single target)
  paired    fold each sequence against its own partner, taken from a second
            column (a set of matched pairs)

CSV is the honest format for the last two, because a FASTA record has nowhere to
say what its partner is. Column names are matched loosely, so `binder`/`sequence`
/`seq` and `target`/`partner`/`chain_b` all work rather than forcing one spelling.

Ligands are supported through a `smiles` column, so a screen against a small
molecule is the same operation as a screen against a protein.

Usage:  parse_sequences.py FILE --mode monomer|shared|paired [--partner SEQ]
                                [--partner-smiles SMILES]
                                [--binder-msa auto|empty] [--partner-msa auto|empty]
Output: {"jobs": [...], "warnings": [...]} or {"error": "..."}
"""

from __future__ import annotations

import argparse
import csv
import json
import re
import sys
from pathlib import Path

BINDER_KEYS = ("binder", "sequence", "seq", "protein", "query", "design", "name_seq")
PARTNER_KEYS = ("target", "partner", "chain_b", "receptor", "antigen", "partner_sequence")
NAME_KEYS = ("name", "id", "design", "label", "description")
SMILES_KEYS = ("smiles", "ligand", "ligand_smiles")

AA = set("ACDEFGHIKLMNPQRSTVWYXBZJUO")


def fail(message: str) -> None:
    print(json.dumps({"error": message}))
    sys.exit(1)


def clean(sequence: str) -> str:
    return "".join(c for c in (sequence or "").upper() if c.isalpha())


def looks_like_protein(sequence: str) -> bool:
    seq = clean(sequence)
    return len(seq) >= 5 and all(c in AA for c in seq)


def slug(text: str, fallback: str) -> str:
    # A Unicode-only leading character is removed by the ASCII-safe rewrite.
    # Strip every allowed separator afterwards so names such as
    # `α-Cobratoxin` become `Cobratoxin`, not `-Cobratoxin` (which command-line
    # parsers can mistake for an option when passed as a separate argument).
    out = re.sub(r"[^A-Za-z0-9_.-]+", "_", (text or "").strip()).strip("_.-")
    return out[:60] or fallback


def read_fasta(path: Path) -> list:
    entries, name, chunks = [], None, []
    for line in path.read_text(errors="replace").splitlines():
        line = line.strip()
        if not line:
            continue
        if line.startswith(">"):
            if name is not None:
                entries.append((name, "".join(chunks)))
            name, chunks = line[1:].strip(), []
        else:
            chunks.append(line)
    if name is not None:
        entries.append((name, "".join(chunks)))
    return [(n, clean(s)) for n, s in entries if clean(s)]


def pick(row: dict, keys) -> str:
    lowered = {str(k).strip().lower(): (v or "") for k, v in row.items() if k}
    for key in keys:
        if key in lowered and str(lowered[key]).strip():
            return str(lowered[key]).strip()
    return ""


def read_csv(path: Path) -> list:
    with path.open(newline="") as handle:
        sample = handle.read(4096)
        handle.seek(0)
        try:
            dialect = csv.Sniffer().sniff(sample, delimiters=",\t;")
        except Exception:
            dialect = csv.excel
        rows = list(csv.DictReader(handle, dialect=dialect))
    if not rows:
        fail("That file has no rows.")
    return rows


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("file", type=Path)
    parser.add_argument("--mode", choices=["monomer", "shared", "paired"], default="monomer")
    parser.add_argument("--partner", default="")
    parser.add_argument("--partner-smiles", default="")
    parser.add_argument("--binder-msa", default="auto")
    parser.add_argument("--partner-msa", default="auto")
    args = parser.parse_args()

    if not args.file.exists():
        fail(f"No such file: {args.file}")

    warnings, jobs = [], []
    suffix = args.file.suffix.lower()
    is_fasta = suffix in {".fasta", ".fa", ".faa", ".fas", ".seq", ".txt"}

    if is_fasta:
        entries = read_fasta(args.file)
        if not entries:
            fail("No sequences found in that FASTA.")
        if args.mode == "paired":
            fail("A FASTA has nowhere to record each sequence's partner. Use a CSV with a "
                 "partner column, or pick 'same partner for all'.")
        rows = [{"name": n, "binder": s, "partner": "", "smiles": ""} for n, s in entries]
    else:
        raw = read_csv(args.file)
        rows = []
        for i, row in enumerate(raw, 1):
            rows.append({
                "name": pick(row, NAME_KEYS) or f"row{i}",
                "binder": clean(pick(row, BINDER_KEYS)),
                "partner": clean(pick(row, PARTNER_KEYS)),
                "smiles": pick(row, SMILES_KEYS),
            })
        if not any(r["binder"] for r in rows):
            fail("No sequence column found. Name one of: " + ", ".join(BINDER_KEYS))

    seen = {}
    for i, row in enumerate(rows, 1):
        binder = row["binder"]
        if not binder:
            warnings.append(f"Row {i} has no sequence and was skipped.")
            continue
        if not looks_like_protein(binder):
            warnings.append(f"{row['name']}: not a protein sequence, skipped.")
            continue

        name = slug(row["name"], f"job{i}")
        if name in seen:
            seen[name] += 1
            name = f"{name}_{seen[name]}"
        else:
            seen[name] = 0

        chains = [{"id": "A", "kind": "protein", "sequence": binder, "msa": args.binder_msa}]

        if args.mode == "shared":
            if args.partner_smiles.strip():
                chains.append({"id": "B", "kind": "ligand", "smiles": args.partner_smiles.strip()})
            elif clean(args.partner):
                chains.append({"id": "B", "kind": "protein", "sequence": clean(args.partner),
                               "msa": args.partner_msa})
            else:
                fail("Choose a partner sequence or SMILES for 'same partner for all'.")
        elif args.mode == "paired":
            if row["smiles"]:
                chains.append({"id": "B", "kind": "ligand", "smiles": row["smiles"]})
            elif row["partner"]:
                chains.append({"id": "B", "kind": "protein", "sequence": row["partner"],
                               "msa": args.partner_msa})
            else:
                warnings.append(f"{name}: no partner in this row, folded on its own.")

        jobs.append({"name": name, "chains": chains})

    if not jobs:
        fail("Nothing usable in that file.")
    print(json.dumps({"jobs": jobs, "warnings": warnings}))


if __name__ == "__main__":
    main()
