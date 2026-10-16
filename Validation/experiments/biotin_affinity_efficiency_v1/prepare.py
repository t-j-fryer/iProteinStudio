"""Freeze saved biotin inputs without GPU work; submit only via Studio bridge."""
import argparse
from datetime import datetime, timezone
import json
import math
import os
from pathlib import Path
import random
import shutil
import subprocess
import sys
from common import sha, save

HERE = Path(__file__).resolve().parent
REPO = HERE.parents[2]


def select(rows, seed):
    rng = random.Random(seed)
    selected, seen = [], set()
    for phase in ('phase0', 'optimization'):
        eligible = sorted([r for r in rows if r['stage'] == phase],
                          key=lambda r: (r['pbind'], r['unit']))
        for tier in range(3):
            group = eligible[len(eligible)*tier//3:len(eligible)*(tier+1)//3]
            rng.shuffle(group)
            chosen = []
            for row in group:
                if row['sequence'] in seen:
                    continue
                seen.add(row['sequence']); chosen.append(dict(row, score_tertile=tier))
                if len(chosen) == 4:
                    break
            if len(chosen) != 4:
                raise RuntimeError('Insufficient distinct sequences in score/stage stratum')
            selected.extend(chosen)
    return selected


def freeze():
    root = Path(os.environ.get('NANOHUNTER_ROOT', Path.home()/'.iproteinstudio')).resolve()
    out = REPO/'Validation/output/biotin_affinity_efficiency_v1'/datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ')
    frozen = out/'frozen'; frozen.mkdir(parents=True)
    for p in HERE.glob('*.py'):
        shutil.copy2(p, frozen/p.name)
    shutil.copy2(REPO/'Validation/experiments/lasermpnn_residency_v1/benchmark.py', frozen/'laser_cpu.py')
    cases, populations = [], {}
    for generator, run in [('boltz', 'nise-3ea5fa63a1effece'), ('rfd3', 'nise-16b14dfae15e62d5')]:
        source = root/'projects/test2/nise_runs'/run
        rows = []
        receipts = list(source.glob('phase0/cycle*/fold/*/affinity_completed.json'))
        receipts += list(source.glob('cycle*/fold/*/affinity_completed.json'))
        for receipt in receipts:
            obj = json.loads(receipt.read_text())
            pred = obj['result']['prediction']; unit = receipt.parent
            structure = json.loads((unit/'completed.json').read_text())
            seq = structure['input']['sequence']
            if pred['pbind'] is None or not math.isfinite(pred['pbind']):
                continue
            if set(seq) - set('ACDEFGHIKLMNPQRSTVWY'):
                continue
            rows.append(dict(unit=str(unit), pbind=pred['pbind'], sequence=seq,
                             ligand_plddt=pred['ligand_plddt'],
                             stage='phase0' if 'phase0' in unit.parts else 'optimization'))
        populations[generator] = dict(count=len(rows), pbind_range=[min(r['pbind'] for r in rows), max(r['pbind'] for r in rows)])
        for i, row in enumerate(select(rows, 1016)):
            unit = Path(row['unit']); name = unit.name
            frozen_case = frozen/'cases'/f'{generator}_{i:02d}'
            frozen_case.mkdir(parents=True)
            receipt = json.loads((unit/'completed.json').read_text())
            aff = json.loads((unit/'affinity_completed.json').read_text())
            if aff['input']['structure_receipt_sha256'] != sha(unit/'completed.json'):
                raise RuntimeError('Affinity was not scored from this saved structure receipt')
            # Verify original atomic outputs before copying. Preserve every raw input.
            for rel, digest in {**receipt['files'], **aff['files']}.items():
                if sha(source/rel) != digest:
                    raise RuntimeError('Original result has changed: '+rel)
            old = unit/'out/boltz_results_yaml'
            shutil.copytree(old/'processed', frozen_case/'processed')
            shutil.copytree(old/'predictions'/name, frozen_case/'prediction')
            for p in (frozen_case/'prediction').glob('affinity*.json'):
                p.rename(p.with_name('historical_'+p.name))
            shutil.copy2(unit/'yaml'/(name+'.yaml'), frozen_case/(name+'.yaml'))
            save(frozen_case/'structure_receipt.json', receipt)
            save(frozen_case/'affinity_receipt.json', aff)
            for filename in ('config.json', 'ligand_atom_map.json'):
                shutil.copy2(source/filename, frozen_case/filename)
            request=json.loads((source/'nise_config.json').read_text())['request']
            geometry={k:request[k] for k in ('exposure_mode','hotspot_atoms','exposed_atoms',
                                             'hotspot_distance','exposure_min_fraction')}
            if geometry['exposure_mode']!='biotin-carboxamide-v1' or not geometry['hotspot_atoms']:
                raise RuntimeError('Expected recorded biotin geometry checks')
            save(frozen_case/'geometry_settings.json',geometry)
            cases.append(dict(row, generator=generator, name=name, key=f'{generator}_{i:02d}',
                              directory=str(frozen_case), seed=101600+len(cases),
                              pdb=str(next((frozen_case/'prediction').glob('*_model_0.pdb')))))
    laser_inputs = []
    for generator, run in [('boltz','nise-3ea5fa63a1effece'),('rfd3','nise-16b14dfae15e62d5')]:
        paths = sorted((root/'projects/test2/nise_runs'/run/'phase0/cycle01/design').glob('*/prepared.pdb'))[:2]
        if len(paths) != 2:
            raise RuntimeError('Missing prepared LASErMPNN overlap input')
        for i, path in enumerate(paths):
            target=frozen/f'{generator}_laser_{i}.pdb'; shutil.copy2(path,target); laser_inputs.append(str(target))
    cfg = dict(schema=1, output=str(out), root=str(root), cases=cases, populations=populations,
               scripts=str(root/'scripts'), python=str(root/'venvs/NanoHunter_boltz/bin/python'),
               laser_python=str(root/'venvs/NanoHunter_lasermpnn/bin/python'),
               laser_inputs=laser_inputs, source_parent=str(root/'src'),
               weights=str(root/'src/LASErMPNN/model_weights/laser_weights_0p1A_nothing_heldout.pt'),
               arms=[dict(name='reference', steps=200, samples=5), dict(name='light', steps=50, samples=1)],
               repeats=2, batch_size=8, msa_policy='saved empty alignments; no network MSA',
               scheduler='one resident Boltz session, serial paired arms; bounded CPU processes for geometry and overlap')
    cfg['frozen_inputs_sha256'] = {str(p):sha(p) for p in frozen.rglob('*') if p.is_file()}
    save(frozen/'config.json',cfg)
    save(out/'manifest.json',dict(schema=1,config=str(frozen/'config.json'),config_sha256=sha(frozen/'config.json'),
                                  expected_affinity_evaluations=248,expected_distinct_designs=48))
    host={}
    for k,cmd in {
        'chip':['/usr/sbin/sysctl','-n','machdep.cpu.brand_string'],
        'memory':['/usr/sbin/sysctl','-n','hw.memsize'],
        'os':['/usr/bin/sw_vers'], 'commit':['git','-C',str(REPO),'rev-parse','HEAD']}.items():
        proc=subprocess.run(cmd,text=True,capture_output=True)
        host[k]=proc.stdout.strip() if proc.returncode==0 else {'unavailable':proc.stderr.strip()}
    save(out/'host.json',host)
    print(json.dumps(dict(output=str(out),cases=len(cases),populations=populations)),flush=True)
    return out


def submit(out):
    frozen=out/'frozen';cfg=json.loads((frozen/'config.json').read_text());root=Path(cfg['root'])
    sys.path.insert(0,str(root/'mcp'))
    from iprotein_mcp.plans import _persist, _script_provenance
    from server import MCPServer
    server=MCPServer('run')
    save(out/'workflow_guide.json',server.tool_call('workflow_guide',{'workflow':'prediction'}))
    command=['/usr/bin/env','PYTHONDONTWRITEBYTECODE=1','KMP_USE_SHM=0','OMP_NUM_THREADS=1',
             'MKL_NUM_THREADS=1','OPENBLAS_NUM_THREADS=1','VECLIB_MAXIMUM_THREADS=1',
             '/usr/bin/caffeinate','-dimsu',cfg['python'],'-B',str(frozen/cfg.get('entrypoint','run.py')),str(frozen/'config.json')]
    files=list(frozen.rglob('*.py'))+[frozen/'config.json', Path(cfg['weights'])]
    files += [Path(p) for p in cfg['frozen_inputs_sha256']]
    files += list((root/'scripts').rglob('*.py'))+list((root/'src/LASErMPNN').rglob('*.py'))
    boltz=Path(cfg['python']).parent.parent/'lib/python3.11/site-packages/boltz'
    files += list(boltz.rglob('*.py'))
    files += [root/'models/boltz2'/n for n in ('boltz2_conf.ckpt','boltz2_aff.ckpt')]
    files += [Path(cfg['python']).resolve(),Path(cfg['laser_python']).resolve()]
    normalized=dict(workflow='runtime_benchmark', output=str(out), engines=['boltz','lasermpnn'],
                    runtime_python_paths=[cfg['python'],cfg['laser_python']],
                    scheduler=cfg['scheduler'], msa_policy=cfg['msa_policy'],
                    steps=[dict(stage='affinity-and-cpu-efficiency',command=command,cwd=str(out))])
    plan=_persist('desktop_runtime_benchmark','biotin-affinity-efficiency',normalized,command,
                  'apple_gpu_exclusive',_script_provenance(list(dict.fromkeys(files))))
    save(out/'plan.json',plan)
    job=server.tool_call('job_start',dict(plan_id=plan['id'],plan_sha256=plan['sha256']))
    save(out/'submitted.json',job)
    print(json.dumps(dict(plan_id=plan['id'],sha256=plan['sha256'],job=job)),flush=True)


if __name__ == '__main__':
    parser=argparse.ArgumentParser();parser.add_argument('--submit',type=Path)
    args=parser.parse_args()
    if args.submit: submit(args.submit)
    else: freeze()
