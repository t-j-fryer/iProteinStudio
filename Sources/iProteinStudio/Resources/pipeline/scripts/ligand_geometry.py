#!/usr/bin/env python3
"""Optional shared ligand geometry hit filter and exact sampled-cone display.

CPU-only. Structures and scientific scores remain immutable; receipts carry a
separate geometry verdict, the policy, atom identity and implementation hashes.
"""
import argparse
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys

SCRIPTS = Path(__file__).resolve().parent
sys.path.insert(0, str(SCRIPTS / 'nise'))
from ligand_geometry_policy import normalize, atom_settings


def digest(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def atomic(path, value):
    path = Path(path); path.parent.mkdir(parents=True, exist_ok=True)
    temp = path.with_suffix(path.suffix + '.part')
    temp.write_text(json.dumps(value, indent=2, sort_keys=True, allow_nan=False) + '\n'); temp.replace(path)


def cone_overlay(path, manifest, result):
    """Replay the classifier's nominal samples without changing its verdict."""
    if result.get('linker_exit') is None:
        return None
    import numpy as np
    from rdkit import Chem
    from biotin_exit import case_from_structure
    from linker_geometry import extensions, clashes, ray_clearance, RAD
    saved = result['linker_exit']; case = case_from_structure(path, manifest)
    stubs, _ = extensions(*np.asarray(case['attachment_frame']), nphi=saved['protocol']['nphi'], angles=(120,))
    core, env = np.asarray(case['core']), np.asarray(case['environment'])
    cz, ez = np.asarray(case['core_z']), np.asarray(case['environment_z'])
    p, n, c = clashes(stubs, env, ez, core, cz, case['bonded_exclusions'])
    fit = (p <= .8) & (n <= .5) & (c <= .5)
    xyz = np.vstack((env, core))
    radii = np.asarray([RAD.get(int(z), Chem.GetPeriodicTable().GetRvdw(int(z))) for z in np.r_[ez, cz]])
    clearances = [ray_clearance(s[2], xyz, radii, saved['protocol']['nrays'])[0] if ok else None for s, ok in zip(stubs, fit)]
    labels = ['clash' if not ok else 'wide' if gap >= 1.4 else 'limited' for ok, gap in zip(fit, clearances)]
    if int(fit.sum()) != saved['nominal_standard_fit'] or labels.count('wide') != saved['nominal_wide_exit']:
        raise ValueError('Cone display does not reproduce the recorded geometry samples.')
    return dict(stem=[case['attachment_frame'][0], *stubs[0, :2].tolist()],
                stubs=stubs.tolist(), labels=labels, counts={k: labels.count(k) for k in ('wide', 'limited', 'clash')},
                note='Discrete idealized trans-amide samples at physical scale. Colours describe sampled standard-fit/direct exits; they are not a binding probability or a continuous accessible region.')


def predicted_manifest(smiles, predictor):
    if predictor in ('boltz','boltz2','boltz_potentials'):
        from ligand_atoms import resolve
        return resolve(smiles)
    if predictor == 'native':
        from rdkit import Chem
        mol=Chem.MolFromSmiles(smiles)
        if mol is None: raise ValueError('Invalid ligand SMILES.')
        return dict(smiles_used=smiles,atoms=[dict(index=i,name=a.GetSymbol()+str(i+1),el=a.GetSymbol()) for i,a in enumerate(mol.GetAtoms())])
    if predictor == 'boltz-structure' or predictor.startswith('esmfold2-'):
        from rfd4.ligand_score import esm_ligand_manifest
        return esm_ligand_manifest(smiles)
    if predictor=='intellifold-full': predictor='intellifold'
    from rdkit import Chem
    from rfd4.mixed_target import native_names
    mol=Chem.MolFromSmiles(smiles)
    names=native_names(smiles,predictor)
    return dict(smiles_used=smiles,atoms=[dict(index=i,name=names[i],el=a.GetSymbol()) for i,a in enumerate(mol.GetAtoms())])


def check(path, smiles, policy, *, predictor='boltz', manifest=None, ligand_chain='B', measured=None):
    """Evaluate one complete holo structure, with a checked exact atom map."""
    import gemmi
    import numpy, scipy
    from rdkit import rdBase
    from atom_geometry import measure
    from biotin_exit import roles, source_signature
    source = Path(path).resolve(); cfg = normalize(policy)
    manifest = manifest or predicted_manifest(smiles, predictor)
    settings = atom_settings(cfg, smiles, manifest)
    if cfg['mode'] == 'biotin-carboxamide-v1': roles(manifest)
    implementation = dict(classifier_sha256=source_signature(), adapter_sha256=digest(__file__),
                          policy_sha256=digest(SCRIPTS/'ligand_geometry_policy.py'),
                          rdkit=rdBase.rdkitVersion, numpy=numpy.__version__, scipy=scipy.__version__, gemmi=gemmi.__version__)
    specification = dict(structure_sha256=digest(source), policy=cfg, smiles=smiles,
                         manifest=manifest, ligand_chain=ligand_chain, predictor=predictor, implementation=implementation)
    sidecar = Path(str(source) + '.ligand_geometry.json')
    if sidecar.exists():
        saved = json.loads(sidecar.read_text())
        if saved['input'] != specification: raise ValueError('Saved ligand geometry inputs changed; use a new run.')
        checksum = hashlib.sha256(json.dumps(saved['result'], sort_keys=True, allow_nan=False).encode()).hexdigest()
        if checksum != saved['result_sha256']: raise ValueError('Saved ligand geometry result changed.')
        return saved['result']
    # The frozen Figure 4 adapter expects binder A and ligand B. Preserve every
    # other atom as an obstacle; never infer connectivity or a ligand identity.
    st = gemmi.read_structure(str(source))
    if len(st) != 1: raise ValueError('Geometry requires exactly one coordinate model.')
    import math
    for chain in st[0]:
        for residue in chain:
            if residue.name in ('HOH','WAT'):continue
            for atom in residue:
                if atom.element.is_hydrogen:continue
                if atom.has_altloc() or atom.occ<=0 or atom.element.atomic_number<=0 or not all(math.isfinite(v) for v in (atom.pos.x,atom.pos.y,atom.pos.z)):
                    raise ValueError('Geometry requires finite, occupied, unambiguous heavy atoms.')
    chains = [c.name for c in st[0]]
    if len(set(chains)) != len(chains) or 'A' not in chains or ligand_chain not in chains or ligand_chain == 'A':
        raise ValueError('Geometry requires one explicit ligand chain and binder A.')
    target = source
    normalized = None
    if ligand_chain != 'B':
        normalized = source.parent / (source.name + '.geometry_input.cif')
        # Swap names through a temporary identity, retaining the source pose.
        for chain in st[0]:
            if chain.name == 'B': chain.name = '__old_B__'
        st[0][ligand_chain].name = 'B'
        for chain in st[0]:
            if chain.name == '__old_B__': chain.name = ligand_chain
        st.make_mmcif_document().write_file(str(normalized)); target = normalized
    try:
        result = dict(measured) if measured is not None else measure(target, settings, manifest)
        result['cone'] = cone_overlay(target, manifest, result)
    finally:
        if normalized is not None: normalized.unlink(missing_ok=True)
    if digest(source) != specification['structure_sha256']: raise ValueError('Structure changed during geometry check.')
    result.update(policy=cfg, settings=settings, ligand_chain=ligand_chain, structure=str(source),
                  structure_sha256=specification['structure_sha256'], scope='Predicted holo geometry; computational hit criterion')
    checksum = hashlib.sha256(json.dumps(result, sort_keys=True, allow_nan=False).encode()).hexdigest()
    atomic(sidecar, dict(schema=1, input=specification, result=result, result_json=json.dumps(result,sort_keys=True,allow_nan=False), result_sha256=checksum))
    return result


def in_runtime(root, path, smiles, policy, *, predictor='boltz', manifest=None, ligand_chain='B', runtime='boltz'):
    """Keep RDKit/Gemmi out of predictor environments which do not ship them."""
    request = dict(path=str(path), smiles=smiles, policy=policy, predictor=predictor, manifest=manifest, ligand_chain=ligand_chain)
    python = Path(root) / ('venvs/NanoHunter_' + runtime + '/bin/python')
    result = subprocess.run([str(python), '-B', str(SCRIPTS/'ligand_geometry.py'), 'check'],
        input=json.dumps(request), text=True, capture_output=True,
        env=dict(os.environ, PYTHONDONTWRITEBYTECODE='1', OMP_NUM_THREADS='1', OPENBLAS_NUM_THREADS='1', VECLIB_MAXIMUM_THREADS='1'))
    if result.returncode: raise ValueError('Ligand geometry check failed: ' + result.stderr[-2500:])
    return json.loads(result.stdout)


def tables(root, policy, smiles, files, predictor):
    import csv
    results = []
    for file in files:
        for row in csv.DictReader(Path(file).open()):
            # Table entries alone identify completed holo files; no recursive
            # coordinate scan that could accidentally qualify an apo sibling.
            path = row.get('structure_path') or row.get('pdb') or row.get('structure') or row.get('predictor_structure')
            if not path: raise ValueError('Geometry table omitted its holo structure path.')
            if row.get('prediction_context') in ('binder_alone','apo'): continue
            source = Path(path)
            if not source.is_absolute(): source = Path(root) / source
            engine=row.get('predictor') or predictor
            if engine=='boltz' and predictor=='boltz-structure': engine=predictor
            results.append(check(source, smiles, policy, predictor=engine))
    return results



def recorded_preview(path):
    """Render an existing immutable NISE receipt; no reclassification or writes."""
    source=Path(path).resolve();checksum=digest(source)
    from biotin_exit import source_signature
    for parent in list(source.parents)[:12]:
        directory=parent/'geometry_receipts'
        if not directory.is_dir(): continue
        for receipt in directory.glob('*.json'):
            saved=json.loads(receipt.read_text());spec=saved.get('input',{})
            if spec.get('structure_sha256')!=checksum:continue
            result=saved['result']
            if hashlib.sha256(json.dumps(result,sort_keys=True,allow_nan=False).encode()).hexdigest()!=saved['result_sha256']:
                raise ValueError('Recorded geometry result changed.')
            if spec.get('implementation',{}).get('code_sha256')!=source_signature():
                raise ValueError('This receipt requires its retained classifier version to render its samples.')
            manifest=spec['manifest'];cone=cone_overlay(source,manifest,result)
            if cone is None:raise ValueError('This result used SASA only; no exit cone was calculated.')
            return dict(result,cone=cone,structure_sha256=checksum,ligand_chain='B',receipt=str(receipt))
        raise ValueError('No completed linker-exit receipt matches this structure.')
    raise ValueError('No recorded linker-exit calculation was found for this structure.')

if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('action', choices=('check', 'tables', 'validate', 'recorded'))
    parser.add_argument('--structure')
    parser.add_argument('--policy')
    parser.add_argument('--smiles')
    parser.add_argument('--template')
    parser.add_argument('--root')
    parser.add_argument('--predictor', default='boltz')
    parser.add_argument('--tables', nargs='+')
    args = parser.parse_args()
    if args.action == 'recorded':
        print(json.dumps(recorded_preview(args.structure),allow_nan=False))
    elif args.action == 'check':
        request=json.load(sys.stdin)
        if 'measured' in request: raise ValueError('Precomputed measurements are internal to the recorded NISE stage.')
        print(json.dumps(check(**request), allow_nan=False))
    else:
        policy = normalize(json.loads(args.policy))
        smiles = args.smiles
        if args.template:
            import yaml
            ligands = [e['ligand'] for e in yaml.safe_load(Path(args.template).read_text())['sequences'] if 'ligand' in e]
            if len(ligands) != 1 or ligands[0].get('id') != 'B' or not ligands[0].get('smiles'):
                raise ValueError('Geometry filtering requires one explicit SMILES ligand B in the template.')
            smiles = ligands[0]['smiles']
            if args.predictor in ('boltz','boltz2','boltz_potentials') and not any('affinity' in prop for prop in yaml.safe_load(Path(args.template).read_text()).get('properties',[])):
                args.predictor='boltz-structure'
        if args.action == 'validate':
            manifest = predicted_manifest(smiles, args.predictor)
            atom_settings(policy, smiles, manifest)
            if policy['mode'] == 'biotin-carboxamide-v1':
                from biotin_exit import roles
                roles(manifest)
            print(json.dumps(dict(valid=True)))
        else:
            print(json.dumps(dict(checked=len(tables(args.root, policy, smiles, args.tables, args.predictor)))))
