#!/usr/bin/env python3
"""CPU-only input-order conformer and explicit linker split for the app viewer."""
import json
import sys


def preview(smiles, core=None, linker=None):
    from rdkit import Chem
    from rdkit.Chem import AllChem
    mol = Chem.MolFromSmiles(smiles)
    if mol is None or len(Chem.GetMolFrags(mol)) != 1:
        raise ValueError('Enter one connected molecule.')
    full = Chem.AddHs(mol)
    params = AllChem.ETKDGv3(); params.randomSeed = 1
    if AllChem.EmbedMolecule(full, params) != 0:
        raise ValueError('Could not generate a 3D conformer. The 2D atom selector remains available.')
    # This is a display conformer, not an inferred bound pose or tautomer search.
    result = Chem.RemoveHs(full)
    conf = result.GetConformer()
    atoms = [dict(index=a.GetIdx(), element=a.GetSymbol(), xyz=list(conf.GetAtomPosition(a.GetIdx()))) for a in result.GetAtoms()]
    bonds = [dict(a=b.GetBeginAtomIdx(), b=b.GetEndAtomIdx(), order=float(b.GetBondTypeAsDouble())) for b in result.GetBonds()]
    preset = None
    ref = Chem.MolFromSmiles('O=C(O)CCCC[C@@H]1SC[C@@H]2NC(=O)N[C@@H]21')
    if Chem.MolToSmiles(ref) == Chem.MolToSmiles(mol):
        match = mol.GetSubstructMatch(ref, useChirality=True)
        # Figure 4's nine bicyclic-core atoms, including its carbonyl oxygen.
        preset = dict(schema=1, mode='biotin-carboxamide-v1', contact_atoms=[match[i] for i in range(7,16)],
                      exposed_atoms=[], contact_distance=6.0, exposure_min_fraction=0.5)
    split = None
    if core is not None and linker is not None:
        bond = mol.GetBondBetweenAtoms(core, linker)
        if bond is None or bond.IsInRing():
            raise ValueError('Select a directed non-ring core-to-linker bond.')
        edited = Chem.RWMol(mol); edited.RemoveBond(core, linker)
        parts = Chem.GetMolFrags(edited)
        if len(parts) != 2:
            raise ValueError('The selected bond does not separate one core and one linker.')
        split = dict(core=list(next(p for p in parts if core in p)), linker=list(next(p for p in parts if linker in p)))
    return dict(smiles=smiles, atoms=atoms, bonds=bonds, sdf=Chem.MolToMolBlock(result), figure4_preset=preset, split=split)


if __name__ == '__main__':
    try:
        req = json.loads(sys.argv[2]) if len(sys.argv) > 2 and sys.argv[1] == '--json' else json.load(sys.stdin) if len(sys.argv) == 1 else dict(smiles=sys.argv[1])
        print(json.dumps(preview(req['smiles'], req.get('core'), req.get('linker')), allow_nan=False))
    except Exception as exc:
        print(json.dumps(dict(error=str(exc)))); sys.exit(1)
