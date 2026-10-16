"""Bounded paired qualification of the shipping ligand adapters; managed job only."""
import hashlib
import json
import os
from pathlib import Path
import sys
import time
from types import SimpleNamespace


def main(config_path):
    cfg = json.loads(Path(config_path).read_text())
    out = Path(cfg['output']); scripts = Path(cfg['scripts'])
    sys.path[:0] = [str(scripts), str(scripts/'nise')]
    from prediction_profiles import activate
    from runtime import atomic, digest
    from batch_runtime import PoolBackend
    from proposal_pipeline import run
    from ligand_atoms import resolve, validate_selection
    from nise_lib import rank_score
    activate(cfg['prediction_settings'])
    manifest = resolve(cfg['smiles'])
    settings = {**cfg['geometry'], 'smiles': cfg['smiles'], 'ligand_atom_signature': manifest['signature'],
                'scheduler':'resident', 'scoring_mode':'boltz', 'nesso_screen':False, 'geometry_workers':2}
    validate_selection(settings, manifest)
    args = SimpleNamespace(seed=42, use_potentials=True, boltz_phase='structure', fs_distance=10., ala_budget=2, gly_budget=0)
    summaries = {}
    for mode in ('fresh_serial', 'resident_overlap'):
        directory = out/mode
        backend = PoolBackend(Path(cfg['root']),directory,settings,scripts,workers=1)
        backend.ligand_manifest = manifest
        native = backend.science.lasermpnn_design
        if mode == 'fresh_serial':
            def fresh(*a, **kw):
                kw.pop('worker_queue',None);kw.pop('worker_owner',None)
                return native(*a,**kw)
            backend.science.lasermpnn_design = fresh
        rows = [];parents = [Path(x) for x in cfg['inputs']];started=time.perf_counter()
        try:
            for cycle in range(2):
                items=[dict(pdb=str(p),directory=directory/f'c{cycle}/design/{i}',names=[f'c{cycle}_p{i}'],
                            owner=i,seed=100+cycle*10+i) for i,p in enumerate(parents)]
                def design(item):
                    return backend.design(item['pdb'], item['directory'], 1, cfg['smiles'],args,.5,.7,item['seed'],'all',True)
                fold_dir=directory/f'c{cycle}/fold'
                seqs,refs,owners,preds=run(items,design,lambda s:backend.fold(s,cfg['smiles'],fold_dir,args),
                                         overlap=(mode=='resident_overlap'),chunk_size=2)
                checked=backend.check_atom_requirements_batch(preds)
                scored=backend.affinity(preds,fold_dir,args)
                parents=[Path(preds[f'c{cycle}_p{i}'].pdb) for i in range(len(parents))]
                for name in seqs:
                    pred=scored[name]
                    rows.append(dict(name=name,sequence=seqs[name],geometry_pass=checked[name],
                                     pbind=pred.pbind,ligand_plddt=pred.ligand_plddt,
                                     score=rank_score(pred,'ligand_plddt+pbind'),pdb_sha256=digest(pred.pdb)))
                # Replaying audited folds/affinities must not start new requests.
                sessions=len(list((directory/'sessions').glob('*')))
                replay=backend.fold(seqs,cfg['smiles'],fold_dir,args)
                backend.affinity(replay,fold_dir,args)
                assert sessions==len(list((directory/'sessions').glob('*')))
            summaries[mode]=dict(rows=rows,seconds=time.perf_counter()-started)
            atomic(directory/'summary.json',summaries[mode])
        finally:
            backend.close();backend.close_design();backend.science.lasermpnn_design=native
    a,b=summaries.values()
    mismatches=[dict(a=x,b=y) for x,y in zip(a['rows'],b['rows']) if x!=y]
    atomic(out/'summary.json',dict(arms=summaries,exact_mismatches=mismatches,passed=not mismatches,
                                  scope='four saved biotin starts; two cycles; structure, affinity, geometry and replay'))
    if mismatches:raise RuntimeError('Paired release outputs differ; inspect summary.json')


if __name__=='__main__':main(sys.argv[1])
