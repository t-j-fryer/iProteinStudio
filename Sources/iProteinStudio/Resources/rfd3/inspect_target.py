#!/usr/bin/env python3
"""Read a target and report the sites the user can condition on, as JSON.

iProteinStudio asks the user which atoms to bury, expose, or hydrogen bond
with. For that to be safe, the vocabulary has to come from the target itself:
a hand-typed atom name that does not exist would otherwise silently produce an
unconditioned design, which looks exactly like a successful run.

Atom names follow the Boltz convention (``SYMBOL + canonical_rank + 1``) used by
``RFD3/scripts/prepare_ligand_target.py``, so the names shown in the UI are the
names RFdiffusion3 will be given.

Output (stdout, one JSON object):

    {
      "kind": "ligand" | "protein",
      "sites": [{"index","name","element","suggestions"}, ...],
      "formal_charge": int,          # ligand only
      "chains": ["A","B"],           # protein only
      "warnings": [str, ...]
    }

Errors are reported as {"error": "..."} with exit code 1, so the app can show
the reason rather than a blank list.
"""

from __future__ import annotations

import argparse
import json
import sys


def fail(message: str) -> None:
    print(json.dumps({"error": message}))
    sys.exit(1)


# --------------------------------------------------------------------- ligand

def canonical_atom_names(mol, Chem) -> dict[int, str]:
    """Return the exact atom names used by the generated RFD3 component."""
    mol_h = Chem.AddHs(mol)
    ranks = list(Chem.CanonicalRankAtoms(mol_h))
    return {
        atom.GetIdx(): f"{atom.GetSymbol().upper()}{ranks[atom.GetIdx()] + 1}"
        for atom in mol.GetAtoms()
    }


def hbond_features(mol) -> tuple[set[int], set[int]]:
    """Perceive donors/acceptors for the supplied graph and protonation state."""
    from rdkit.Chem import Lipinski

    donors = {idx for match in Lipinski._HDonors(mol) for idx in match}
    acceptors = {idx for match in Lipinski._HAcceptors(mol) for idx in match}
    return donors, acceptors


def inspect_ligand(smiles: str | None, structure: str | None, resname: str | None) -> dict:
    try:
        from rdkit import Chem
        from rdkit.Chem import AllChem
    except ImportError:
        fail("RDKit is not available in this environment. Install RFdiffusion3 support first.")

    warnings: list[str] = []

    if smiles:
        mol = _mol_from_smiles(smiles, Chem, AllChem, warnings)
    elif structure:
        mol = _mol_from_structure(structure, resname, Chem)
    else:
        fail("No SMILES and no structure file were supplied.")

    if smiles:
        names = canonical_atom_names(mol, Chem)
    else:
        names = {}
        for atom in mol.GetAtoms():
            if atom.GetPDBResidueInfo():
                names[atom.GetIdx()] = atom.GetPDBResidueInfo().GetName().strip()
            else:
                names[atom.GetIdx()] = f"{atom.GetSymbol().upper()}{atom.GetIdx() + 1}"

    try:
        donors, acceptors = hbond_features(mol)
    except Exception:
        donors, acceptors = set(), set()
        warnings.append(
            "Hydrogen-bond roles could not be perceived from this structure. "
            "Use a chemically complete SMILES to obtain donor/acceptor suggestions."
        )

    sites = []
    for atom in mol.GetAtoms():
        idx = atom.GetIdx()
        symbol = atom.GetSymbol().upper()
        suggestions = []
        # Do not call every atom without an H-bond feature "non-polar". A
        # quaternary ammonium or metal can be neither donor nor acceptor yet is
        # emphatically not a safe burial default. Limit automatic pocket packing
        # to neutral carbon/halogen atoms; the user can deliberately add other
        # burial restraints after reviewing the molecule.
        safely_hydrophobic = atom.GetFormalCharge() == 0 and atom.GetSymbol() in {
            "C", "F", "Cl", "Br", "I"
        }
        if safely_hydrophobic and idx not in donors and idx not in acceptors:
            suggestions.append({
                "condition": "buried",
                "reason": "non-polar binding-core atom — pocket packing is a useful conservative default",
            })
        if idx in donors:
            suggestions.append({
                "condition": "hbondDonor",
                "reason": "this ligand atom donates a hydrogen bond in the supplied protonation state",
            })
        if idx in acceptors:
            suggestions.append({
                "condition": "hbondAcceptor",
                "reason": "this ligand atom accepts a hydrogen bond in the supplied protonation state",
            })
        sites.append({
            "index": idx,
            "name": names[idx],
            "element": symbol,
            "suggestions": suggestions,
        })

    if len(sites) < 4:
        warnings.append("This molecule has very few heavy atoms; conditioning will have limited effect.")

    return {
        "kind": "ligand",
        "sites": sites,
        "formal_charge": sum(a.GetFormalCharge() for a in mol.GetAtoms()),
        "warnings": warnings,
    }


def _mol_from_smiles(smiles: str, Chem, AllChem, warnings: list[str]):
    """Build the heavy-atom molecule with RFD3-compatible atom names.

    This mirrors ``RFD3/scripts/prepare_ligand_target.py`` step for step, and
    that is not incidental: the canonical ranks are taken on the *hydrogen-added*
    molecule, so naming the heavy-atom molecule instead would produce a
    different, silently wrong set of names. The UI would then show atom names
    that do not exist in the component RFD3 is actually given.
    """
    mol = Chem.MolFromSmiles(smiles)
    if mol is None:
        fail("That SMILES string could not be parsed. Check for a typo or unbalanced brackets.")
    mol_h = Chem.AddHs(mol)
    ranks = list(Chem.CanonicalRankAtoms(mol_h))
    for atom, rank in zip(mol_h.GetAtoms(), ranks):
        atom.SetProp("name", f"{atom.GetSymbol().upper()}{rank + 1}")
    if AllChem.EmbedMolecule(mol_h, randomSeed=20260806) != 0:
        fail("Could not generate a 3D conformer for this molecule.")
    try:
        if AllChem.MMFFHasAllMoleculeParams(mol_h):
            AllChem.MMFFOptimizeMolecule(mol_h, maxIters=1000)
        else:
            AllChem.UFFOptimizeMolecule(mol_h, maxIters=1000)
    except Exception:
        warnings.append("Force-field clean-up was skipped for this molecule.")
    heavy = Chem.RemoveHs(mol_h, sanitize=False)
    Chem.SanitizeMol(heavy)
    return heavy


def _mol_from_structure(path: str, resname: str | None, Chem):
    """Pull one ligand residue out of a user-supplied PDB/CIF."""
    lowered = path.lower()
    if lowered.endswith((".cif", ".mmcif")):
        fail("CIF ligand extraction is not supported yet — save the ligand as a PDB, or paste its SMILES.")
    mol = Chem.MolFromPDBFile(path, removeHs=True, sanitize=False)
    if mol is None:
        fail(f"Could not read a structure from {path}.")
    if not resname:
        fail("Name the ligand residue to extract, e.g. FHE.")
    keep = [a.GetIdx() for a in mol.GetAtoms()
            if a.GetPDBResidueInfo() and a.GetPDBResidueInfo().GetResidueName().strip() == resname.strip().upper()]
    if not keep:
        present = sorted({a.GetPDBResidueInfo().GetResidueName().strip()
                          for a in mol.GetAtoms() if a.GetPDBResidueInfo()})
        fail(f"No residue named {resname!r} in that file. Found: {', '.join(present[:25])}")
    editable = Chem.RWMol(mol)
    for idx in sorted(set(range(mol.GetNumAtoms())) - set(keep), reverse=True):
        editable.RemoveAtom(idx)
    extracted = editable.GetMol()
    try:
        Chem.SanitizeMol(extracted)
    except Exception:
        # Bond orders in PDB HETATM records are frequently wrong or absent. The
        # atom set is still correct, which is what the conditioning UI needs.
        pass
    return extracted


# -------------------------------------------------------------------- protein

def inspect_protein(path: str, chain: str | None, requested_chains: str | None = None,
                    chain_count: int = 1) -> dict:
    """List residues of the target chain with a burial estimate.

    The exposure figure is a heavy-atom neighbour count, not a real SASA
    calculation. It is a coarse proxy, used only to *suggest* hotspots the user
    then confirms — never to make a decision on its own.
    """
    try:
        import numpy as np
    except ImportError:
        fail("NumPy is not available in this environment.")
    try:
        from protein_structure import read_protein_atoms
    except ImportError:
        fail("Studio's protein-structure reader is missing; reinstall the app resources.")

    aa3 = {
        "ALA": "A", "ARG": "R", "ASN": "N", "ASP": "D", "CYS": "C",
        "GLN": "Q", "GLU": "E", "GLY": "G", "HIS": "H", "ILE": "I",
        "LEU": "L", "LYS": "K", "MET": "M", "PHE": "F", "PRO": "P",
        "SER": "S", "THR": "T", "TRP": "W", "TYR": "Y", "VAL": "V",
        "MSE": "M", "SEC": "U", "PYL": "O",
    }
    coords: list[tuple[float, float, float]] = []
    labels: list[tuple[str, str, int]] = []   # (chain, resname, resnum)
    chains: set[str] = set()

    try:
        for atom in read_protein_atoms(path):
            if atom.element == "H":
                continue
            chains.add(atom.chain)
            coords.append((atom.x, atom.y, atom.z))
            labels.append((atom.chain, atom.residue, atom.residue_number))
    except (OSError, ValueError) as exc:
        fail(f"Could not read {path}: {exc}")

    if not coords:
        fail("No protein atoms found in that file. RFdiffusion3 needs a structure, not a sequence.")

    xyz = np.asarray(coords, dtype=float)
    wanted = [value.strip() for value in (requested_chains or chain or "").split(",")
              if value.strip()]
    target_chains = wanted or sorted(chains)[:max(1, chain_count)]
    missing = [value for value in target_chains if value not in chains]
    if missing:
        fail(f"Chain(s) {', '.join(missing)} are not in that file. Found: {', '.join(sorted(chains))}")

    # Neighbour count within 10 A: buried atoms are crowded, surface atoms are not.
    counts = np.zeros(len(xyz), dtype=int)
    for i in range(0, len(xyz), 512):
        block = xyz[i:i + 512]
        d = np.linalg.norm(block[:, None, :] - xyz[None, :, :], axis=-1)
        counts[i:i + 512] = (d < 10.0).sum(axis=1) - 1

    per_residue: dict[tuple[str, int], dict] = {}
    for (ch, resname, resnum), count in zip(labels, counts):
        if ch not in target_chains:
            continue
        entry = per_residue.setdefault((ch, resnum), {"resname": resname, "counts": []})
        entry["counts"].append(int(count))

    if not per_residue:
        fail(f"Selected chain(s) {', '.join(target_chains)} contain no residues.")

    means = {key: sum(v["counts"]) / len(v["counts"]) for key, v in per_residue.items()}
    values = sorted(means.values())
    # Most exposed quartile: candidates for a binding patch.
    cutoff = values[max(0, len(values) // 4 - 1)]

    sites = []
    for (ch, resnum), entry in sorted(per_residue.items(), key=lambda kv: (kv[0][0], kv[0][1])):
        exposed = means[(ch, resnum)] <= cutoff
        sites.append({
            "name": f"{ch}{resnum}",
            "element": entry["resname"],
            "suggestion": "hotspot" if exposed else None,
            "suggestionReason": ("among the most solvent-exposed quarter of this chain"
                                 if exposed else None),
        })

    sequences = []
    contigs = []
    for target_chain in target_chains:
        resnums = sorted(r for ch, r in per_residue if ch == target_chain)
        if not resnums:
            fail(f"Chain {target_chain!r} contains no protein residues.")
        sequences.append("".join(aa3.get(per_residue[(target_chain, number)]["resname"], "X")
                                 for number in resnums))
        contigs.append(f"{target_chain}{resnums[0]}-{resnums[-1]}")
    return {
        "kind": "protein",
        "sites": sites,
        "chains": sorted(chains),
        "chain": target_chains[0],
        "selected_chains": target_chains,
        "contig": ",/0,".join(contigs),
        "sequence": ":".join(sequences),
        "warnings": [
            "Exposure is estimated from a heavy-atom neighbour count, not a full "
            "solvent-accessibility calculation. Treat the suggestions as a starting point."
        ],
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--kind", choices=["ligand", "protein"], required=True)
    parser.add_argument("--smiles")
    parser.add_argument("--structure")
    parser.add_argument("--resname")
    parser.add_argument("--chain")
    parser.add_argument("--chains")
    parser.add_argument("--chain-count", type=int, default=1)
    args = parser.parse_args()

    if args.kind == "ligand":
        result = inspect_ligand(args.smiles, args.structure, args.resname)
    else:
        if not args.structure:
            fail("A protein target needs a structure file.")
        result = inspect_protein(args.structure, args.chain, args.chains, args.chain_count)

    print(json.dumps(result))


if __name__ == "__main__":
    main()
