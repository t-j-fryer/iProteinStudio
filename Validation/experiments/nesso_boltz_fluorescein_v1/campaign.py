#!/usr/bin/env python3
"""Matched resident ligand scoring, submitted through Studio's exclusive broker."""
import argparse
import csv
from dataclasses import asdict
import hashlib
import json
import math
import os
from pathlib import Path
import platform
import shutil
import subprocess
import sys
import time
import uuid

STUDIO = Path(__file__).resolve().parents[3]
PIPELINE = STUDIO / 'Sources/iProteinStudio/Resources/pipeline'


def read(path):
    return json.loads(Path(path).read_text())


def digest(path):
    h = hashlib.sha256()
    with Path(path).open('rb') as stream:
        for block in iter(lambda: stream.read(8 << 20), b''):
            h.update(block)
    return h.hexdigest()


def atomic(path, value):
    path = Path(path); path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + '.part')
    temporary.write_text(json.dumps(value, indent=2, sort_keys=True, allow_nan=False) + '\n')
    temporary.replace(path)


def select(rows, count):
    """Freeze selection without reference to new NESSO or Boltz predictions."""
    unique = {}
    for r in rows:
        seq = r['sequence']
        if int(r['cycle']) < 1 or not seq or set(seq) - set('ACDEFGHIKLMNPQRSTVWY'):
            continue
        if any(not r[k] for k in ('pbind', 'ligand_plddt', 'score')):
            continue
        p, l, s = [float(r[k]) for k in ('pbind', 'ligand_plddt', 'score')]
        if not all(math.isfinite(v) for v in (p, l, s)) or not 0 <= p <= 1 or not 0 <= l <= 100:
            continue
        if abs(p + l/100 - s) > .002:
            raise ValueError('Historical score disagrees with P(bind)+pLDDT/100')
        unique.setdefault(seq, r)
    ordered = sorted(unique.values(), key=lambda r: (float(r['score']), r['name']))
    if len(ordered) < count or count < 2:
        raise ValueError('Insufficient eligible distinct sequences')
    return [dict(ordered[round(i*(len(ordered)-1)/(count-1))], selection_rank=i+1,
                 eligible_rank=round(i*(len(ordered)-1)/(count-1))+1) for i in range(count)], len(ordered)


def prepare(output, source):
    import yaml
    sys.path.insert(0, str(PIPELINE / 'scripts/nise'))
    from runtime import Backend
    from ligand_atoms import resolve
    if (output / 'manifest.json').exists():
        raise ValueError('Selection already frozen; use plan to resume')
    output.mkdir(parents=True, exist_ok=True)
    cfg = read(Path(__file__).with_name('protocol.json'))
    rows, eligible = select(list(csv.DictReader((source / 'trajectory.csv').open())), cfg['selection_count'])
    by_name = {}
    for path in source.rglob('*_model_0.pdb'):
        by_name.setdefault(path.name.removesuffix('_model_0.pdb'), []).append(path)
    snapshots = output / 'source'; snapshots.mkdir(exist_ok=True)
    shutil.copy2(source / 'trajectory.csv', snapshots / 'trajectory.csv')
    shutil.copy2(source / 'config.json', snapshots / 'config.json')
    smiles = None
    for r in rows:
        paths = by_name.get(r['name'], [])
        # "best" can contain a copy; fold directory owns the original prediction.
        paths = [p for p in paths if 'fold' in p.relative_to(source).parts]
        if len(paths) != 1:
            raise ValueError(f"Ambiguous/missing historical structure: {r['name']} ({len(paths)})")
        pdb = paths[0]
        Backend.audit_structure(pdb, r['sequence'], True)
        yamls = list(source.glob('**/yaml/' + r['name'] + '.yaml'))
        if len(yamls) != 1:
            raise ValueError('Ambiguous original YAML: '+r['name'])
        inp = yaml.safe_load(yamls[0].read_text())
        ligand = next(s['ligand']['smiles'] for s in inp['sequences'] if 'ligand' in s)
        protein = next(s['protein'] for s in inp['sequences'] if 'protein' in s)
        if protein['sequence'] != r['sequence'] or protein.get('msa') != 'empty':
            raise ValueError('Historical sequence/MSA mismatch')
        if smiles is not None and ligand != smiles:
            raise ValueError('Mixed ligand chemical states')
        smiles = ligand
        destination = snapshots / r['name']; destination.mkdir(exist_ok=True)
        artifacts = [pdb, yamls[0], *pdb.parent.glob('confidence_*_model_0.json'), *pdb.parent.glob('affinity_*.json')]
        if len(artifacts) != 4:
            raise ValueError('Missing historical confidence/affinity')
        for path in artifacts:
            shutil.copy2(path, destination / path.name)
        r.update(source_pdb=str(pdb), source_pdb_sha256=digest(pdb),
                 original_constraints=inp.get('constraints', []),
                 historical_files={str((destination/p.name).relative_to(output)):digest(p) for p in artifacts})
    ligand = resolve(smiles)
    atomic(output / 'selection.json', rows)
    atomic(output / 'ligand.json', ligand)
    shutil.copy2(Path(__file__).with_name('protocol.json'), output / 'protocol.json')
    manifest = dict(schema=1, protocol=cfg, source=str(source), source_csv_sha256=digest(source/'trajectory.csv'),
                    eligible_distinct_sequences=eligible, selected=len(rows),
                    sequence_lengths=[len(r['sequence']) for r in rows], original_origins=sorted({r['origin'] for r in rows}),
                    score_range=[rows[0]['score'],rows[-1]['score']],
                    selection_sha256=digest(output/'selection.json'), ligand_sha256=digest(output/'ligand.json'),
                    machine=platform.platform(), hardware=subprocess.check_output(['sysctl','-n','machdep.cpu.brand_string'],text=True).strip(),
                    memory_bytes=int(subprocess.check_output(['sysctl','-n','hw.memsize'],text=True)),
                    commit=subprocess.check_output(['git','rev-parse','HEAD'],cwd=STUDIO,text=True).strip(),
                    working_tree='Dirty; exact runner, scripts, source inputs and dependencies frozen in each plan')
    atomic(output/'manifest.json',manifest)
    print(json.dumps(manifest,indent=2))


def plan(output, phase):
    sys.path.insert(0,str(PIPELINE/'mcp'))
    sys.path.insert(0,str(PIPELINE/'scripts/nise'))
    from iprotein_mcp.common import runtime_root
    from iprotein_mcp.plans import _persist, _script_provenance
    from nesso_contract import validate_installation, installation_files
    root=runtime_root()
    validate_installation(root)
    manifest=read(output/'manifest.json')
    if digest(output/'selection.json') != manifest['selection_sha256'] or digest(output/'ligand.json') != manifest['ligand_sha256']:
        raise ValueError('Frozen inputs changed')
    if phase=='full' and read(output/'pilot/audit.json')['status']!='passed':
        raise ValueError('Three-case end-to-end pilot must pass before 50 cases')
    stage=output/phase; stage.mkdir(exist_ok=True)
    if (stage/'plan.json').exists():
        print(json.dumps(read(stage/'plan.json'))); return
    snapshot=stage/'snapshot'
    shutil.copytree(PIPELINE/'scripts',snapshot/'scripts',ignore=shutil.ignore_patterns('__pycache__','*.pyc'))
    shutil.copy2(__file__,snapshot/'campaign.py')
    for name in ('analyse.py','test_campaign.py','test_analysis.py','README.md'):
        shutil.copy2(Path(__file__).with_name(name),snapshot/name)
    version_command = "import importlib.metadata as m,json,sys; print(json.dumps(dict(python=sys.version,packages={d.metadata['Name']:d.version for d in m.distributions()})))"
    from nesso_contract import installation
    environments = {name:json.loads(subprocess.check_output([str(python),'-c',version_command],text=True)) for name,python in [('boltz',root/'venvs/NanoHunter_boltz/bin/python'),('nesso',installation(root)/'venv/bin/python')]}
    atomic(snapshot/'environments.json',environments)
    atomic(stage/'run_config.json',dict(root=str(root),output=str(output),phase=phase))
    required=[root/'venvs/NanoHunter_boltz/bin/python',root/'models/boltz2/boltz2_conf.ckpt',root/'models/boltz2/boltz2_aff.ckpt']
    required += list((root/'venvs/NanoHunter_boltz/lib').glob('python*/site-packages/boltz/**/*.py'))
    required += installation_files(root)
    # Fingerprint full chemical dictionary; don't redistribute it or weights.
    required += [p for p in (root/'models/boltz2/mols').iterdir() if p.is_file()]
    required += [p for p in snapshot.rglob('*') if p.is_file()]
    required += [output/n for n in ('selection.json','ligand.json','manifest.json','protocol.json')]+[stage/'run_config.json']
    required += [p for p in (output/'source').rglob('*') if p.is_file()]
    if phase=='full': required += [output/'pilot/audit.json']
    command=['/usr/bin/caffeinate','-dimsu',str(root/'venvs/NanoHunter_boltz/bin/python'),str(snapshot/'campaign.py'),'run','--output',str(output),'--phase',phase]
    frozen=_persist('desktop_nesso_boltz_validation','nesso-boltz-validation',
        dict(output=str(stage),workflow='nesso-boltz-validation',steps=[dict(command=command,cwd=str(stage),stage='paired-'+phase)],environment_overrides={}),
        command,'apple_gpu_exclusive',_script_provenance(sorted(set(required))))
    atomic(stage/'plan.json',frozen)
    print(json.dumps(dict(id=frozen['id'],sha256=frozen['sha256'])))


def run(output, phase):
    stage=output/phase; cfg=read(stage/'run_config.json'); root=Path(cfg['root'])
    scripts=stage/'snapshot/scripts'; sys.path.insert(0,str(scripts/'nise'))
    from runtime import ResidentClient, Backend, Journal
    from nesso_screen import NessoClient
    from ligand_atoms import audit_atoms
    from nesso_contract import placement_score
    import nise_lib as science
    protocol=read(output/'protocol.json'); candidates=read(output/'selection.json'); ligand=read(output/'ligand.json')
    if phase=='pilot': candidates=[candidates[i] for i in protocol['pilot']['selection_indices']]
    journal=Journal(stage)
    all_results=[]
    for engine in protocol[phase]['engine_order']:
        worker=None
        try:
            for i,r in enumerate(candidates):
                unit=stage/engine/r['name']; receipt=unit/'completed.json'
                spec=dict(engine=engine,candidate=r['name'],sequence=r['sequence'],smiles=ligand['smiles_used'],seed=protocol['seed'],protocol_sha256=digest(output/'protocol.json'))
                cached=journal.load(receipt,spec)
                if cached is not None:
                    all_results.append(cached); continue
                if worker is None:
                    started=time.monotonic()
                    worker=(NessoClient(root,stage,scripts,protocol['seed']) if engine=='nesso' else ResidentClient(root,stage,scripts,protocol['seed'],True,True))
                    startup=time.monotonic()-started
                    # Every new resident gets an excluded warmup, including lazy affinity load.
                    warmup=stage/engine/'warmups'/worker.queue.name
                    warm=execute(worker,engine,r,ligand,warmup,science,Backend,audit_atoms,placement_score)
                    atomic(warmup/'warmup.json',dict(result=warm,process_startup_wall_seconds=startup,ready=worker.ready))
                attempt=unit/('attempt-'+uuid.uuid4().hex); attempt.mkdir(parents=True)
                result=execute(worker,engine,r,ligand,attempt,science,Backend,audit_atoms,placement_score)
                files=[p for p in attempt.rglob('*') if p.is_file()]
                journal.save(receipt,spec,result,files)
                all_results.append(result)
                print(f"{phase} {engine} {i+1}/{len(candidates)} {r['name']}: {result['wall_seconds']:.3f}s",flush=True)
                atomic(stage/'progress.json',dict(phase=phase,engine=engine,completed=i+1,total=len(candidates),last=result))
        finally:
            if worker is not None: worker.close()
    if len(all_results)!=2*len(candidates): raise ValueError('Incomplete paired outputs')
    sessions={engine:sorted({r['session'] for r in all_results if r['engine']==engine}) for engine in ('nesso','boltz')}
    # No forbidden generic MPS fallback; the compatibility layer documents explicit linalg SVD.
    fallback=[]
    for log in (stage/'sessions').glob('*/worker.log'):
        for line in log.read_text().splitlines():
            if 'fall back' in line.lower() or 'fallback' in line.lower():
                fallback.append(dict(log=str(log.relative_to(stage)),message=line))
                if ('fall back to run on the cpu' in line.lower() or 'falling back to cpu' in line.lower()) and 'linalg_svd' not in line:
                    raise ValueError('Forbidden CPU fallback in '+str(log))
    atomic(stage/'audit.json',dict(status='passed',paired_candidates=len(candidates),receipts=len(all_results),
        sessions=sessions,fallback_messages=fallback,measured_model_load_count=2,
        input_hashes=dict(selection=digest(output/'selection.json'),protocol=digest(output/'protocol.json')),
        completed_files={str(p.relative_to(stage)):digest(p) for p in stage.glob('*/*/completed.json')}))
    print(f'{phase} complete: {len(candidates)} paired candidates',flush=True)


def execute(worker,engine,r,ligand,directory,science,Backend,audit_atoms,placement_score):
    directory.mkdir(parents=True,exist_ok=True)
    if engine=='boltz':
        inputs=directory/'yaml'; inputs.mkdir()
        science.write_boltz_yaml(inputs/(r['name']+'.yaml'),r['sequence'],ligand['smiles_used'],affinity=True,pocket=None)
    start=time.monotonic()
    native=(worker.score(r['sequence'],ligand['smiles_used'],directory) if engine=='nesso' else worker.predict(inputs,directory/'fold',True))
    elapsed=time.monotonic()-start
    result=dict(engine=engine,candidate=r['name'],sequence_length=len(r['sequence']),wall_seconds=elapsed,
                session=native['session'],native=native)
    if engine=='nesso':
        result.update(scores=native['scores'],combined=placement_score(native['scores'])['score'])
        if not (directory/'ligand_identity.json').is_file(): raise ValueError('Missing NESSO identity audit')
    else:
        pred=science.parse_prediction(directory/'fold',r['name'])
        if pred is None or pred.pbind is None: raise ValueError('Missing Boltz prediction/affinity')
        if len(list((directory/'fold').glob('**/predictions/*/*_model_*.pdb'))) != 1: raise ValueError('Unexpected structure count')
        Backend.audit_structure(pred.pdb,r['sequence'],True); audit_atoms(pred.pdb,ligand)
        if not (0<=pred.pbind<=1 and math.isfinite(pred.ligand_plddt) and 0<=pred.ligand_plddt<=100): raise ValueError('Invalid Boltz score')
        affinity=read(Path(pred.pdb).with_name('affinity_'+r['name']+'.json'))
        result.update(scores=asdict(pred),affinity=affinity,combined=pred.pbind+pred.ligand_plddt/100)
    return result


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('action',choices=['prepare','plan','run'])
    parser.add_argument('--output',type=Path,required=True)
    parser.add_argument('--source',type=Path)
    parser.add_argument('--phase',choices=['pilot','full'],default='pilot')
    args=parser.parse_args(); output=args.output.resolve()
    if args.action=='prepare': prepare(output,args.source.resolve())
    elif args.action=='plan': plan(output,args.phase)
    else: run(output,args.phase)
