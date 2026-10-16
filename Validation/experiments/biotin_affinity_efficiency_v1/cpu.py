"""Bounded CPU work, isolated and alongside saved-input affinity inference."""
from concurrent.futures import ProcessPoolExecutor
import json
import multiprocessing as mp
from pathlib import Path
import sys
import time
from common import save, seal, verified


def geometry(item):
    scripts, case = item
    sys.path.insert(0,str(Path(scripts)/'nise'))
    from atom_geometry import measure
    folder=Path(case['directory'])
    start=time.perf_counter()
    result=measure(case['pdb'],json.loads((folder/'geometry_settings.json').read_text()),
                   json.loads((folder/'ligand_atom_map.json').read_text()))
    return dict(key=case['key'],result=result,seconds=time.perf_counter()-start)


def main(cfg, mode, directory, workers):
    directory=Path(directory)
    if verified(directory) is not None:
        return
    if directory.exists():
        # Preserve an interrupted attempt; never merge incomplete output with a rerun.
        directory.rename(directory.with_name(directory.name+f'.interrupted-{time.time_ns()}'))
    directory.mkdir(parents=True)
    start=time.perf_counter()
    if mode=='geometry':
        cases=cfg['cases'] if workers!=2 or 'isolated' in str(directory) else cfg['cases'][:8]
        with ProcessPoolExecutor(workers,mp_context=mp.get_context('spawn')) as pool:
            rows=list(pool.map(geometry,[(cfg['scripts'],c) for c in cases]))
    elif mode=='laser':
        import laser_cpu
        specs=[dict(key=f'{i}_n{n}',input=p,count=n,seed=700+i*10+n,weights=cfg['weights'],
                    output=str(directory/f'{i}_n{n}'))
               for n in (1,5) for i,p in enumerate(cfg['laser_inputs'])]
        with ProcessPoolExecutor(workers,mp_context=mp.get_context('spawn'),
                                 initializer=laser_cpu.initialise,initargs=(cfg,1)) as pool:
            rows=list(pool.map(laser_cpu.task,specs))
    else:
        raise ValueError(mode)
    result=dict(mode=mode,workers=workers,elapsed_seconds=time.perf_counter()-start,rows=rows)
    save(directory/'results.json',result);seal(directory,result)


if __name__=='__main__':
    cfg=json.loads(Path(sys.argv[1]).read_text())
    main(cfg,sys.argv[2],sys.argv[3],int(sys.argv[4]))
