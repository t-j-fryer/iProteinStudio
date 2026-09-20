#!/usr/bin/env python3
"""Narrow Validation-only plan factory; launch exclusively through MCP job_start.

Uses the same immutable plan persistence and desktop step executor as Studio.
This is not an arbitrary-command endpoint and adds no production tool surface.
"""
import argparse
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
from bench_worker import atomic, sha

REPO=Path(__file__).resolve().parents[3]
EXPERIMENT=Path(__file__).resolve().parent
OUTPUT=REPO/'Validation/output/apple_runtime_throughput_v1'


def main():
    ap=argparse.ArgumentParser();ap.add_argument('--stage',choices=['smoke','threads','repeat','profile','schedule','precision'],default='smoke');ap.add_argument('--start',action='store_true');args=ap.parse_args()
    if os.environ.get('IPROTEINSTUDIO_AGENT_ROOT'): raise SystemExit('Shared production broker root required; remove agent-root override')
    root=Path(os.environ.get('NANOHUNTER_ROOT',Path.home()/'.iproteinstudio')).resolve()
    os.environ['NANOHUNTER_ROOT']=str(root)
    sys.path.insert(0,str(REPO/'Sources/iProteinStudio/Resources/pipeline/mcp'))
    from server import MCPServer
    from iprotein_mcp.plans import _persist, _script_provenance
    server=MCPServer('run')
    guide=server.tool_call('workflow_guide',{'workflow':'prediction'})
    spec=json.loads((EXPERIMENT/'manifest.json').read_text())
    if args.stage!='smoke':
        passed=[]
        for p in OUTPUT.glob('smoke_*/candidate.comparison.json'):
            if (p.parent/'completed.json').exists() and json.loads(p.read_text())['passed']:passed.append(p)
        if not passed:raise SystemExit('Complete the bounded paired smoke before further screening')
    stamp=datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S%fZ')
    out=OUTPUT/(args.stage+'_'+stamp);out.mkdir(parents=True)
    frozen=out/'frozen';frozen.mkdir();scripts=frozen/'scripts';scripts.mkdir()
    for name in ('bench_worker.py','coordinator.py','analyse.py','profile_stages.py','equivalent_schedule.py','selective_precision.py','manifest.json'):
        shutil.copy2(EXPERIMENT/name,frozen/name)
    # Use exact managed production helpers, snapshotted against later app updates.
    for name in ('resident_predictor.py','boltz_mps.py','validate_prediction_geometry.py'):
        shutil.copy2(root/'scripts'/name,scripts/name)
    seals={}
    for name in ('boltz-torch213','boltz-torch214'):
        p=frozen/(name+'.seal.json');shutil.copy2(OUTPUT/p.name,p);seals[name]=str(p)
    seed=43 if args.stage=='repeat' else 42
    cases=[dict(**spec['cases'][0],seed=seed,warmup=True)]+[dict(**x,seed=seed,warmup=False) for x in spec['cases']]
    configs=[('baseline','boltz-torch213','2.13.0',4,None),('candidate','boltz-torch214','2.14.0',4,'baseline')]
    if args.stage=='threads':
        configs=[('reference','boltz-torch214','2.14.0',4,None)]+[(f'threads{n}','boltz-torch214','2.14.0',n,'reference') for n in (1,8,12)]
    if args.stage=='repeat':
        configs=[('candidate','boltz-torch214','2.14.0',4,None),('baseline','boltz-torch213','2.13.0',4,'candidate')]
    if args.stage=='profile':
        configs=[('reference','boltz-torch214','2.14.0',4,None),('profile','boltz-torch214','2.14.0',4,'reference')]
    if args.stage=='schedule':
        configs=[('reference','boltz-torch214','2.14.0',4,None),('schedule','boltz-torch214','2.14.0',4,'reference')]
    if args.stage=='precision':
        configs=[('reference','boltz-torch214','2.14.0',4,None),('diffusion_bf16','boltz-torch214','2.14.0',4,'reference')]
    cores=int(subprocess.check_output(['/usr/sbin/sysctl','-n','hw.physicalcpu'],text=True).strip())
    if max(c[3] for c in configs)>cores:raise SystemExit('Requested thread count exceeds physical cores; declare a device-specific manifest')
    blocks=[dict(id=i,runtime=r,torch_version=v,threads=t,reference=ref,cases=cases) for i,r,v,t,ref in configs]
    if args.stage=='profile':blocks[-1]['profile']=True
    if args.stage=='repeat':blocks[-1]['comparison_direction']='this_is_baseline'
    if args.stage=='schedule':blocks[-1]['variant']='schedule_host_once'
    if args.stage=='precision':blocks[-1]['variant']='diffusion_bf16'
    cfg=dict(output=str(out),scripts=str(scripts),root=str(root),model_cache=str(root/'models/boltz2'),seals=seals,
             scientific_manifest=str(frozen/'manifest.json'),blocks=blocks,scheduler='one resident model per block; serial GPU blocks; shared broker lease')
    manifest=frozen/'run.json';atomic(manifest,cfg)
    atomic(out/'workflow_guide.json',guide)
    host={k:subprocess.check_output(cmd,text=True).strip() for k,cmd in {
        'chip':['/usr/sbin/sysctl','-n','machdep.cpu.brand_string'], 'physical_cores':['/usr/sbin/sysctl','-n','hw.physicalcpu'],
        'memory_bytes':['/usr/sbin/sysctl','-n','hw.memsize'],'os':['/usr/bin/sw_vers'],
        'git_commit':['git','-C',str(REPO),'rev-parse','HEAD']}.items()}
    host['source_hashes']={str(p.relative_to(REPO)):sha(p) for p in EXPERIMENT.glob('*.py')}
    atomic(out/'host.json',host)
    assets=[root/'models/boltz2/boltz2_conf.ckpt']
    # The fixture uses canonical amino acids only. Freeze their actual component records.
    mols=root/'models/boltz2/mols'
    assets += [mols/(name+'.pkl') for name in ('ALA','ARG','ASN','ASP','CYS','GLN','GLU','GLY','HIS','ILE','LEU','LYS','MET','PHE','PRO','SER','THR','TRP','TYR','VAL')]
    command=['/usr/bin/caffeinate','-dimsu',sys.executable,str(frozen/'coordinator.py'),'--manifest',str(manifest)]
    provenance=_script_provenance([p for p in frozen.rglob('*') if p.is_file()]+assets+[Path(sys.executable).resolve()])
    normalized=dict(workflow='runtime_benchmark',output=str(out),scheduler=cfg['scheduler'],steps=[dict(stage='runtime-benchmark',command=command,cwd=str(out))])
    plan=_persist('desktop_runtime_benchmark','validation-runtime-benchmark',normalized,command,'apple_gpu_exclusive',provenance)
    atomic(out/'plan.json',plan)
    print(json.dumps({'output':str(out),'plan_id':plan['id'],'plan_sha256':plan['sha256']}),flush=True)
    if args.start:
        job=server.tool_call('job_start',{'plan_id':plan['id'],'plan_sha256':plan['sha256']})
        atomic(out/'submitted.json',job);print(json.dumps(job),flush=True)


if __name__=='__main__':main()
