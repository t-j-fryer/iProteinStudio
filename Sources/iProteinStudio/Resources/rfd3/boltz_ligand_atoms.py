#!/usr/bin/env python3
"""Report the ligand atom names Boltz will use, so constraints can address them.

Boltz names ligand atoms as ``element symbol + canonical RDKit rank + 1`` — and,
when the affinity head is enabled, it first *standardises* the SMILES, which
changes the canonical ranks and therefore the names. So an atom called ``O21``
with affinity off may be ``O23`` with affinity on. Names must be regenerated
whenever the SMILES, charge state, stereochemistry, or the affinity setting
changes; caching them across such a change is a silent way to constrain the
wrong atoms.

This mirrors NanoHunter's own ``scripts/nise/boltz_ligand_atoms.py`` exactly,
including the standardisation step, and must be run in the Boltz environment so
that `boltz.data.parse.schema.standardize` is the one Boltz will actually apply.

Usage:  boltz_ligand_atoms.py <smiles> <affinity 0|1>
Output: {"atoms": [{"name","el","x","y","z"}, ...], "standardized": bool}
"""

from __future__ import annotations

import json
import sys


def fail(message: str) -> None:
    print(json.dumps({"error": message}))
    sys.exit(1)


def neutral_match(Chem, target, source):
    """Match two molecules that differ only in protonation."""
    def flatten(mol):
        copy = Chem.RWMol(mol)
        for atom in copy.GetAtoms():
            atom.SetFormalCharge(0)
            atom.SetNumExplicitHs(0)
            atom.SetNoImplicit(True)
        flat = copy.GetMol()
        try:
            Chem.SanitizeMol(flat, Chem.SanitizeFlags.SANITIZE_ALL
                             ^ Chem.SanitizeFlags.SANITIZE_PROPERTIES)
        except Exception:
            pass
        return flat
    try:
        return flatten(source).GetSubstructMatch(flatten(target))
    except Exception:
        return ()


def main() -> None:
    if len(sys.argv) < 2:
        fail("No SMILES supplied.")
    smiles = sys.argv[1]
    affinity = len(sys.argv) > 2 and sys.argv[2] == "1"

    try:
        from rdkit import Chem
        from rdkit.Chem import AllChem
        from rdkit import RDLogger
        RDLogger.DisableLog("rdApp.*")
    except ImportError:
        fail("RDKit is not available in this environment.")

    standardize = None
    try:
        from boltz.data.parse.schema import standardize as _standardize
        standardize = _standardize
    except Exception:
        standardize = None

    sequence = smiles
    standardized = False
    if affinity and standardize is not None:
        try:
            candidate = standardize(smiles)
            if candidate:
                sequence, standardized = candidate, True
        except Exception:
            # Better to report unstandardised names and say so than to guess.
            standardized = False

    mol = AllChem.MolFromSmiles(sequence)
    if mol is None:
        fail("That SMILES could not be parsed by RDKit.")
    mol = AllChem.AddHs(mol)
    canonical_order = AllChem.CanonicalRankAtoms(mol)
    Chem.AssignStereochemistry(mol, force=True, cleanIt=True)
    names = [a.GetSymbol().upper() + str(rank + 1)
             for a, rank in zip(mol.GetAtoms(), canonical_order)]

    if AllChem.EmbedMolecule(mol, randomSeed=1) != 0:
        fail("Could not generate a 3D conformer for this molecule.")
    try:
        AllChem.MMFFOptimizeMolecule(mol)
    except Exception:
        pass

    conf = mol.GetConformer()
    atoms = []
    for i, atom in enumerate(mol.GetAtoms()):
        if atom.GetAtomicNum() == 1:
            continue
        p = conf.GetAtomPosition(i)
        atoms.append({"name": names[i], "el": atom.GetSymbol(),
                      "x": round(p.x, 3), "y": round(p.y, 3), "z": round(p.z, 3)})

    # Map the *input* SMILES' heavy-atom order onto these names, so a click on
    # the 2D depiction (which is drawn from the input SMILES) can be turned into
    # the name Boltz will recognise. Standardisation can change the graph, in
    # which case there is no honest mapping and the UI must fall back to a list.
    input_order_names, mapped = [], False
    try:
        target = Chem.MolFromSmiles(smiles)
        source = Chem.RemoveHs(mol)
        if target is not None and target.GetNumAtoms() == source.GetNumAtoms():
            match = source.GetSubstructMatch(target)
            if not match:
                # Affinity standardisation changes protonation, so a charged
                # input will not match the standardised molecule atom for atom.
                # The heavy-atom skeleton is unchanged, so compare that instead —
                # which is exactly the correspondence the depiction needs.
                match = neutral_match(Chem, target, source)
            if match and len(match) == target.GetNumAtoms():
                heavy_names = [a["name"] for a in atoms]
                input_order_names = [heavy_names[match[i]] for i in range(target.GetNumAtoms())]
                mapped = True
    except Exception:
        mapped = False

    print(json.dumps({
        "atoms": atoms,
        "affinity": affinity,
        "standardized": standardized,
        "smiles_used": sequence,
        "input_order_names": input_order_names,
        "mapped_to_input_order": mapped,
    }))


if __name__ == "__main__":
    main()
