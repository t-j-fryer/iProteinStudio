#!/usr/bin/env python3
"""Assign per-structure binder secondary structure with Biotite P-SEA."""

from __future__ import annotations

import argparse
import csv
import json
import os
import sys
from collections import Counter
from pathlib import Path


def ensure_biotite() -> None:
    try:
        import biotite  # noqa: F401
        return
    except ImportError:
        pass
    managed = Path.home() / ".iproteinstudio/venvs/NanoHunter_protenix/bin/python"
    if managed.is_file() and Path(sys.executable).resolve() != managed.resolve():
        os.execv(str(managed), [str(managed), str(Path(__file__).resolve()), *sys.argv[1:]])
    raise SystemExit("Biotite is required; install the managed Protenix runtime.")


def assignment(path: Path, chain: str) -> tuple[str, Counter]:
    from biotite.structure import annotate_sse
    if path.suffix.lower() == ".cif":
        from biotite.structure.io.pdbx import CIFFile, get_structure
        atoms = get_structure(CIFFile.read(path), model=1)
    else:
        from biotite.structure.io.pdb import PDBFile
        atoms = PDBFile.read(path).get_structure(model=1)
    chain_atoms = atoms[atoms.chain_id == chain]
    codes = "".join(annotate_sse(chain_atoms))
    if not codes:
        raise RuntimeError(f"no P-SEA assignments for chain {chain}: {path}")
    counts = Counter(codes)
    return codes, counts


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--campaign-root", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--phase", default="full")
    parser.add_argument("--chain", default="A")
    args = parser.parse_args()
    ensure_biotite()
    rows = []
    for campaign in sorted(args.campaign_root.glob(f"{args.phase}__*")):
        arm = campaign.name.split("__", 1)[1]
        for structure in sorted(campaign.glob("run_*/cycle_*/pred_min/model_0.*")):
            cycle = int(structure.parents[1].name.split("_")[-1])
            codes, counts = assignment(structure, args.chain)
            n = len(codes)
            rows.append({
                "arm": arm, "run": structure.parents[2].name, "cycle": cycle,
                "is_design": cycle > 0, "residues": n,
                "helix_fraction": counts["a"] / n,
                "sheet_fraction": counts["b"] / n,
                "coil_fraction": counts["c"] / n,
                "psea": codes, "structure": str(structure),
            })
    args.output.parent.mkdir(parents=True, exist_ok=True)
    fields = ["arm", "run", "cycle", "is_design", "residues", "helix_fraction",
              "sheet_fraction", "coil_fraction", "psea", "structure"]
    with args.output.open("w", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields)
        writer.writeheader()
        writer.writerows(rows)
    print(json.dumps({"rows": len(rows), "output": str(args.output)}))


if __name__ == "__main__":
    main()
