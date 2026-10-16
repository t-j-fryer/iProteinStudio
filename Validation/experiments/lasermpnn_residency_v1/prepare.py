"""Freeze a bounded CPU qualification and submit through Studio's job manager."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import shutil
import sys
from datetime import datetime, timezone

def main():
    parser=argparse.ArgumentParser();parser.add_argument('--start',action='store_true');args=parser.parse_args()
    root=Path(os.environ.get('NANOHUNTER_ROOT',Path.home()/'.iproteinstudio'))
    here=Path(__file__).resolve().parent;repo=here.parents[2]
    out=repo/'Validation/output/lasermpnn_residency_v1'/datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ')
    frozen=out/'frozen';frozen.mkdir(parents=True)
    shutil.copy2(here/'benchmark.py',frozen/'benchmark.py')
    inputs=[]
    for label,run in [('boltz','nise-3ea5fa63a1effece'),('rfd3','nise-16b14dfae15e62d5')]:
        files=sorted((root/'projects/test2/nise_runs'/run/'phase0/cycle01/design').glob('*/prepared.pdb'))[:2]
        if len(files)!=2:raise RuntimeError('Missing saved prepared qualification inputs')
        for src in files:
            dest=frozen/f'{label}_{src.parent.name}.pdb';shutil.copy2(src,dest);inputs.append(str(dest))
    source=root/'src/LASErMPNN';weights=source/'model_weights/laser_weights_0p1A_nothing_heldout.pt'
    sha=lambda p:hashlib.sha256(Path(p).read_bytes()).hexdigest()
    cfg=dict(schema=1,output=str(out),source_parent=str(source.parent),weights=str(weights),inputs=inputs,
             inputs_sha256={p:sha(p) for p in inputs},config_path=str(frozen/'config.json'),
             protocol='4 prepared biotin complexes; 1/5 designs; fresh vs resident1/2/4 CPUs; threads1/2; two alternating repeats; reset Python/NumPy/Torch RNG after loading; no GPU',
             expected_designs=240,upstream_sha256={str(p):sha(p) for p in source.rglob('*.py')},weights_sha256=sha(weights))
    (frozen/'config.json').write_text(json.dumps(cfg,indent=2)+'\n')
    sys.path.insert(0,str(root/'mcp'))
    from iprotein_mcp.plans import _persist,_script_provenance
    from iprotein_mcp.broker import start_job
    py=root/'venvs/NanoHunter_lasermpnn/bin/python'
    command=['/usr/bin/env','PYTHONDONTWRITEBYTECODE=1','KMP_USE_SHM=0','OMP_NUM_THREADS=1',
             'MKL_NUM_THREADS=1','OPENBLAS_NUM_THREADS=1','VECLIB_MAXIMUM_THREADS=1',
             '/usr/bin/caffeinate','-dimsu',str(py),str(frozen/'benchmark.py'),'--config',str(frozen/'config.json')]
    normalized=dict(workflow='runtime_benchmark',engines=['lasermpnn'],runtime_python_paths=[str(py)],
                    output=str(out),msa_policy='not applicable; inverse folding of saved ligand complexes',
                    scheduler='CPU-only persistent pools; exclusive Studio lease to avoid contention with other scientific work',
                    steps=[dict(stage='lasermpnn-cpu-qualification',command=command,cwd=str(out))])
    files=list(frozen.iterdir())+[weights,py]+list(source.rglob('*.py'))
    plan=_persist('desktop_runtime_benchmark','lasermpnn-qualification',normalized,command,
                  'apple_gpu_exclusive',_script_provenance(files))
    (out/'plan.json').write_text(json.dumps(plan,indent=2)+'\n')
    print(json.dumps(dict(output=str(out),plan_id=plan['id'],sha256=plan['sha256'])),flush=True)
    if args.start:
        job=start_job(plan['id'],plan['sha256']);(out/'submitted.json').write_text(json.dumps(job,indent=2)+'\n')
        print(json.dumps(job),flush=True)

if __name__=='__main__':main()
