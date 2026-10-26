"""Audited CCD chemistry and paired motif-preserving sequence-design inputs.

Uses the installed Boltz CCD cache's native chemical graphs; no graph guessing
from atom distances and no download. Preparation alone does not run a model.
"""
import json
from pathlib import Path
import pickle
from .contract import atomic, digest
from .geometry import read, LETTERS, heavy


def molecule(cache, component, expected):
    from rdkit import Chem
    path = Path(cache) / (component + '.pkl')
    if not path.is_file():
        raise ValueError('Missing installed CCD graph: ' + component)
    # Only the managed, preinstalled model cache is accepted by callers.
    mol = Chem.RemoveHs(pickle.loads(path.read_bytes()))
    atoms = {a.GetProp('name'): a for a in mol.GetAtoms()}
    if len(atoms) != mol.GetNumAtoms() or set(atoms) != set(expected):
        raise ValueError(f'{component}: CCD/fixture heavy-atom sets differ; '
                         f'CCD-only={sorted(set(atoms) - set(expected))}, fixture-only={sorted(set(expected) - set(atoms))}. '
                         'Resolve a chemical variant explicitly before prediction or sequence design.')
    for name, atom in atoms.items():
        if atom.GetSymbol().upper() != expected[name]['element'].upper():
            raise ValueError(component + ': CCD element mismatch at ' + name)
    return mol, dict(component=component, ccd_sha256=digest(path),
                    smiles=Chem.MolToSmiles(mol, isomericSmiles=True),
                    formal_charge=Chem.GetFormalCharge(mol),
                    atoms=[dict(name=a.GetProp('name'), index=a.GetIdx(), element=a.GetSymbol(),
                                charge=a.GetFormalCharge(), chiral_tag=str(a.GetChiralTag())) for a in mol.GetAtoms()],
                    bonds=[dict(a=b.GetBeginAtom().GetProp('name'), b=b.GetEndAtom().GetProp('name'),
                                order=str(b.GetBondType()), stereo=str(b.GetStereo())) for b in mol.GetBonds()])


def chemistry_audit(case, cache):
    records, failures = [], []
    for ligand in case['ligands']:
        identity = f"{ligand['chain']}:{ligand['residue']}:{ligand['component']}"
        try:
            _, record = molecule(cache, ligand['component'], heavy(ligand))
            records.append(dict(instance=identity, **record))
        except ValueError as exc:
            failures.append(dict(instance=identity, error=str(exc)))
    return dict(ready=not failures, components=records, blockers=failures,
                chemical_state='Installed CCD charge/tautomer/stereochemistry; no pH optimisation.')


def prepare(reference, current, cache, output):
    """Same heavy geometry for both designers, catalytic identities locked."""
    from rdkit import Chem
    import gemmi
    reference, current, output = Path(reference), Path(current), Path(output)
    ref = json.loads(reference.read_text()); present = read(current)
    expected_keys = set(ref['atoms'])
    if set(present) != expected_keys:
        raise ValueError('Sequence-design structure changed its molecular instance set.')
    for key, component in ref['identities'].items():
        if present[key]['component'] != component:
            raise ValueError('Input catalytic identity changed: ' + key)
    chemistry = []
    structure = gemmi.read_structure(str(current))
    for chain in structure[0]:
        for residue in chain:
            key = f'{chain.name}:{residue.seqid.num}:{residue.seqid.icode.strip()}'
            for atom in residue:
                atom.b_iso = 1.0 if key in ref['identities'] else 0.0
    for ligand in ref['ligands']:
        key = ligand['key']; residue = present[key]
        if residue['component'] != ligand['component'] or set(residue['atoms']) != set(ligand['atoms']):
            raise ValueError('Ligand changed before sequence design: ' + key)
        mol, record = molecule(cache, ligand['component'], residue['atoms'])
        conformer = Chem.Conformer(mol.GetNumAtoms())
        for a in mol.GetAtoms(): conformer.SetAtomPosition(a.GetIdx(), residue['atoms'][a.GetProp('name')]['xyz'])
        mol.RemoveAllConformers(); mol.AddConformer(conformer)
        protonated = Chem.AddHs(mol, addCoords=True)
        cid, number, _ = key.split(':')
        target = next(r for r in structure[0][cid] if r.seqid.num == int(number))
        # Existing hydrogens are replaced under this recorded CCD chemical state.
        target.remove_hydrogens()
        names = set(residue['atoms']); added = []
        for a in protonated.GetAtoms():
            if a.GetAtomicNum() != 1: continue
            name = 'H' + str(a.GetIdx() + 1)
            if name in names or len(name) > 4:
                raise ValueError('Cannot assign unique PDB hydrogen labels.')
            p = protonated.GetConformer().GetAtomPosition(a.GetIdx())
            atom = gemmi.Atom(); atom.name = name; atom.element = gemmi.Element('H')
            atom.pos = gemmi.Position(p.x, p.y, p.z); atom.occ = 1.0; atom.b_iso = 0
            target.add_atom(atom); added.append(name)
        chemistry.append(dict(instance=key, added_hydrogens=added, **record))
    spec = dict(reference_sha256=digest(reference), current_sha256=digest(current), chemistry=chemistry)
    marker = output / 'designers.json'
    if marker.exists():
        saved = json.loads(marker.read_text())
        if saved['input'] != spec or any(digest(output / n) != h for n, h in saved['files'].items()):
            raise ValueError('Sequence-design inputs or artifacts changed.')
        return saved
    output.mkdir(parents=True, exist_ok=True)
    heavy_pdb = output / 'ligandmpnn.pdb'
    heavy_structure = gemmi.read_structure(str(current)); heavy_structure.remove_hydrogens()
    heavy_structure.write_pdb(str(heavy_pdb))
    laser_pdb = output / 'lasermpnn.pdb'; structure.write_pdb(str(laser_pdb))
    fixed = ' '.join(k.split(':')[0] + k.split(':')[1] for k in ref['identities'])
    atomic(output / 'fixed_residues.json', {str(heavy_pdb.resolve()): fixed})
    # Prove that protonation did not change any heavy coordinate or name.
    if read(laser_pdb) != {k: {**v, 'atoms': {a: {**x, 'b': 1.0 if k in ref['identities'] else 0.0}
                                          for a, x in v['atoms'].items()}} for k, v in present.items()}:
        raise ValueError('Protonation changed heavy atoms.')
    result = dict(input=spec, ligandmpnn_args=['--fixed_residues_multi', str((output / 'fixed_residues.json').resolve()),
                                             '--chains_to_design', 'A'],
                  lasermpnn_args=['--fix_beta'], locked_positions=fixed,
                  files={p.name: digest(p) for p in (heavy_pdb, laser_pdb, output / 'fixed_residues.json')},
                  qualification='Prepared atom/identity masks; model sampling and retention still require smoke tests.')
    atomic(marker, result)
    return result


def validate_sequence(reference, sequence):
    ref = json.loads(Path(reference).read_text())
    if len(sequence) != len(ref['backbone_atoms']) or set(sequence) - set(LETTERS.values()):
        raise ValueError('Designer returned an incomplete or incorrectly sized sequence.')
    for key, component in ref['identities'].items():
        if sequence[int(key.split(':')[1]) - 1] != LETTERS[component]:
            raise ValueError('Designer mutated a locked catalytic residue; proposal rejected.')
