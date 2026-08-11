#!/usr/bin/env python3
"""Read a target and report the sites the user can condition on, as JSON.

NanoHunter Studio asks the user which atoms to bury, expose, or hydrogen bond
with. For that to be safe, the vocabulary has to come from the target itself:
a hand-typed atom name that does not exist would otherwise silently produce an
unconditioned design, which looks exactly like a successful run.

Atom names follow the Boltz convention (``SYMBOL + canonical_rank + 1``) used by
``RFD3/scripts/prepare_ligand_target.py``, so the names shown in the UI are the
names RFdiffusion3 will be given.

Output (stdout, one JSON object):

    {
      "kind": "ligand" | "protein",
      "sites": [{"name","element","suggestion","suggestionReason"}, ...],
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

# Groups worth keeping solvent-exposed by default: conjugation handles and
# solubilising tails. Burying a linker is the classic way to design a binder
# that cannot then be attached to anything.
EXPOSURE_SMARTS = [
    # Whole linker arms first, so the atoms between the anchor and the tip are
    # caught too. Matching only the amide would bury the middle of a linker.
    ("C(=O)N[CX4][CX4][OX2H]", "hydroxyalkyl-amide linker — keep the whole arm reachable"),
    ("C(=O)N[CX4][CX4][NX3]", "aminoalkyl-amide linker — keep the whole arm reachable"),
    ("[NX3][CX4][CX4][OX2H]", "aminoalcohol arm — a conjugation handle"),
    ("C(=O)N", "amide — a common conjugation handle"),
    ("[OX2H]", "hydroxyl — often a linker attachment point"),
    ("[NX3;H2]", "primary amine — often a linker attachment point"),
    ("C(=O)[OX2H1,OX1-]", "carboxylate — usually solvent-facing"),
    ("OCCO", "ethylene-glycol-like tail — solubilising"),
    ("[SX2H]", "thiol — a conjugation handle"),
    ("[N+](=O)[O-]", "nitro — strongly polar"),
]


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

    # Names are carried on the atoms by _mol_from_smiles (canonical ranks taken
    # on the hydrogen-added molecule, exactly as prepare_ligand_target.py does).
    # Structure-derived molecules fall back to their PDB atom names.
    names = {}
    for atom in mol.GetAtoms():
        if atom.HasProp("name"):
            names[atom.GetIdx()] = atom.GetProp("name")
        elif atom.GetPDBResidueInfo():
            names[atom.GetIdx()] = atom.GetPDBResidueInfo().GetName().strip()
        else:
            names[atom.GetIdx()] = f"{atom.GetSymbol().upper()}{atom.GetIdx() + 1}"

    # Suggestions: expose recognised handles, bury the hydrophobic core, and
    # mark polar atoms as hydrogen-bond partners.
    suggestions: dict[int, tuple[str, str]] = {}
    for smarts, reason in EXPOSURE_SMARTS:
        patt = Chem.MolFromSmarts(smarts)
        if patt is None:
            continue
        for match in mol.GetSubstructMatches(patt):
            for idx in match:
                suggestions.setdefault(idx, ("exposed", reason))

    sites = []
    for atom in mol.GetAtoms():
        idx = atom.GetIdx()
        symbol = atom.GetSymbol().upper()
        if idx in suggestions:
            suggestion, reason = suggestions[idx]
        elif symbol in ("N", "O") and atom.GetTotalNumHs() > 0:
            suggestion, reason = "hbondAcceptor", "polar donor — a good hydrogen-bonding partner"
        elif symbol in ("N", "O"):
            suggestion, reason = "hbondDonor", "polar acceptor — a good hydrogen-bonding partner"
        else:
            suggestion, reason = "buried", "non-polar — packing protein around it drives affinity"
        sites.append({
            "name": names[idx],
            "element": symbol,
            "suggestion": suggestion,
            "suggestionReason": reason,
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

def inspect_protein(path: str, chain: str | None) -> dict:
    """List residues of the target chain with a burial estimate.

    The exposure figure is a heavy-atom neighbour count, not a real SASA
    calculation. It is a coarse proxy, used only to *suggest* hotspots the user
    then confirms — never to make a decision on its own.
    """
    try:
        import numpy as np
    except ImportError:
        fail("NumPy is not available in this environment.")

    coords: list[tuple[float, float, float]] = []
    labels: list[tuple[str, str, int]] = []   # (chain, resname, resnum)
    chains: set[str] = set()

    try:
        with open(path, "r") as handle:
            for line in handle:
                if not line.startswith("ATOM"):
                    continue
                element = line[76:78].strip() or line[12:16].strip()[:1]
                if element == "H":
                    continue
                ch = line[21].strip() or "A"
                chains.add(ch)
                try:
                    resnum = int(line[22:26])
                    xyz = (float(line[30:38]), float(line[38:46]), float(line[46:54]))
                except ValueError:
                    continue
                coords.append(xyz)
                labels.append((ch, line[17:20].strip(), resnum))
    except OSError as exc:
        fail(f"Could not read {path}: {exc}")

    if not coords:
        fail("No protein atoms found in that file. RFdiffusion3 needs a structure, not a sequence.")

    xyz = np.asarray(coords, dtype=float)
    target_chain = (chain or "").strip() or sorted(chains)[0]
    if target_chain not in chains:
        fail(f"Chain {target_chain!r} is not in that file. Found: {', '.join(sorted(chains))}")

    # Neighbour count within 10 A: buried atoms are crowded, surface atoms are not.
    counts = np.zeros(len(xyz), dtype=int)
    for i in range(0, len(xyz), 512):
        block = xyz[i:i + 512]
        d = np.linalg.norm(block[:, None, :] - xyz[None, :, :], axis=-1)
        counts[i:i + 512] = (d < 10.0).sum(axis=1) - 1

    per_residue: dict[tuple[str, int], dict] = {}
    for (ch, resname, resnum), count in zip(labels, counts):
        if ch != target_chain:
            continue
        entry = per_residue.setdefault((ch, resnum), {"resname": resname, "counts": []})
        entry["counts"].append(int(count))

    if not per_residue:
        fail(f"Chain {target_chain!r} contains no residues.")

    means = {key: sum(v["counts"]) / len(v["counts"]) for key, v in per_residue.items()}
    values = sorted(means.values())
    # Most exposed quartile: candidates for a binding patch.
    cutoff = values[max(0, len(values) // 4 - 1)]

    sites = []
    for (ch, resnum), entry in sorted(per_residue.items(), key=lambda kv: kv[0][1]):
        exposed = means[(ch, resnum)] <= cutoff
        sites.append({
            "name": f"{ch}{resnum}",
            "element": entry["resname"],
            "suggestion": "hotspot" if exposed else None,
            "suggestionReason": ("among the most solvent-exposed quarter of this chain"
                                 if exposed else None),
        })

    resnums = sorted(r for _, r in per_residue)
    return {
        "kind": "protein",
        "sites": sites,
        "chains": sorted(chains),
        "chain": target_chain,
        "contig": f"{target_chain}{resnums[0]}-{resnums[-1]}",
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
    args = parser.parse_args()

    if args.kind == "ligand":
        result = inspect_ligand(args.smiles, args.structure, args.resname)
    else:
        if not args.structure:
            fail("A protein target needs a structure file.")
        result = inspect_protein(args.structure, args.chain)

    print(json.dumps(result))


if __name__ == "__main__":
    main()
