#!/usr/bin/env python3
"""Create an AtomWorks CCD-mirror entry from an SDF and explicit atom map."""

from __future__ import annotations

import argparse
import csv
import sys
from pathlib import Path

from rdkit import Chem

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
from prepare_ligand_target import write_ccd  # noqa: E402


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--sdf", type=Path, required=True)
    parser.add_argument("--atom-map", type=Path, required=True)
    parser.add_argument("--component-id", required=True)
    parser.add_argument("--output", type=Path, required=True, help="CCD mirror root")
    args = parser.parse_args()
    component = args.component_id.upper()
    if not (1 <= len(component) <= 3):
        raise SystemExit("component ID must contain 1-3 characters")

    supplier = Chem.SDMolSupplier(str(args.sdf.resolve()), removeHs=False, sanitize=True)
    mol = supplier[0] if supplier and len(supplier) else None
    if mol is None:
        raise SystemExit(f"RDKit could not read {args.sdf}")
    rows = list(csv.DictReader(args.atom_map.open()))
    rows.sort(key=lambda r: int(r["atom_number_1based"]))
    if len(rows) != mol.GetNumAtoms():
        raise SystemExit(f"atom map has {len(rows)} rows but SDF has {mol.GetNumAtoms()} atoms")
    for atom, row in zip(mol.GetAtoms(), rows, strict=True):
        if atom.GetSymbol().upper() != row["element"].upper():
            raise SystemExit(f"element mismatch at atom {row['atom_number_1based']}")
        atom.SetProp("name", row["atom_name"])

    smiles = mol.GetProp("SMILES") if mol.HasProp("SMILES") else Chem.MolToSmiles(mol, isomericSmiles=True)
    out = args.output.resolve()
    ccd = out / component[0] / component / f"{component}.cif"
    ccd.parent.mkdir(parents=True, exist_ok=True)
    write_ccd(mol, ccd, component, smiles)
    (out / ".ccd_codes_cache").write_text(component + "\n")
    print(f"wrote {component} ({mol.GetNumAtoms()} atoms, charge {Chem.GetFormalCharge(mol)}) -> {ccd}")


if __name__ == "__main__":
    main()
