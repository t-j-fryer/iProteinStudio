#!/usr/bin/env python3
"""Create a reproducible fluorescein-hydroxyethylamide RFD3 input.

The official RFD3/AtomWorks input pipeline resolves non-polymers through the
Chemical Component Dictionary (CCD).  A generic ``LIG`` PDB therefore loses
the molecule's chemistry.  This script creates both a ligand PDB and a minimal
local CCD entry with identical, deterministic atom names.
"""

from __future__ import annotations

import argparse
import csv
import json
from pathlib import Path

from rdkit import Chem
from rdkit.Chem import AllChem, Descriptors, rdMolDescriptors


DEFAULT_SMILES = "O=C(NCCO)c1ccc(-c2c3ccc(=O)cc-3oc3cc([O-])ccc23)c(C(=O)[O-])c1"
LINKER_SMARTS = "O=C(NCCO)"


def boltz_atom_names(mol_h: Chem.Mol) -> None:
    """Apply the atom naming convention used for SMILES inputs by Boltz."""
    ranks = list(Chem.CanonicalRankAtoms(mol_h))
    for atom, rank in zip(mol_h.GetAtoms(), ranks, strict=True):
        atom.SetProp("name", f"{atom.GetSymbol().upper()}{rank + 1}")


def bond_order_name(bond: Chem.Bond) -> str:
    if bond.GetIsAromatic():
        return "AROM"
    return {
        Chem.BondType.SINGLE: "SING",
        Chem.BondType.DOUBLE: "DOUB",
        Chem.BondType.TRIPLE: "TRIP",
    }.get(bond.GetBondType(), "SING")


def write_pdb(mol: Chem.Mol, path: Path, component_id: str) -> None:
    conf = mol.GetConformer()
    lines: list[str] = []
    for serial, atom in enumerate(mol.GetAtoms(), 1):
        pos = conf.GetAtomPosition(atom.GetIdx())
        name = atom.GetProp("name")
        element = atom.GetSymbol().upper()
        charge = atom.GetFormalCharge()
        charge_field = "  " if charge == 0 else f"{abs(charge)}{'-' if charge < 0 else '+'}"
        atom_field = name.rjust(4) if len(name) < 4 else name[:4]
        lines.append(
            f"HETATM{serial:5d} {atom_field} {component_id:>3} L   1    "
            f"{pos.x:8.3f}{pos.y:8.3f}{pos.z:8.3f}  1.00  0.00          "
            f"{element:>2}{charge_field:>2}"
        )
    for atom in mol.GetAtoms():
        bonded = sorted(n.GetIdx() + 1 for n in atom.GetNeighbors())
        if bonded:
            lines.append(f"CONECT{atom.GetIdx() + 1:5d}" + "".join(f"{i:5d}" for i in bonded))
    lines.extend(["TER", "END"])
    path.write_text("\n".join(lines) + "\n")


def write_ccd(mol: Chem.Mol, path: Path, component_id: str, smiles: str) -> None:
    conf = mol.GetConformer()
    formula = rdMolDescriptors.CalcMolFormula(mol)
    total_charge = sum(atom.GetFormalCharge() for atom in mol.GetAtoms())
    rows = [
        f"data_{component_id}",
        "#",
        f"_chem_comp.id {component_id}",
        "_chem_comp.name 'Fluorescein hydroxyethylamide'",
        "_chem_comp.type non-polymer",
        f"_chem_comp.formula '{formula}'",
        f"_chem_comp.formula_weight {Descriptors.MolWt(mol):.3f}",
        f"_chem_comp.pdbx_formal_charge {total_charge}",
        "_chem_comp.one_letter_code ?",
        f"_chem_comp.three_letter_code {component_id}",
        "#",
        "loop_",
        "_chem_comp_atom.comp_id",
        "_chem_comp_atom.atom_id",
        "_chem_comp_atom.alt_atom_id",
        "_chem_comp_atom.type_symbol",
        "_chem_comp_atom.charge",
        "_chem_comp_atom.pdbx_aromatic_flag",
        "_chem_comp_atom.pdbx_leaving_atom_flag",
        "_chem_comp_atom.pdbx_stereo_config",
        "_chem_comp_atom.model_Cartn_x",
        "_chem_comp_atom.model_Cartn_y",
        "_chem_comp_atom.model_Cartn_z",
        "_chem_comp_atom.pdbx_model_Cartn_x_ideal",
        "_chem_comp_atom.pdbx_model_Cartn_y_ideal",
        "_chem_comp_atom.pdbx_model_Cartn_z_ideal",
    ]
    for atom in mol.GetAtoms():
        pos = conf.GetAtomPosition(atom.GetIdx())
        name = atom.GetProp("name")
        rows.append(
            f"{component_id} {name} {name} {atom.GetSymbol().upper()} "
            f"{atom.GetFormalCharge()} {'Y' if atom.GetIsAromatic() else 'N'} N N "
            f"{pos.x:.6f} {pos.y:.6f} {pos.z:.6f} {pos.x:.6f} {pos.y:.6f} {pos.z:.6f}"
        )
    rows.extend(
        [
            "#",
            "loop_",
            "_chem_comp_bond.comp_id",
            "_chem_comp_bond.atom_id_1",
            "_chem_comp_bond.atom_id_2",
            "_chem_comp_bond.value_order",
            "_chem_comp_bond.pdbx_aromatic_flag",
            "_chem_comp_bond.pdbx_stereo_config",
            "_chem_comp_bond.pdbx_ordinal",
        ]
    )
    for ordinal, bond in enumerate(mol.GetBonds(), 1):
        a = bond.GetBeginAtom().GetProp("name")
        b = bond.GetEndAtom().GetProp("name")
        rows.append(
            f"{component_id} {a} {b} {bond_order_name(bond)} "
            f"{'Y' if bond.GetIsAromatic() else 'N'} N {ordinal}"
        )
    rows.extend(
        [
            "#",
            "loop_",
            "_pdbx_chem_comp_descriptor.comp_id",
            "_pdbx_chem_comp_descriptor.type",
            "_pdbx_chem_comp_descriptor.program",
            "_pdbx_chem_comp_descriptor.program_version",
            "_pdbx_chem_comp_descriptor.descriptor",
            f"{component_id} SMILES RDKit {Chem.rdBase.rdkitVersion} '{smiles}'",
            "#",
        ]
    )
    path.write_text("\n".join(rows) + "\n")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--smiles", default=DEFAULT_SMILES)
    parser.add_argument("--component-id", default="FHE")
    parser.add_argument("--output-dir", type=Path, default=Path("assets/fluorescein"))
    parser.add_argument("--seed", type=int, default=20260806)
    args = parser.parse_args()

    component_id = args.component_id.upper()
    if len(component_id) > 3:
        raise SystemExit("PDB compatibility requires a component ID of at most three characters")

    mol = Chem.MolFromSmiles(args.smiles)
    if mol is None:
        raise SystemExit("RDKit could not parse --smiles")
    mol_h = Chem.AddHs(mol)
    boltz_atom_names(mol_h)
    if AllChem.EmbedMolecule(mol_h, randomSeed=args.seed) != 0:
        raise SystemExit("RDKit failed to generate a 3D conformer")
    if AllChem.MMFFHasAllMoleculeParams(mol_h):
        AllChem.MMFFOptimizeMolecule(mol_h, maxIters=1000)
    else:
        AllChem.UFFOptimizeMolecule(mol_h, maxIters=1000)
    heavy = Chem.RemoveHs(mol_h, sanitize=False)
    Chem.SanitizeMol(heavy)

    linker = Chem.MolFromSmarts(LINKER_SMARTS)
    matches = heavy.GetSubstructMatches(linker)
    if len(matches) != 1:
        raise SystemExit(f"Expected one linker match for {LINKER_SMARTS!r}, got {len(matches)}")
    exposed_idx = set(matches[0])
    exposed = [heavy.GetAtomWithIdx(i).GetProp("name") for i in matches[0]]
    buried = [
        atom.GetProp("name")
        for atom in heavy.GetAtoms()
        if atom.GetIdx() not in exposed_idx
    ]

    out = args.output_dir.resolve()
    ccd_path = out / "ccd" / component_id[0] / component_id / f"{component_id}.cif"
    ccd_path.parent.mkdir(parents=True, exist_ok=True)
    out.mkdir(parents=True, exist_ok=True)
    pdb_path = out / f"{component_id}.pdb"
    write_pdb(heavy, pdb_path, component_id)
    write_ccd(heavy, ccd_path, component_id, args.smiles)

    manifest = {
        "component_id": component_id,
        "smiles": args.smiles,
        "linker_smarts": LINKER_SMARTS,
        "exposed_atoms": exposed,
        "buried_atoms": buried,
        "all_heavy_atoms": [a.GetProp("name") for a in heavy.GetAtoms()],
        "formal_charge": sum(a.GetFormalCharge() for a in heavy.GetAtoms()),
        "pdb": str(pdb_path),
        "ccd_mirror": str(out / "ccd"),
        "seed": args.seed,
    }
    (out / "atom_selections.json").write_text(json.dumps(manifest, indent=2) + "\n")
    with (out / "atom_map.csv").open("w", newline="") as handle:
        writer = csv.writer(handle)
        writer.writerow(["rdkit_index", "atom_name", "element", "formal_charge", "rfd3_rasa"])
        for atom in heavy.GetAtoms():
            writer.writerow(
                [
                    atom.GetIdx(),
                    atom.GetProp("name"),
                    atom.GetSymbol(),
                    atom.GetFormalCharge(),
                    "exposed" if atom.GetIdx() in exposed_idx else "buried",
                ]
            )

    print(json.dumps(manifest, indent=2))


if __name__ == "__main__":
    main()
