"""One explicit chemical state and atom identity for Studio ligand NISE.

Run in the pinned Boltz environment. Display the *standardized* molecule so no
substructure-match guess is needed to translate a click on the original SMILES.
"""
import hashlib
import json
import sys
from pathlib import Path


def resolve(smiles):
    from rdkit import Chem, rdBase
    from rdkit.Chem import AllChem
    import boltz.data.parse.schema as schema
    original = smiles.strip()
    mol = Chem.MolFromSmiles(original)
    if mol is None or len(Chem.GetMolFrags(mol)) != 1 or mol.GetNumHeavyAtoms() < 3:
        raise ValueError('Enter one connected small molecule with at least three heavy atoms.')
    used = schema.standardize(original)
    if not used or schema.standardize(used) != used:
        raise ValueError('Boltz affinity standardization failed or is not stable; no atom names may be guessed.')
    mol = Chem.MolFromSmiles(used)
    if mol is None or len(Chem.GetMolFrags(mol)) != 1 or mol.GetNumHeavyAtoms() != Chem.MolFromSmiles(original).GetNumHeavyAtoms():
        raise ValueError('Boltz standardization changed the heavy-atom count or connectivity; inspect the molecule first.')
    molecule = Chem.AddHs(mol)
    ranks = Chem.CanonicalRankAtoms(molecule)
    Chem.AssignStereochemistry(molecule, force=True, cleanIt=True)
    names = [a.GetSymbol().upper() + str(rank + 1) for a, rank in zip(molecule.GetAtoms(), ranks)]
    heavy = [a for a in molecule.GetAtoms() if a.GetAtomicNum() != 1]
    if any(len(names[a.GetIdx()]) > 4 for a in heavy):
        raise ValueError('Boltz ligand atom names exceed the supported PDB width.')
    identity = dict(schema=1, input_smiles=original, smiles_used=used,
                    atoms=[dict(name=names[a.GetIdx()], el=a.GetSymbol(), index=i) for i, a in enumerate(heavy)],
                    rdkit_version=rdBase.rdkitVersion,
                    boltz_parser_sha256=hashlib.sha256(Path(schema.__file__).read_bytes()).hexdigest())
    signature = hashlib.sha256(json.dumps(identity, sort_keys=True).encode()).hexdigest()
    if AllChem.EmbedMolecule(molecule, randomSeed=1) != 0:
        raise ValueError('Could not generate the ligand conformer for automatic contact selection.')
    optimization_status = int(AllChem.MMFFOptimizeMolecule(molecule))
    if optimization_status < 0:
        raise ValueError('MMFF parameters are unavailable for the automatic contact-selection conformer.')
    conf = molecule.GetConformer()
    atoms = [dict(atom, **dict(zip(('x', 'y', 'z'), map(float, conf.GetAtomPosition(a.GetIdx())))))
             for atom, a in zip(identity['atoms'], heavy)]
    return dict(identity, atoms=atoms, signature=signature, standardized=True,
                chemical_state_changed=Chem.MolToSmiles(Chem.MolFromSmiles(original)) != Chem.MolToSmiles(mol),
                display_smiles=used, input_order_names=[a['name'] for a in atoms],
                mapped_to_input_order=False, affinity=True, conformer_mmff_status=optimization_status)


def validate_selection(settings, manifest):
    names = {a['name'] for a in manifest['atoms']}
    selected = set(settings.get('hotspot_atoms', [])) | set(settings.get('exposed_atoms', []))
    if selected and settings.get('ligand_atom_signature') != manifest['signature']:
        raise ValueError('Saved NISE atom selections are stale. Reload the molecule and select its atoms again.')
    if set(settings.get('exposed_atoms', [])) == names:
        raise ValueError('Leave at least one ligand atom available for binding.')
    if selected - names:
        raise ValueError('Unknown NISE ligand atoms: ' + ', '.join(sorted(selected - names)))


def contact_atoms(manifest, k=5, excluded=()):
    import numpy as np
    atoms = [a for a in manifest['atoms'] if a['name'] not in excluded]
    if not atoms:
        raise ValueError('Leave at least one atom available for a binding contact.')
    names = [a['name'] for a in atoms]
    if len(atoms) <= k:
        return names
    coords = np.array([[a['x'], a['y'], a['z']] for a in atoms])
    i, j = np.unravel_index(np.sum((coords[:, None] - coords[None, :])**2, axis=-1).argmax(), (len(atoms), len(atoms)))
    axis = coords[j] - coords[i]
    proj = (coords - coords[i]) @ (axis / (np.linalg.norm(axis) + 1e-9))
    chosen = []
    for target in np.linspace(proj.min(), proj.max(), k):
        chosen.append(next(int(i) for i in np.argsort(abs(proj - target)) if i not in chosen))
    return [names[i] for i in chosen]


def audit_atoms(path, manifest):
    import gemmi
    model = gemmi.read_structure(str(path))[0]
    observed = [(a.name.strip(), a.element.name.upper()) for c in model if c.name == 'B'
                for r in c for a in r if a.element.name not in ('H', 'D')]
    expected = [(a['name'], a['el'].upper()) for a in manifest['atoms']]
    if len(observed) != len(expected) or set(observed) != set(expected):
        raise ValueError('Ligand atom names/elements differ from the saved Boltz atom map; refusing guessed correspondence.')


def audit_nesso_ligand(smiles, directory, assign_names):
    # These pickles are generated locally by NESSO's parser, not user uploads.
    import pickle
    from rdkit import Chem
    paths = list(directory.glob('*.pkl'))
    if len(paths) != 1:
        raise ValueError('NESSO did not prepare exactly one ligand molecule.')
    with paths[0].open('rb') as stream:
        mol = pickle.load(stream)
    expected = Chem.MolToSmiles(Chem.MolFromSmiles(smiles))
    observed = Chem.MolToSmiles(Chem.RemoveHs(mol))
    if observed != expected:
        raise ValueError('NESSO changed the ligand chemical graph or chemical state.')
    assign_names(mol)  # RDKit pickles may omit atom properties; use NESSO itself.
    atoms = [dict(index=a.GetIdx(), name=a.GetProp('name'), element=a.GetSymbol()) for a in mol.GetAtoms()]
    if len({a['name'] for a in atoms}) != len(atoms):
        raise ValueError('NESSO produced duplicate ligand atom names.')
    return dict(smiles_used=smiles, canonical_smiles=observed, atoms=atoms,
                naming='NESSO-native; no Boltz indices or constraints supplied')


if __name__ == '__main__':
    try:
        print(json.dumps(resolve(sys.argv[1])))
    except Exception as exc:
        print(json.dumps({'error': str(exc)}))
        sys.exit(1)
