#!/usr/bin/env python3
"""Assign cycle 01+ binder secondary structure with Biotite P-SEA."""

from __future__ import annotations

import argparse
import csv
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
    raise SystemExit(
        "Biotite is required for structural secondary-structure assignment. "
        "Install the managed Protenix engine or install biotite into the active environment."
    )


def assignments(structure: Path, chain: str = "A") -> Counter:
    from biotite.structure import annotate_sse
    if structure.suffix.lower() == ".cif":
        from biotite.structure.io.pdbx import CIFFile, get_structure
        atoms = get_structure(CIFFile.read(structure), model=1)
    else:
        from biotite.structure.io.pdb import PDBFile
        atoms = PDBFile.read(structure).get_structure(model=1)
    chain_atoms = atoms[atoms.chain_id == chain]
    if not len(chain_atoms):
        raise RuntimeError(f"structure has no chain {chain}: {structure}")
    codes = annotate_sse(chain_atoms)
    counts = Counter({
        "helix": sum(code == "a" for code in codes),
        "sheet": sum(code == "b" for code in codes),
        "coil": sum(code == "c" for code in codes),
    })
    if sum(counts.values()) != len(codes) or not len(codes):
        raise RuntimeError(f"incomplete P-SEA assignment for chain {chain}: {structure}")
    return counts


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--campaign-root", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--chain", default="A")
    args = parser.parse_args()
    ensure_biotite()
    rows = []
    for campaign in sorted(path for path in args.campaign_root.iterdir() if path.is_dir()):
        if "__" not in campaign.name:
            continue
        total: Counter = Counter()
        structures = []
        for path in sorted(campaign.glob("run_*/cycle_*/pred_min/model_0.*")):
            cycle = int(path.parents[1].name.split("_")[-1])
            if cycle == 0:
                continue
            total.update(assignments(path, args.chain))
            structures.append(path)
        if not structures:
            continue
        count = sum(total.values())
        engine, arm = campaign.name.split("__", 1)
        rows.append({
            "engine": engine, "arm": arm, "structures": len(structures),
            "binder_residues": count,
            "helix_fraction": total["helix"] / count,
            "sheet_fraction": total["sheet"] / count,
            "coil_fraction": total["coil"] / count,
        })
    args.output.parent.mkdir(parents=True, exist_ok=True)
    with args.output.open("w", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(rows[0]) if rows else [
            "engine", "arm", "structures", "binder_residues",
            "helix_fraction", "sheet_fraction", "coil_fraction",
        ])
        writer.writeheader()
        writer.writerows(rows)


if __name__ == "__main__":
    main()
