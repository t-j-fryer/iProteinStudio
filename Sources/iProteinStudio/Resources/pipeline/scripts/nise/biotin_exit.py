"""Versioned biotin carboxamide-exit policy; no pose rotation or score changes.

Port of Validation/experiments/biotin_exit_filter_trial_v1. Passes open and
restricted; unresolved and blocked fail. The chemical graph determines atom
roles, never atom serials. This protocol is explicitly limited to free biotin.
"""
from pathlib import Path
import hashlib
import json
import math

PROTOCOL = 'biotin-carboxamide-v1'
REFERENCE = 'O=C(O)CCCC[C@@H]1SC[C@@H]2NC(=O)N[C@@H]21'


def roles(manifest):
    from rdkit import Chem
    mol = Chem.MolFromSmiles(manifest['smiles_used'])
    ref = Chem.MolFromSmiles(REFERENCE)
    if mol is None or Chem.MolToSmiles(mol) != Chem.MolToSmiles(ref):
        raise ValueError('Biotin linker-exit filtering requires the supported free-biotin chemical state and stereochemistry.')
    names = {a['index']: a['name'] for a in manifest['atoms']}
    if set(names) != set(range(mol.GetNumAtoms())) or len(set(names.values())) != len(names):
        raise ValueError('Invalid biotin atom map.')
    match = mol.GetSubstructMatches(Chem.MolFromSmarts('[C;X3](=[O;X1])([O;H1])-[#6]-[#6]'))
    if len(match) != 1:
        raise ValueError('Expected one unambiguous terminal biotin carboxyl group.')
    c, o, oh, tail, previous = match[0]
    return dict(zip(('carbonyl', 'oxygen', 'leaving', 'tail', 'previous'), (names[i] for i in (c,o,oh,tail,previous))))


def case_from_structure(path, manifest):
    import gemmi
    from ligand_atoms import audit_atoms
    audit_atoms(path, manifest)
    r = roles(manifest)
    atoms = []
    for chain in gemmi.read_structure(str(path))[0]:
        for residue in chain:
            if residue.name in ('HOH', 'WAT'):
                continue
            for a in residue:
                if a.element.name in ('H', 'D'):
                    continue
                xyz = [a.pos.x, a.pos.y, a.pos.z]
                if a.altloc != '\x00' or a.occ <= 0 or not all(math.isfinite(x) for x in xyz) or a.element.atomic_number <= 0:
                    raise ValueError('Exit geometry requires finite, occupied, unambiguous heavy atoms.')
                atoms.append(dict(name=a.name.strip(), z=a.element.atomic_number, xyz=xyz, target=chain.name=='B'))
    core = [a for a in atoms if a['target'] and a['name'] != r['leaving']]
    env = [a for a in atoms if not a['target']]
    if not env:
        raise ValueError('Exit geometry requires protein atoms.')
    order = {a['name']: i for i,a in enumerate(core)}
    byname = {a['name']: a for a in atoms if a['target']}
    c,o,t,prev = (r[k] for k in ('carbonyl','oxygen','tail','previous'))
    return dict(id=Path(path).stem, core=[a['xyz'] for a in core],core_z=[a['z'] for a in core],
        core_names=[a['name'] for a in core], environment=[a['xyz'] for a in env],environment_z=[a['z'] for a in env],
        attachment_frame=[byname[r[k]]['xyz'] for k in ('carbonyl','oxygen','leaving')],
        bonded_exclusions=[[order[n] for n in (c,o,t,prev)],[order[n] for n in (c,o,t)],[order[c]]])


def classify(case):
    from linker_geometry import evaluate, guarded
    # Clear passes take the inexpensive path. Every non-open case receives the
    # denser trial before rejection; no finite rotation is treated as a rescue.
    result = evaluate(case)
    dense = result['label'] != 'open'
    if dense:
        result = evaluate(case, nphi=72, nrays=384, grid_step=.5)
    if result['label'] == 'open':
        forward = guarded(case, nphi=24)
        result['forward'] = forward
        if not forward['broad_forward_exit']:
            result.update(label='restricted', reason='An exit exists, but broad forward access was not demonstrated.')
    result.update(protocol_version=PROTOCOL, dense_recheck=dense,
                  passed=result['label'] in ('open','restricted'), rotation_rescue=False)
    return result


def source_signature():
    h = hashlib.sha256()
    for name in ('biotin_exit.py', 'linker_geometry.py', 'atom_geometry.py', 'ligand_atoms.py'):
        h.update(name.encode()); h.update(Path(__file__).with_name(name).read_bytes())
    return h.hexdigest()

if __name__ == '__main__':
    import sys
    from ligand_atoms import resolve, validate_selection
    try:
        settings = json.load(sys.stdin)
        manifest = resolve(settings['smiles'])
        validate_selection(settings, manifest)
        print(json.dumps(roles(manifest)))
    except Exception as exc:
        print(str(exc), file=sys.stderr)
        raise SystemExit(1)
