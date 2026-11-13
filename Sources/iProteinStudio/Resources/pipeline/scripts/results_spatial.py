#!/usr/bin/env python3
"""Explicit, resumable CPU-only review of exact saved poses; never edits a run."""
import argparse
import hashlib
import fcntl
import json
import math
from pathlib import Path
import re
import sys
import tempfile

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE / 'nise'))

def sha(path): return hashlib.sha256(Path(path).read_bytes()).hexdigest()
def canonical(value): return json.dumps(value, sort_keys=True, separators=(',', ':'), ensure_ascii=False, allow_nan=False)
def digest(value): return hashlib.sha256(canonical(value).encode()).hexdigest()
def tokens(value): return [v for v in re.split(r'[,;\s]+', value.strip()) if v]

def validate(policy):
    if policy.get('schema') != 1 or policy.get('mode') not in ('protein', 'ligand') or policy.get('coverage') not in ('all', 'any'):
        raise ValueError('Unsupported spatial review policy.')
    if not tokens(policy['binderChains']) or not policy['targetChain'].strip() :
        raise ValueError('Specify distinct protein and target/ligand chains.')
    if policy['targetChain'].strip() in tokens(policy['binderChains']):
        if policy['mode'] == 'protein' or not policy.get('ligandResidue', '').strip():
            raise ValueError('Shared protein/ligand chains require one explicit nonpolymer ligand residue; protein epitope chains must be distinct.')
    cutoff = float(policy['cutoff'])
    if not math.isfinite(cutoff) or not 0 < cutoff <= 100: raise ValueError('Distance must be >0 and ≤100 Å.')
    if policy['mode'] == 'protein' and not tokens(policy['residues']): raise ValueError('Select target residue IDs.')
    if policy['mode'] == 'protein' and (policy.get('requireGeometry') or policy.get('minimumBurial') or policy.get('maximumBurial')):
        raise ValueError('Ligand geometry/burial settings require ligand mode.')
    for key in ('minimumBurial', 'maximumBurial'):
        if policy.get(key) and (not math.isfinite(float(policy[key])) or not 0 <= float(policy[key]) <= 100):
            raise ValueError('Burial thresholds must be between0 and100 percent.')
    if policy.get('minimumBurial') and policy.get('maximumBurial') and float(policy['minimumBurial']) > float(policy['maximumBurial']):
        raise ValueError('Minimum burial exceeds maximum burial.')

def read(path):
    import gemmi
    st = gemmi.read_structure(str(path))
    if len(st) != 1: raise ValueError('Choose a structure containing exactly one coordinate model.')
    if len({c.name for c in st[0]}) != len(st[0]): raise ValueError('Duplicate chain IDs are ambiguous.')
    records = []
    for ci, chain in enumerate(st[0]):
        seen_residues = set()
        for ri, residue in enumerate(chain):
            if residue.name in ('HOH', 'WAT', 'DOD'): continue
            protein = gemmi.find_tabulated_residue(residue.name).is_amino_acid() and residue.entity_type != gemmi.EntityType.NonPolymer
            rid = str(residue.seqid.num) + residue.seqid.icode.strip()
            if rid in seen_residues: raise ValueError('Duplicate author residue IDs are ambiguous in this chain.')
            seen_residues.add(rid)
            seen_atoms = set()
            for atom in residue:
                if atom.element.is_hydrogen: continue
                if atom.name.strip() in seen_atoms: raise ValueError('Duplicate heavy-atom names are ambiguous in this residue.')
                seen_atoms.add(atom.name.strip())
                xyz = (atom.pos.x, atom.pos.y, atom.pos.z)
                if atom.has_altloc() or atom.occ <= 0 or atom.element.atomic_number <= 0 or not all(math.isfinite(v) for v in xyz):
                    raise ValueError('Spatial review requires finite, occupied heavy atoms without alternate locations.')
                records.append(dict(chain=chain.name, residue=rid, component=residue.name, name=atom.name.strip(),
                    xyz=xyz, protein=protein, ci=ci, ri=ri, element=atom.element.name))
    if not records: raise ValueError('No usable heavy atoms.')
    return st, records

def inventory(path):
    _, atoms = read(path)
    chains = {}
    for a in atoms:
        chain = chains.setdefault(a['chain'], dict(protein_residues=[], ligands={}))
        if a['protein']:
            if a['residue'] not in chain['protein_residues']: chain['protein_residues'].append(a['residue'])
        else:
            key = a['residue'] + ':' + a['component']
            chain['ligands'].setdefault(key, []).append(a['name'])
    return dict(numbering='Author chain/residue IDs from the exact assessed structure, including insertion codes', chains=chains)

_GEOMETRY_INDEX = {}

def geometry(path, checksum):
    """Verify a recorded verdict, without re-running or reinterpreting its policy."""
    sidecar = Path(str(path) + '.ligand_geometry.json')
    candidates = [sidecar] if sidecar.exists() else []
    for parent in list(Path(path).resolve().parents)[:12]:
        directory = parent / 'geometry_receipts'
        if directory.is_dir():
            if str(directory) not in _GEOMETRY_INDEX:
                indexed = {}
                for receipt in sorted(directory.glob('*.json')):
                    try:
                        saved = json.loads(receipt.read_text())
                        source = saved.get('input', {}).get('structure_sha256') or saved.get('result', {}).get('structure_sha256')
                        indexed.setdefault(source, []).append((receipt, saved))
                    except (ValueError, OSError):
                        continue
                _GEOMETRY_INDEX[str(directory)] = indexed
            candidates += _GEOMETRY_INDEX[str(directory)].get(checksum, []); break
    for entry in candidates:
        if isinstance(entry, tuple): receipt, saved = entry
        else: receipt = entry; saved = json.loads(receipt.read_text())
        result = saved.get('result', {})
        source = saved.get('input', {}).get('structure_sha256') or result.get('structure_sha256')
        if source != checksum: continue
        raw = saved.get('result_json') or json.dumps(result, sort_keys=True, allow_nan=False)
        if json.loads(raw) != result or hashlib.sha256(raw.encode()).hexdigest() != saved.get('result_sha256'):
            raise ValueError('Recorded ligand geometry receipt failed integrity validation.')
        if not isinstance(result.get('passed'), bool): raise ValueError('Recorded geometry has no boolean verdict.')
        return dict(passed=result['passed'], receipt=str(receipt), sha256=sha(receipt),
                    linker_exit=result.get('linker_exit', {}).get('label') if result.get('linker_exit') else None)
    return None

def ligand_sasa(st, atoms, binder_chains, ligand_key, cache):
    # Port the existing atom_geometry protocol unchanged: RDKit FreeSASA,
    # Shrake–Rupley, heavy-atom RDKit VdW radii,1.4Å probe. No new classifier.
    import gemmi
    from atom_geometry import measure
    normalized = gemmi.Structure(); model = gemmi.Model('1')
    binder, ligand = gemmi.Chain('A'), gemmi.Chain('B'); others = []
    for ci, chain in enumerate(st[0]):
        extra = gemmi.Chain('E' + str(ci))
        for ri, residue in enumerate(chain):
            if residue.name in ('HOH', 'WAT', 'DOD'): continue
            if (ci, ri) == ligand_key: ligand.add_residue(residue.clone())
            elif chain.name in binder_chains and gemmi.find_tabulated_residue(residue.name).is_amino_acid(): binder.add_residue(residue.clone())
            else: extra.add_residue(residue.clone())
        if len(extra): others.append(extra)
    model.add_chain(binder); model.add_chain(ligand)
    for chain in others: model.add_chain(chain)
    normalized.add_model(model)
    selected = [a for a in atoms if (a['ci'], a['ri']) == ligand_key]
    names = [a['name'] for a in selected]
    if len(set(names)) != len(names): raise ValueError('Selected ligand contains duplicate atom names.')
    manifest = dict(atoms=[dict(name=a['name'], el=a['element']) for a in selected])
    with tempfile.TemporaryDirectory(prefix='sasa-', dir=cache) as temporary:
        path = Path(temporary) / 'normalized.cif'; normalized.make_mmcif_document().write_file(str(path))
        measured = measure(path, dict(exposed_atoms=names, hotspot_atoms=[], exposure_min_fraction=0, hotspot_distance=6), manifest)
    exposed = measured['exposure']
    free = sum(v['isolated_ligand_sasa_a2'] for v in exposed.values())
    bound = sum(v['complex_sasa_a2'] for v in exposed.values())
    if free <= .1: raise ValueError('Isolated ligand accessibility is too small to define burial.')
    return dict(buried_percent=max(0, min(100, 100 * (1 - bound / free))), isolated_sasa_a2=free,
                complex_sasa_a2=bound, per_atom=exposed, protocol=measured['protocol'], probe_radius_a=1.4)

def assess(path, policy, cache):
    import numpy as np
    from scipy.spatial import cKDTree
    validate(policy)
    st, atoms = read(path)
    binders = set(tokens(policy['binderChains'])); target_chain = policy['targetChain'].strip()
    present = {a['chain'] for a in atoms if a['protein']}
    if not binders <= present: raise ValueError('A selected binder/protein chain is missing or is not protein.')
    protein = [a['xyz'] for a in atoms if a['chain'] in binders and a['protein']]
    tree = cKDTree(np.asarray(protein))
    target = [a for a in atoms if a['chain'] == target_chain]
    distances = {}; sasa = None
    if policy['mode'] == 'protein':
        requested = tokens(policy['residues'])
        if len(set(requested)) != len(requested): raise ValueError('Choose distinct residue IDs.')
        for rid in requested:
            selected = [a for a in target if a['protein'] and a['residue'] == rid]
            if not selected: raise ValueError('A requested target residue is absent. Inspect the exact pose and its author numbering.')
            distances[rid] = float(tree.query([a['xyz'] for a in selected])[0].min())
    else:
        rid = policy.get('ligandResidue', '').strip()
        selected = [a for a in target if (not rid or a['residue'] == rid)]
        if any(a['protein'] for a in selected): raise ValueError('Choose a nonpolymer ligand residue, not protein residues.')
        keys = {(a['ci'], a['ri']) for a in selected}
        if len(keys) != 1: raise ValueError('Select one exact ligand residue; the target chain is missing or contains multiple components.')
        names = tokens(policy.get('atoms', '')) or [a['name'] for a in selected]
        if len(set(names)) != len(names) or len({a['name'] for a in selected}) != len(selected): raise ValueError('Ligand atom names must be unambiguous.')
        byname = {a['name']: a for a in selected}
        if not set(names) <= set(byname): raise ValueError('A selected ligand atom is absent from this predicted chemical state. Inspect its exact atom names.')
        distances = {name: float(tree.query(byname[name]['xyz'])[0]) for name in names}
        sasa = ligand_sasa(st, atoms, binders, next(iter(keys)), cache)
    minimum, maximum = min(distances.values()), max(distances.values())
    passed = (maximum if policy['coverage'] == 'all' else minimum) <= float(policy['cutoff'])
    return dict(passed=passed, distances=distances, minimum_distance=minimum, maximum_distance=maximum, sasa=sasa)

def run(request):
    import gemmi, numpy, scipy
    from rdkit import rdBase
    policy = request['policy']; validate(policy)
    key = digest(policy)
    if request['policy_sha256'] != key: raise ValueError('Spatial policy digest mismatch.')
    cache = Path(request['cache']); cache.mkdir(parents=True, exist_ok=True)
    versions = dict(gemmi=gemmi.__version__, numpy=numpy.__version__, scipy=scipy.__version__, rdkit=rdBase.rdkitVersion,
                    helper_sha256=sha(__file__), sasa_helper_sha256=sha(HERE/'nise/atom_geometry.py'))
    for unit in request['units']:
        row = dict(id=unit['id'], source_item_id=unit['source_item_id'], source=unit['source'], source_stamp=unit['source_stamp'], policy_sha256=key)
        try:
            if not unit['source'] or not unit['source_stamp']: raise ValueError('No usable complex pose is available; binder-alone checks cannot supply target contacts.')
            source = Path(unit['source']); checksum = sha(source); row['source_sha256'] = checksum
            recorded = None; geometry_warning = None
            if policy['mode'] == 'ligand':
                try: recorded = geometry(source, checksum)
                except (ValueError, OSError) as error:
                    if policy.get('requireGeometry'): raise
                    geometry_warning = 'Recorded geometry unavailable: ' + str(error)
            spec = dict(structure_sha256=checksum, policy=policy, implementation=versions, geometry=recorded, geometry_warning=geometry_warning)
            receipt = cache / (digest(spec) + '.json')
            with receipt.with_suffix('.lock').open('a') as lock:
                fcntl.flock(lock, fcntl.LOCK_EX)
                if receipt.exists():
                    saved = json.loads(receipt.read_text())
                    if saved['input'] != spec or digest(saved['result']) != saved['result_sha256']: raise ValueError('Spatial review cache failed integrity validation.')
                    result = saved['result']
                else:
                    # Thresholds do not change the measured pose. Reuse physical
                    # measurements across cutoff/coverage/burial/geometry criteria.
                    selection = {k: policy.get(k) for k in ('mode','binderChains','targetChain','residues','ligandResidue','atoms')}
                    measurement_spec = dict(structure_sha256=checksum, selection=selection, implementation=versions)
                    directory = cache/'measurements'; directory.mkdir(exist_ok=True)
                    measurement = directory/(digest(measurement_spec)+'.json')
                    with measurement.with_suffix('.lock').open('a') as measure_lock:
                        fcntl.flock(measure_lock, fcntl.LOCK_EX)
                        if measurement.exists():
                            measured = json.loads(measurement.read_text())
                            if measured['input'] != measurement_spec or digest(measured['result']) != measured['result_sha256']:
                                raise ValueError('Spatial measurement cache failed integrity validation.')
                            result = measured['result']
                        else:
                            result = assess(source, policy, cache); result.pop('passed', None)
                            if sha(source) != checksum: raise ValueError('Structure changed during spatial review.')
                            measured = dict(input=measurement_spec,result=result,result_sha256=digest(result))
                            temp = measurement.with_suffix('.part');temp.write_text(json.dumps(measured,sort_keys=True,allow_nan=False));temp.replace(measurement)
                    result = dict(result)
                    result['passed'] = (result['maximum_distance'] if policy['coverage']=='all' else result['minimum_distance']) <= float(policy['cutoff'])
                    if policy.get('requireGeometry'): result['passed'] &= recorded is not None and recorded['passed']
                    if result['sasa']:
                        burial = result['sasa']['buried_percent']
                        if policy.get('minimumBurial'): result['passed'] &= burial >= float(policy['minimumBurial'])
                        if policy.get('maximumBurial'): result['passed'] &= burial <= float(policy['maximumBurial'])
                    result['recorded_geometry'] = recorded
                    result['geometry_warning'] = geometry_warning
                    if sha(source) != checksum: raise ValueError('Structure changed during spatial review.')
                    saved = dict(input=spec, result=result, result_sha256=digest(result))
                    temp = receipt.with_suffix('.part'); temp.write_text(json.dumps(saved, sort_keys=True, allow_nan=False)); temp.replace(receipt)
            row.update(result); row['receipt'] = str(receipt)
        except Exception as error:
            row.update(passed=False, error=str(error))
        print(json.dumps(row, allow_nan=False), flush=True)

if __name__ == '__main__':
    parser = argparse.ArgumentParser(); parser.add_argument('action', choices=['inspect', 'run']); parser.add_argument('path'); args = parser.parse_args()
    try:
        if args.action == 'inspect': print(json.dumps(inventory(args.path), allow_nan=False))
        else: run(json.loads(Path(args.path).read_text()))
    except Exception as error:
        print('Spatial review failed: ' + str(error), file=sys.stderr); sys.exit(1)
