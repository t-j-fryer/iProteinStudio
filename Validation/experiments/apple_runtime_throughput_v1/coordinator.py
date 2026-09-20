#!/usr/bin/env python3
"""Run only under Studio's shared broker lease. Preserve interrupted attempts."""
import argparse
import json
import os
from pathlib import Path
import subprocess
import sys
from bench_worker import sha, atomic


def verify_seal(path):
    seal=json.loads(Path(path).read_text()); root=Path(seal['root'])
    actual={str(p.relative_to(root)) for p in root.rglob('*') if p.is_file() and '__pycache__' not in p.parts and p.suffix!='.pyc'}
    if actual != set(seal['files']): raise RuntimeError('Runtime file inventory changed')
    for name,digest in seal['files'].items():
        if sha(root/name)!=digest: raise RuntimeError('Runtime changed: '+name)
    return root/'bin/python'


def verify_completed(output, request):
    receipt=json.loads((output/'completed.json').read_text())
    if receipt['request_sha256']!=sha(request): raise RuntimeError('Request changed')
    actual={str(p.relative_to(output)) for p in output.rglob('*') if p.is_file() and p.name!='completed.json'}
    if actual!=set(receipt['files']): raise RuntimeError('Output inventory changed')
    for name,digest in receipt['files'].items():
        p=(output/name).resolve()
        if output.resolve() not in p.parents or sha(p)!=digest: raise RuntimeError('Completed output changed: '+name)


def main():
    ap=argparse.ArgumentParser();ap.add_argument('--manifest',type=Path,required=True);args=ap.parse_args()
    cfg=json.loads(args.manifest.read_text()); out=Path(cfg['output'])
    # A real broker job marker is required; a direct CLI invocation is not a supported launch path.
    marker=json.loads((out/'studio_job.json').read_text())
    if not marker.get('plan_id'): raise RuntimeError('No broker plan marker')
    envs={name:verify_seal(path) for name,path in cfg['seals'].items()}
    atomic(out/'runtime_verified.json',dict(seals={k:sha(v) for k,v in cfg['seals'].items()}))
    results={}
    for block in cfg['blocks']:
        base=out/block['id'];base.mkdir(exist_ok=True)
        complete=sorted(base.glob('attempt_*/completed.json'))
        if complete:
            attempt=complete[-1].parent;verify_completed(attempt,attempt.parent/(attempt.name+'.request.json'))
            print('BENCH_REUSED|'+block['id'],flush=True)
        else:
            i=1
            while (base/f'attempt_{i:03d}').exists():i+=1
            attempt=base/f'attempt_{i:03d}'
            request={**block,'output':str(attempt),'scripts':cfg['scripts'],'root':cfg['root'],'model_cache':cfg['model_cache']}
            req=base/(attempt.name+'.request.json');atomic(req,request)
            env=dict(os.environ,PYTHONDONTWRITEBYTECODE='1',PYTHONUNBUFFERED='1',PYTHONNOUSERSITE='1',PYTORCH_ENABLE_MPS_FALLBACK='0')
            env.pop('PYTHONPATH',None)
            for key in ('OMP_NUM_THREADS','OPENBLAS_NUM_THREADS','MKL_NUM_THREADS','VECLIB_MAXIMUM_THREADS','NUMEXPR_NUM_THREADS'):
                env[key]=str(block['threads'])
            print('BENCH_START|'+block['id'],flush=True)
            # Inherit broker process group so cancellation kills/reaps this worker too.
            with (base/(attempt.name+'.log')).open('w') as log:
                child=subprocess.Popen([str(envs[block['runtime']]),str(Path(__file__).with_name('bench_worker.py')),'--request',str(req)],env=env,stdout=subprocess.PIPE,stderr=subprocess.STDOUT,text=True)
                fallback_lines=[]
                for line in child.stdout:
                    log.write(line);log.flush();print(line,end='',flush=True)
                    lower=line.lower()
                    if ('fall back' in lower or 'fallback' in lower or 'falling back' in lower) and 'cpu' in lower:
                        fallback_lines.append(line.strip())
                code=child.wait()
            atomic(base/(attempt.name+'.fallbacks.json'),fallback_lines)
            if any('aten::linalg_svd' not in line for line in fallback_lines):
                raise RuntimeError('Undocumented CPU fallback; further blocks held')
            if code:raise RuntimeError(f'Block {block["id"]} failed with exit {code}; attempt retained')
            verify_completed(attempt,req)
        results[block['id']]=str(attempt)
        atomic(out/'progress.json',results)
        if block.get('reference'):
            report=out/(block['id']+'.comparison.json')
            left,right=results[block['reference']],str(attempt)
            if block.get('comparison_direction')=='this_is_baseline':left,right=right,left
            code=subprocess.call([str(envs[block['runtime']]),str(Path(__file__).with_name('analyse.py')),
                                  left,right,cfg['scientific_manifest'],str(report)],env=dict(os.environ,PYTHONDONTWRITEBYTECODE='1'))
            if code: raise RuntimeError('Numerical screen failed; further blocks held, raw outputs retained')
    atomic(out/'completed.json',dict(blocks=results,plan=marker))


if __name__=='__main__':main()
