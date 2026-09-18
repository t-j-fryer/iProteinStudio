"""Bounded real-model batching, interruption recovery and affinity-head test."""
import json
import os
from pathlib import Path
from types import SimpleNamespace

from runtime import atomic,digest


def validate(output, descriptor):
    if descriptor.get('schema')!=1 or not 1<=len(descriptor.get('ids',[]))<=5:
        raise ValueError('Batch smoke requires 1–5 frozen inputs')
    paths=[]
    for relative,sha in descriptor['files'].items():
        path=(output/relative).resolve()
        if (output/'batch_test_inputs').resolve() not in path.parents or not path.is_file() or digest(path)!=sha:
            raise ValueError('Batch smoke input changed')
        paths.append(path)
    for name in descriptor['ids']:
        if f'batch_test_inputs/{name}/completed.json' not in descriptor['files']:
            raise ValueError('Missing frozen input receipt')
    return paths


def run(config_path):
    from batch_runtime import BatchBackend
    from contract import preflight,saved_request
    from ligand_atoms import resolve
    output=Path(config_path).resolve().parent;config=json.loads(Path(config_path).read_text())
    validate(output,config['batch_test']);settings=preflight(Path(os.environ['NANOHUNTER_ROOT']),saved_request(config['request']))
    if settings['partial_noising'] or settings['nesso_screen'] or settings['phase0_nesso_screen']:
        raise ValueError('Batch smoke isolates ordinary Boltz scheduling')
    sequences={};pocket=None
    for name in config['batch_test']['ids']:
        saved=json.loads((output/'batch_test_inputs'/name/'completed.json').read_text())
        sequences[name]=saved['input']['sequence'];pocket=saved['input']['pocket']
    scripts=Path(__file__).resolve().parent.parent
    root=Path(os.environ['NANOHUNTER_ROOT']);manifest=resolve(settings['smiles'])
    args=SimpleNamespace(seed=settings['seed'],use_potentials=True,boltz_phase='structure')
    directory=output/'folds'
    class Interrupted(Exception):pass
    class InterruptOnce(BatchBackend):
        def _execute(self,directory,pending,args,phase,affinity,checkpoint,apo=False):
            def interrupt(marker):
                atomic(output/'intentional_interruption.json',dict(marker=str(marker),
                    stage='Native writer completed; controller has not committed unit receipt'))
                raise Interrupted('Controlled checkpoint recovery test')
            return super()._execute(directory,pending,args,phase,affinity,interrupt,apo)
    backend=InterruptOnce(root,output,settings,scripts)
    try:
        backend.fold(sequences,manifest['smiles_used'],directory,args,pocket)
        raise RuntimeError('Fault injection did not trigger')
    except Interrupted:
        pass
    finally:backend.close()
    backend=BatchBackend(root,output,settings,scripts)
    try:
        predictions=backend.fold(sequences,manifest['smiles_used'],directory,args,pocket)
        scored=backend.affinity(predictions,directory,args)
        receipts={str(p.relative_to(output)):digest(p) for p in directory.rglob('*completed.json')}
        again=backend.fold(sequences,manifest['smiles_used'],directory,args,pocket)
        rescored=backend.affinity(again,directory,args)
        if {str(p.relative_to(output)):digest(p) for p in directory.rglob('*completed.json')}!=receipts:
            raise RuntimeError('Resume changed completed operation receipts')
        if [p.pbind for p in scored.values()]!=[p.pbind for p in rescored.values()]:
            raise RuntimeError('Resume changed affinity results')
        counts={name:len(list((directory/'_batches').glob(f'structure-*/items/{name}.json'))) for name in sequences}
        if any(n!=1 for n in counts.values()):raise RuntimeError('Completed native input was folded twice')
        atomic(output/'summary.json',dict(status='completed',structures=len(predictions),affinities=len(scored),
            recovery_verified=True,repeat_resume_reused_all=True,native_completion_counts=counts))
    finally:backend.close()


if __name__=='__main__':
    import argparse
    parser=argparse.ArgumentParser();parser.add_argument('--config',required=True);run(parser.parse_args().config)
