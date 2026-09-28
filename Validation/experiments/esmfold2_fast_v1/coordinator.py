"""Sequential, audited prediction units under the shared GPU broker lease."""
import argparse
import json
import os
from pathlib import Path
import subprocess
import sys
import time
sys.dont_write_bytecode=True
from common import atomic,sha,verify_inventory

def main(path):
    cfg=json.loads(Path(path).read_text());here=Path(__file__).resolve().parent
    verify_inventory(cfg['inventory'])
    env=os.environ.copy();env.update(PYTHONDONTWRITEBYTECODE='1',PYTORCH_ENABLE_MPS_FALLBACK='0',HF_HUB_OFFLINE='1',TRANSFORMERS_OFFLINE='1',HF_DATASETS_OFFLINE='1',TOKENIZERS_PARALLELISM='false',OMP_NUM_THREADS='4',MKL_NUM_THREADS='4',MPLCONFIGDIR=str(Path(cfg['output'])/'matplotlib-cache'))
    contexts={};preparation={};hashes={}
    for context,contextpath in cfg['context_configs'].items():
        contexts[context]=json.loads(Path(contextpath).read_text())
        start=time.perf_counter()
        subprocess.run([cfg['host_python'],str(here/'features.py'),'prepare',contextpath],env=env,check=True)
        preparation[context]=time.perf_counter()-start
        hashes[context]=sha(Path(contexts[context]['output'])/'inputs/features.npz')
    receipts=[]
    for block in cfg['blocks']:
        context=block['context'];contextpath=cfg['context_configs'][context];out=Path(block['output'])
        if out.exists():raise RuntimeError('Do not overwrite partial/completed benchmark block')
        if sha(Path(contexts[context]['output'])/'inputs/features.npz')!=hashes[context]:raise RuntimeError('Frozen features changed')
        py=cfg['host_python'] if block['backend']=='pytorch' else cfg['pythons']['new']
        worker='torch_worker.py' if block['backend']=='pytorch' else 'mlx_worker.py'
        start=time.perf_counter();print('START '+block['id'],flush=True)
        subprocess.run([py,str(here/worker),'--config',contextpath,'--block',block['id']],env=env,check=True)
        inferred=time.perf_counter();record=json.loads((out/'worker_complete.json').read_text())
        if len(record['rows'])!=block['repeats']:raise RuntimeError('Wrong output cardinality')
        for row in record['rows']:
            unit=Path(row['unit'])
            if sha(unit/'outputs.npz')!=row['outputs_sha256']:raise RuntimeError('Raw output changed')
            subprocess.run([cfg['host_python'],str(here/'features.py'),'decode',contextpath,'--unit',str(unit)],env=env,check=True)
        elapsed=time.perf_counter()-start
        atomic(out/'timings.json',dict(worker_and_decode_seconds=elapsed,model_process_seconds=inferred-start,feature_prepare_shared_seconds=preparation[context],complete_two_calls_including_prepare_seconds=elapsed+preparation[context],model_call_seconds=[r['inference_seconds'] for r in record['rows']],feature_sha256=hashes[context],scope='One fresh process, two same-seed predictions with weights retained between calls, CPU decode/audit per output. First and resident call reported separately.'))
        files=[dict(path=str(p),sha256=sha(p)) for p in sorted(out.rglob('*')) if p.is_file()]
        atomic(out/'completed.json',dict(block=block['id'],files=files));receipts.append(str(out/'completed.json'))
        atomic(Path(cfg['output'])/'progress.json',dict(completed=receipts));print('AUDITED '+block['id'],flush=True)
    atomic(Path(cfg['output'])/'completed.json',dict(receipts=receipts,feature_sha256=hashes,config_sha256=sha(path)))

if __name__=='__main__':
    ap=argparse.ArgumentParser();ap.add_argument('--config',required=True);a=ap.parse_args();main(a.config)
