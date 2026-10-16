"""Bounded CPU-only qualification of the unmodified upstream LASErMPNN sampler.

Fresh and resident calls use the same upstream entry point and explicit RNG
reset AFTER weight loading. This is a new recorded seed policy, not a claim
that historical unseeded NISE sampling can be reproduced.
"""
import argparse
from concurrent.futures import ProcessPoolExecutor
import hashlib
import json
import multiprocessing as mp
import os
from pathlib import Path
import resource
import subprocess
import sys
import time

MODEL = None

def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()

def save(path, value):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    temp = path.with_suffix('.tmp')
    temp.write_text(json.dumps(value, indent=2) + '\n')
    temp.replace(path)

def initialise(cfg, threads):
    global MODEL
    os.environ.update(OMP_NUM_THREADS=str(threads), MKL_NUM_THREADS=str(threads),
                      OPENBLAS_NUM_THREADS=str(threads), VECLIB_MAXIMUM_THREADS=str(threads))
    sys.path.insert(0, cfg['source_parent'])
    import torch
    from LASErMPNN import run_batch_inference as upstream
    torch.set_num_threads(threads)
    torch.set_num_interop_threads(1)
    start = time.perf_counter()
    model, params = upstream.load_model_from_parameter_dict(cfg['weights'], 'cpu', strict=True)
    model.eval()
    MODEL = (upstream, model, params, time.perf_counter() - start)

def task(spec):
    import random
    import numpy as np
    import torch
    upstream, model, params, load_s = MODEL
    output = Path(spec['output'])
    if output.exists():
        raise RuntimeError('Refuse to overwrite a test unit')
    # Keep every upstream operation, including ligand featurization, constraints,
    # sidechain handling and FASTA scores. Cache only the verified model instance.
    original = upstream.load_model_from_parameter_dict
    def cached(*args, **kwargs):
        random.seed(spec['seed']); np.random.seed(spec['seed']); torch.manual_seed(spec['seed'])
        return model, params
    upstream.load_model_from_parameter_dict = cached
    arguments = [str(spec['input']), str(output), str(spec['count']), '--device', 'cpu',
                 '--model_weights_path', spec['weights'], '--sequence_temp', '0.5',
                 '--first_shell_sequence_temp', '0.7', '--fs_calc_ca_distance', '10',
                 '--disabled_residues', 'X,C', '--output_fasta_only', '--silent',
                 '-c', '--ala_budget', '2', '--gly_budget', '0']
    old_argv = sys.argv
    start = time.perf_counter()
    try:
        sys.argv = ['run_batch_inference', *arguments]
        upstream.run_inference(**upstream.parse_args(spec['weights']))
    finally:
        sys.argv = old_argv
        upstream.load_model_from_parameter_dict = original
    fasta = output / 'designs.fasta'
    lines = fasta.read_text().splitlines()
    sequences = [x for x in lines if x and not x.startswith('>')]
    if len(sequences) != spec['count'] or any(set(s) - set('ACDEFGHIKLMNPQRSTVWY') for s in sequences):
        raise RuntimeError('Invalid sampler output')
    row = dict(key=spec['key'], sha256=sha(fasta), count=len(sequences),
               wall_seconds=time.perf_counter()-start, load_seconds=load_s,
               pid=os.getpid(), peak_rss_bytes=resource.getrusage(resource.RUSAGE_SELF).ru_maxrss,
               cpu_seconds=sum(resource.getrusage(resource.RUSAGE_SELF)[i] for i in (0,1)))
    save(output/'receipt.json', row)
    return row

def run(cfg):
    out = Path(cfg['output'])
    for path, digest in cfg['inputs_sha256'].items():
        if sha(path) != digest:
            raise RuntimeError(f'Input changed: {path}')
    arms = [('fresh', 0, 1), ('resident1', 1, 1), ('resident2', 2, 1),
            ('resident4', 4, 1), ('resident2_threads2', 2, 2)]
    results = []
    # Reverse order on repeat to reduce first/last ordering bias.
    for repeat in range(2):
        for label, workers, threads in (arms if repeat == 0 else arms[::-1]):
            directory = out/f'r{repeat}_{label}'
            directory.mkdir()
            specs = [dict(key=f'{i}_n{n}', input=p, count=n, seed=700+i*10+n,
                          weights=cfg['weights'], output=str(directory/f'{i}_n{n}'))
                     for n in (1,5) for i,p in enumerate(cfg['inputs'])]
            start = time.perf_counter()
            if workers:
                with ProcessPoolExecutor(workers, mp_context=mp.get_context('spawn'),
                        initializer=initialise, initargs=(cfg,threads)) as pool:
                    rows = list(pool.map(task,specs))
            else:
                rows=[]
                for spec in specs:
                    specpath=directory/(spec['key']+'.json');save(specpath,spec)
                    with (directory/(spec['key']+'.log')).open('w') as log:
                        subprocess.run([sys.executable,__file__, '--config', cfg['config_path'],
                                        '--single',str(specpath)],check=True,stdout=log,stderr=subprocess.STDOUT)
                    rows.append(json.loads((Path(spec['output'])/'receipt.json').read_text()))
            result=dict(arm=label,repeat=repeat,workers=workers,threads=threads,
                        elapsed_seconds=time.perf_counter()-start,rows=rows)
            save(directory/'summary.json',result);results.append(result)
            print(json.dumps({k:v for k,v in result.items() if k!='rows'}),flush=True)
    reference={r['key']:r['sha256'] for r in results[0]['rows']}
    mismatches=[dict(arm=a['arm'],repeat=a['repeat'],key=r['key']) for a in results
                for r in a['rows'] if r['sha256']!=reference[r['key']]]
    save(out/'results.json',dict(arms=results,exact_fasta_score_mismatches=mismatches,
                               passed=not mismatches,scope='CPU-only; includes imports, loading and pool teardown'))
    if mismatches:raise RuntimeError('Sampling equivalence failed; inspect results.json')

if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('--config',required=True);parser.add_argument('--single')
    args=parser.parse_args();cfg=json.loads(Path(args.config).read_text())
    if args.single:
        initialise(cfg,1);task(json.loads(Path(args.single).read_text()))
    else:run(cfg)
