#!/usr/bin/env python
"""Prepare a LASErMPNN input PDB from a NanoHunter predicted co-structure.

LASErMPNN was trained on *protonated* structures and expects the ligand to
carry explicit hydrogens in the correct protonation state (see the LASErMPNN
README and the NISE ``protonate_and_add_conect_records.py`` helper). The
protonation state is defined entirely by the ligand SMILES from the design
template, so we reprotonate the predicted ligand pose against that SMILES
rather than guessing a pH model.

This helper does three things in one prody/RDKit pass:

1. Reprotonates the predicted ligand: bond orders are re-assigned from the
   SMILES template, then RDKit adds coordinate-bearing hydrogens consistent
   with the SMILES formal charges (e.g. deprotonated carboxylates/phenolates
   stay deprotonated). CONECT records are emitted for the ligand.
2. Sets protein B-factors for LASErMPNN's ``--fix_beta`` convention: designed
   positions get B-factor 0.0, fixed positions get B-factor 1.0.
3. Writes a merged ``protein + protonated ligand`` PDB with CONECT records.

The protonation logic mirrors polizzilab/NISE so behaviour matches the method
as published; the B-factor masking is the NanoHunter addition needed to hold
the framework / non-redesigned residues fixed.
"""

import io
import sys
import argparse
from pathlib import Path
from collections import defaultdict

import prody as pr
from rdkit import Chem
from rdkit.Chem import AllChem


def _parse_positions(spec):
    """Parse a whitespace/comma separated list of 1-based residue numbers.

    Returns None for the sentinel ``all`` (design every protein residue).
    """
    if spec is None:
        return None
    spec = spec.strip()
    if spec == "" or spec.lower() == "all":
        return None
    out = set()
    for tok in spec.replace(",", " ").split():
        # Tokens may look like "A12" or "12"; take the trailing integer.
        digits = "".join(ch for ch in tok if ch.isdigit())
        if not digits:
            raise ValueError(f"Invalid residue token: {tok!r}")
        out.add(int(digits))
    return out


def _mol_from_template_coords(lig_atoms, smiles):
    """Build a protonated RDKit mol by transferring the predicted heavy-atom
    coordinates onto the SMILES template *by atom order*, then AddHs.

    Boltz emits ligand heavy atoms in the same order as RDKit's
    ``MolFromSmiles(smiles)`` (verified), so this avoids PDB bond perception
    entirely — no proximity bonding, no valence errors on odd predicted poses.
    Returns None if the order/count/elements do not line up (caller falls back).
    """
    from rdkit.Geometry import Point3D
    tmpl = Chem.MolFromSmiles(smiles)
    if tmpl is None:
        return None
    tmpl_syms = [a.GetSymbol() for a in tmpl.GetAtoms()]  # heavy only (no explicit H yet)
    coords = lig_atoms.getCoords()
    elems = [str(e).strip().capitalize() for e in lig_atoms.getElements()]
    if len(coords) != len(tmpl_syms):
        return None
    if [s.capitalize() for s in tmpl_syms] != elems:
        return None
    conf = Chem.Conformer(tmpl.GetNumAtoms())
    for i, (x, y, z) in enumerate(coords):
        conf.SetAtomPosition(i, Point3D(float(x), float(y), float(z)))
    tmpl.AddConformer(conf, assignId=True)
    return Chem.AddHs(tmpl, addCoords=True)


def protonate_ligand(lig_atoms, smiles):
    """Return a prody AtomGroup of the ligand with SMILES-consistent hydrogens
    and the RDKit-derived CONECT record lines (unoffset)."""
    resnames = set(lig_atoms.getResnames())
    if len(resnames) != 1:
        raise ValueError(
            "Expected exactly one ligand residue name, found: "
            f"{sorted(resnames)}. Rename/deduplicate hetero atoms."
        )
    tlc = resnames.pop()

    # Preferred: transfer predicted coords onto the SMILES template by atom order.
    mol = _mol_from_template_coords(lig_atoms, smiles)
    if mol is None:
        # Fallback: perceive bonds from the PDB and re-assign from the template.
        sstream = io.StringIO()
        pr.writePDBStream(sstream, lig_atoms)
        pdb_mol = Chem.MolFromPDBBlock(sstream.getvalue(), removeHs=True, sanitize=False)
        if pdb_mol is None:
            raise ValueError("RDKit could not parse the predicted ligand PDB block.")
        smi_mol = Chem.MolFromSmiles(smiles)
        if smi_mol is None:
            raise ValueError(f"RDKit could not parse the ligand SMILES: {smiles!r}")
        pdb_mol = AllChem.AssignBondOrdersFromTemplate(smi_mol, pdb_mol)
        mol = AllChem.AddHs(pdb_mol, addCoords=True)

    rdkit_block = Chem.MolToPDBBlock(mol, flavor=(4 | 8))
    conect = [ln for ln in rdkit_block.split("\n") if ln.startswith("CONECT")]

    modlig = pr.parsePDBStream(io.StringIO(rdkit_block))
    modlig.setResnames(tlc)
    modlig.setResnums(1)
    modlig.setChids("B")
    modlig.setOccupancies(1.0)
    modlig.setBetas(0.0)

    # Sequentially rename atoms by element so names stay unique after AddHs.
    new_names = []
    counts = defaultdict(int)
    for name in modlig.getNames():
        element = "".join(ch for ch in name if not ch.isdigit())
        counts[element] += 1
        new_names.append(f"{element}{counts[element]}")
    modlig.setNames(new_names)
    return modlig, conect


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--in-pdb", required=True)
    ap.add_argument("--out-pdb", required=True)
    ap.add_argument("--smiles", required=True, help="Ligand SMILES (defines protonation state).")
    ap.add_argument(
        "--designed-positions",
        default="all",
        help="1-based protein residue numbers to design (space/comma separated), "
        "or 'all' to design every protein residue. Positions NOT listed are fixed "
        "(B-factor 1.0) for LASErMPNN --fix_beta.",
    )
    ap.add_argument(
        "--fixed-positions",
        default=None,
        help="Alternative to --designed-positions: 1-based residue numbers to FIX "
        "(B-factor 1.0); all others are designed. Mutually exclusive with a "
        "non-'all' --designed-positions.",
    )
    ap.add_argument("--protein-chain", default="A")
    args = ap.parse_args()

    designed = _parse_positions(args.designed_positions)
    fixed = _parse_positions(args.fixed_positions)
    if designed is not None and fixed is not None:
        raise SystemExit("Pass only one of --designed-positions / --fixed-positions.")

    st = pr.parsePDB(args.in_pdb)
    if st is None:
        raise SystemExit(f"Could not parse input PDB: {args.in_pdb}")

    prot = st.select("protein")
    if prot is None:
        raise SystemExit("No protein atoms found in input PDB.")
    prot = prot.copy()

    lig = st.select("(not protein) and (not water) and (not element H)")
    if lig is None:
        raise SystemExit(
            "No ligand (non-protein) atoms found. LASErMPNN is only wired in for "
            "small-molecule minibinder design; the predicted structure must contain a ligand."
        )
    lig = lig.copy()

    modlig, conect = protonate_ligand(lig, args.smiles)

    # B-factor masking on the protein: fixed -> 1.0, designed -> 0.0.
    #   --designed-positions X : design X, fix the rest
    #   --fixed-positions Y    : fix Y, design the rest
    #   neither (or 'all')     : design everything (no residue fixed)
    fixed_count = 0
    for res in prot.getHierView().iterResidues():
        num = res.getResnum()
        if fixed is not None:
            design_this = num not in fixed
        else:
            design_this = (designed is None) or (num in designed)
        beta = 0.0 if design_this else 1.0
        if not design_this:
            fixed_count += 1
        for atom in res:
            atom.setBeta(beta)

    # Merge protein + protonated ligand and offset CONECT records.
    prot_len = len(prot)
    merged = io.StringIO()
    pr.writePDBStream(merged, prot + modlig)
    merged_text = merged.getvalue()
    if "TER " in merged_text:
        prot_len += 1  # account for the TER record between protein and ligand

    offset_conect = []
    for rec in conect:
        head, *idxs = rec.split()
        offset_conect.append(head + "".join(str(int(i) + prot_len).rjust(5) for i in idxs))

    with open(args.out_pdb, "w") as fh:
        fh.write(merged_text.rsplit("END", 1)[0] + "\n".join(offset_conect) + "\n")

    total_res = prot.getHierView().numResidues()
    sys.stderr.write(
        f"[lasermpnn_prepare_input] wrote {args.out_pdb}: "
        f"{total_res} protein residues ({fixed_count} fixed / {total_res - fixed_count} designed), "
        f"ligand {len(modlig)} atoms (protonated from SMILES).\n"
    )


if __name__ == "__main__":
    main()
