"""Finish CPU/overlap checks without repeating the completed affinity cohort."""
import json
from pathlib import Path
import sys
import time
from common import save, seal, verified
from run import Replay, cpu_job, finish_cpu


def main(config):
    cfg=json.loads(config.read_text());out=Path(cfg['output'])
    from common import sha
    for p,digest in cfg['frozen_inputs_sha256'].items():
        if sha(p)!=digest:raise RuntimeError('Frozen input changed: '+p)
    # Retain completed control provenance; never edit the cancelled parent's data.
    parent=Path(cfg['continued_from'])
    for arm in ('reference','light'):
        results=[verified(p.parent) for p in (parent/'r0'/arm).glob('*/completed.json')]
        assert sum(len(r['rows']) for r in results)==48
    geometries=[]
    for repeat in range(2):
        for workers in ([1,2,4,8] if repeat==0 else [8,4,2,1]):
            path=out/'isolated_geometry'/f'r{repeat}_w{workers}'
            finish_cpu([cpu_job(cfg,config,'geometry',path,workers)])
            geometries.append(verified(path))
    ref={r['key']:r['result'] for r in geometries[0]['rows']}
    assert all({r['key']:r['result'] for r in g['rows']}==ref for g in geometries)
    save(out/'geometry_results.json',dict(passed=True,arms=geometries))
    replay=Replay(cfg)
    replay.batch(out/'warmup',cfg['cases'][:2],cfg['arms'][1],0)
    overlaps=[]
    # One matched same-seed serial/overlap pair, not a second affinity seed trial.
    for mode in ('serial','overlap'):
        path=out/'overlap'/mode
        if verified(path) is not None:
            overlaps.append(verified(path));continue
        if path.exists():path.rename(path.with_name(path.name+f'.interrupted-{time.time_ns()}'))
        path.mkdir(parents=True);start=time.perf_counter()
        jobs=[cpu_job(cfg,config,'laser',path/'laser',2),cpu_job(cfg,config,'geometry',path/'geometry',2)]
        try:
            if mode=='serial':finish_cpu(jobs)
            gpu=replay.batch(path/'affinity',cfg['cases'][:8],cfg['arms'][1],0)
            if mode=='overlap':finish_cpu(jobs)
        finally:
            for proc,log in jobs:
                if proc.poll() is None:proc.terminate();proc.wait()
                log.close()
        result=dict(mode=mode,elapsed_seconds=time.perf_counter()-start,gpu=gpu,
                    laser=verified(path/'laser'),geometry=verified(path/'geometry'))
        seal(path,result);overlaps.append(result)
    save(out/'overlap_results.json',dict(arms=overlaps))
    serial,overlap=overlaps
    laser=lambda a:{r['key']:r['sha256'] for r in a['laser']['rows']}
    geometry=lambda a:{r['key']:r['result'] for r in a['geometry']['rows']}
    from analyse import compare
    scores=compare({r['key']:r for r in serial['gpu']['rows']},{r['key']:r for r in overlap['gpu']['rows']})
    summary=dict(geometry_exact=True,serial_seconds=serial['elapsed_seconds'],
                 overlap_seconds=overlap['elapsed_seconds'],
                 serial_over_overlap=serial['elapsed_seconds']/overlap['elapsed_seconds'],
                 exact_laser_fasta_scores=laser(serial)==laser(overlap),
                 exact_overlap_geometry=geometry(serial)==geometry(overlap),affinity=scores,
                 repeats=1,production_default_changed=False)
    save(out/'analysis/summary.json',summary)
    assert summary['exact_laser_fasta_scores'] and summary['exact_overlap_geometry'] and scores['identical_feature_hashes']
    save(out/'completed.json',dict(passed=True,scope='Prepared-input CPU/affinity overlap; one same-seed pair; not a full cycling benchmark'))


if __name__=='__main__':main(Path(sys.argv[1]))
