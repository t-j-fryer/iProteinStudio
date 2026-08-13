#!/usr/bin/env python3
"""Turn a SMILES + conditioning spec into an RFD3 ligand CCD/PDB + input JSON.

Generalizes ``prepare_fluorescein.py`` beyond one hardcoded molecule: instead
of deriving exposed/buried atoms from a single hardcoded SMARTS pattern, this
script takes an explicit ``ligand_spec.json`` naming hotspots / hydrogen-bond
donor and acceptor atoms / exposed and buried atoms directly, using the same
Boltz-convention atom names (``SYMBOL + canonical_rank + 1``) this script
assigns to the molecule -- so the fixed vocabulary is discoverable up front
via ``atom_selections.json`` before the user has to name a single atom.

Per-ligand DesignInputSpecification fields use two different addressing
conventions in the pinned Foundry build:
  - select_hbond_donor / select_hbond_acceptor / select_exposed /
    select_buried / select_fixed_atoms are keyed by the ligand's CCD code.
  - select_hotspots needs literal chain+resnum addressing, and can mix
    protein and ligand chains in one dict.
This script writes the ligand PDB as chain L, resnum 1 (Foundry reserves
chain A for the diffused binder and raises "Ligand chain(s) overlap with
existing chain(s)" if the input ligand is also on A), and lets the spec file
use the placeholder key "LIGAND" everywhere; it substitutes "LIGAND" to the
CCD code for the CCD-keyed fields and to "L1" for select_hotspots.
"""

from __future__ import annotations

import argparse
import csv
import json
from pathlib import Path

from rdkit import Chem
from rdkit.Chem import AllChem, Descriptors, rdMolDescriptors

ROOT = Path(__file__).resolve().parents[1]


def boltz_atom_names(mol_h: Chem.Mol) -> None:
    """Apply the atom naming convention used for SMILES inputs by Boltz."""
    ranks = list(Chem.CanonicalRankAtoms(mol_h))
    for atom, rank in zip(mol_h.GetAtoms(), ranks, strict=True):
        atom.SetProp("name", f"{atom.GetSymbol().upper()}{rank + 1}")


def bond_order_name(bond: Chem.Bond) -> str:
    # Biotite's CIF reader wants the *kekulized* order here (value_order) with
    # aromaticity conveyed separately via pdbx_aromatic_flag; the mol must be
    # Kekulized first (see main()) or every ring bond reports BondType.AROMATIC,
    # which has no order and biotite/RDKit cannot re-derive one from ("AROM", "Y").
    return {
        Chem.BondType.SINGLE: "SING",
        Chem.BondType.DOUBLE: "DOUB",
        Chem.BondType.TRIPLE: "TRIP",
    }.get(bond.GetBondType(), "SING")


def write_pdb(mol: Chem.Mol, path: Path, component_id: str, chain: str = "L") -> None:
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
            f"HETATM{serial:5d} {atom_field} {component_id:>3} {chain}   1    "
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
        "_chem_comp.name 'RFD3 campaign ligand'",
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


def _strip_comments(value):
    """Recursively drop JSON-doesn't-support-comments '_comment'/'_...' keys from spec dicts."""
    if isinstance(value, dict):
        return {k: _strip_comments(v) for k, v in value.items() if not k.startswith("_")}
    return value


def _parse_atom_list(value: str) -> list[str]:
    return [tok.strip() for tok in value.split(",") if tok.strip()]


def _substitute_hotspots(selection: dict | str | None, ligand_key: str) -> dict | str | None:
    if not selection:
        return None
    if isinstance(selection, str):
        return selection
    substituted = {(ligand_key if k == "LIGAND" else k): v for k, v in selection.items() if v}
    return substituted or None


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--spec", type=Path, required=True, help="ligand_spec.json path")
    parser.add_argument("--component-id", required=True, help="3-letter CCD code, e.g. FHE")
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument("--seed", type=int, default=20260806)
    parser.add_argument(
        "--ligand-chain-resnum",
        default="L1",
        help="chain+resnum key to substitute for the 'LIGAND' placeholder in select_hotspots",
    )
    parser.add_argument(
        "--base-json",
        type=Path,
        default=ROOT / "oracle" / "input_dtf401_base.json",
        help="where to write the shared DesignInputSpecification fragment",
    )
    parser.add_argument(
        "--design-name",
        default="dtf401",
        help="top-level key in --base-json, and the name build_length_bins.py extends per bin",
    )
    args = parser.parse_args()

    component_id = args.component_id.upper()
    if len(component_id) > 3:
        raise SystemExit("PDB compatibility requires a component ID of at most three characters")

    spec = json.loads(args.spec.read_text())
    spec = _strip_comments(spec)
    smiles = spec["smiles"]

    mol = Chem.MolFromSmiles(smiles)
    if mol is None:
        raise SystemExit(f"RDKit could not parse spec['smiles']: {smiles!r}")
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
    Chem.Kekulize(heavy, clearAromaticFlags=False)

    all_heavy_atoms = [a.GetProp("name") for a in heavy.GetAtoms()]
    all_heavy_set = set(all_heavy_atoms)

    def _validated(key: str) -> list[str]:
        atoms = _parse_atom_list(spec[key]["LIGAND"]) if key in spec and "LIGAND" in spec.get(key, {}) else []
        bad = [a for a in atoms if a not in all_heavy_set]
        if bad:
            raise SystemExit(
                f"spec['{key}']['LIGAND'] names atoms not present on the molecule: {bad}\n"
                f"Valid heavy-atom names: {sorted(all_heavy_set)}"
            )
        return atoms

    exposed = _validated("exposed")
    buried = _parse_atom_list(spec["buried"]["LIGAND"]) if spec.get("buried", {}).get("LIGAND") else None
    if buried is None:
        buried = sorted(all_heavy_set - set(exposed))
    else:
        bad = [a for a in buried if a not in all_heavy_set]
        if bad:
            raise SystemExit(f"spec['buried']['LIGAND'] names unknown atoms: {bad}")
    hbond_donor = _validated("hbond_donor")
    hbond_acceptor = _validated("hbond_acceptor")

    hotspots_raw = spec.get("hotspots")
    if isinstance(hotspots_raw, dict) and "LIGAND" in hotspots_raw:
        bad = [a for a in _parse_atom_list(hotspots_raw["LIGAND"]) if a not in all_heavy_set]
        if bad:
            raise SystemExit(f"spec['hotspots']['LIGAND'] names unknown atoms: {bad}")

    out = args.output_dir.resolve()
    ccd_path = out / "ccd" / component_id[0] / component_id / f"{component_id}.cif"
    ccd_path.parent.mkdir(parents=True, exist_ok=True)
    out.mkdir(parents=True, exist_ok=True)
    pdb_path = out / f"{component_id}.pdb"
    write_pdb(heavy, pdb_path, component_id)
    write_ccd(heavy, ccd_path, component_id, smiles)

    manifest = {
        "component_id": component_id,
        "smiles": smiles,
        "ligand_chain_resnum": args.ligand_chain_resnum,
        "exposed_atoms": exposed,
        "buried_atoms": buried,
        "hbond_donor_atoms": hbond_donor,
        "hbond_acceptor_atoms": hbond_acceptor,
        "all_heavy_atoms": all_heavy_atoms,
        "formal_charge": sum(a.GetFormalCharge() for a in heavy.GetAtoms()),
        "pdb": str(pdb_path),
        "ccd_mirror": str(out / "ccd"),
        "seed": args.seed,
    }
    (out / "atom_selections.json").write_text(json.dumps(manifest, indent=2) + "\n")
    with (out / "atom_map.csv").open("w", newline="") as handle:
        writer = csv.writer(handle)
        writer.writerow(["rdkit_index", "atom_name", "element", "formal_charge", "class"])
        exposed_set, buried_set = set(exposed), set(buried)
        for atom in heavy.GetAtoms():
            name = atom.GetProp("name")
            cls = "exposed" if name in exposed_set else ("buried" if name in buried_set else "unassigned")
            writer.writerow([atom.GetIdx(), name, atom.GetSymbol(), atom.GetFormalCharge(), cls])

    # Assemble the DesignInputSpecification fragment shared by every length bin.
    design_input: dict = {
        "input": str(pdb_path),
        "ligand": component_id,
        "select_fixed_atoms": {component_id: "ALL"},
        "infer_ori_strategy": spec.get("infer_ori_strategy", "com"),
    }
    if exposed:
        design_input["select_exposed"] = {component_id: ",".join(exposed)}
    if buried:
        design_input["select_buried"] = {component_id: ",".join(buried)}
    if hbond_donor:
        design_input["select_hbond_donor"] = {component_id: ",".join(hbond_donor)}
    if hbond_acceptor:
        design_input["select_hbond_acceptor"] = {component_id: ",".join(hbond_acceptor)}
    hotspots = _substitute_hotspots(hotspots_raw, args.ligand_chain_resnum)
    if hotspots:
        design_input["select_hotspots"] = hotspots
    if design_input["infer_ori_strategy"] == "hotspots" and "select_hotspots" not in design_input:
        raise SystemExit("infer_ori_strategy='hotspots' requires spec['hotspots'] to be set")

    args.base_json.parent.mkdir(parents=True, exist_ok=True)
    args.base_json.write_text(json.dumps({args.design_name: design_input}, indent=2) + "\n")

    print(json.dumps({"manifest": str(out / "atom_selections.json"), "base_input_json": str(args.base_json), **manifest}, indent=2))


if __name__ == "__main__":
    main()
