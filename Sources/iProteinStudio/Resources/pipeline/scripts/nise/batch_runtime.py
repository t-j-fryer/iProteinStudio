"""Opt-in stage-directory execution, retaining per-input NISE checkpoints."""
from dataclasses import asdict
import json
import math
from pathlib import Path
import re
import shutil
import time
from types import SimpleNamespace
import uuid

from runtime import Backend, ResidentClient, atomic, digest, input_digest


class BatchClient(ResidentClient):
    worker_script = 'nise/batch_worker.py'

    def predict_many(self, batch, count, affinity, phase, on_item, prediction_seed=None):
        identifier=uuid.uuid4().hex
        filename='request_'+identifier+'.json'
        source,out=batch/'yaml',batch/'out'
        checksum=input_digest(source)
        atomic(self.queue/'requests'/filename,dict(request_id=identifier,input_dir=str(source),
            output_dir=str(out),expected_jobs=count,input_sha256=checksum,phase=phase,prediction_seed=prediction_seed))
        response=self.queue/'responses'/filename
        seen=set();deadline=time.monotonic()+1800
        while True:
            for marker in sorted((batch/'items').glob('*.json')):
                if marker.name not in seen:
                    on_item(marker);seen.add(marker.name);deadline=time.monotonic()+1800
            if response.exists():
                # The final marker may have arrived after this iteration's scan.
                for marker in sorted((batch/'items').glob('*.json')):
                    if marker.name not in seen:
                        on_item(marker);seen.add(marker.name)
                receipt=json.loads(response.read_text())
                break
            if self.process.poll() is not None:
                raise RuntimeError(f'NISE batch worker exited; see {self.log}')
            if time.monotonic()>deadline:
                raise RuntimeError(f'No completed NISE input for 30 minutes; see {self.log}')
            time.sleep(.1)
        loads=2 if affinity or self.loaded_affinity else 1
        if (not receipt.get('ok') or receipt.get('request_id')!=identifier
                or receipt.get('input_sha256')!=checksum or receipt.get('completed_jobs')!=count
                or receipt.get('phase')!=phase or receipt.get('model_load_count')!=loads
                or receipt.get('prediction_seed')!=prediction_seed or len(seen)!=count):
            raise RuntimeError(f'Incomplete NISE directory request: {receipt}; see {self.log}')
        self.loaded_affinity=self.loaded_affinity or affinity
        atomic(batch/'request_completed.json',dict(receipt,session=str(self.queue),startup_seconds=self.ready['startup_seconds']))


def copy_processed(source, destination, name):
    """Copy one native input cache; generate its manifest using native types."""
    from boltz.data.types import Manifest, Record
    required=[source/folder/f'{name}.{ext}' for folder,ext in
              (('records','json'),('structures','npz'),('mols','pkl'),('constraints','npz'))]
    if not all(p.is_file() for p in required):
        raise RuntimeError(f'Incomplete native processed input for {name}')
    for p in required:
        target=destination/p.relative_to(source);target.parent.mkdir(parents=True,exist_ok=True)
        shutil.copy2(p,target)
    # This route uses empty MSAs. Never silently drop an MSA cache.
    if any((source/'msa').glob('*')):
        raise RuntimeError('Stage-directory NISE requires empty MSAs')
    records=[Record.load(p) for p in (destination/'records').glob('*.json')]
    Manifest(records).dump(destination/'manifest.json')


def verify_event(marker, spec):
    batch=marker.parent.parent
    event=json.loads(marker.read_text());descriptor=json.loads((batch/'batch.json').read_text())
    name=event['name']
    if (descriptor['specifications'].get(name)!=spec or descriptor['phase']!=event['phase']
            or digest(batch/'yaml'/f'{name}.yaml')!=event['yaml_sha256']):
        raise RuntimeError('Batch checkpoint input changed')
    for relative,sha in event['files'].items():
        path=(batch/relative).resolve()
        if batch.resolve() not in path.parents or not path.is_file() or digest(path)!=sha:
            raise RuntimeError(f'Batch checkpoint artifact changed: {relative}')
    return event


class BatchBackend(Backend):
    def _worker(self,args,apo=False):
        if self.worker is None:
            self.worker=BatchClient(self.root,self.output,self.scripts,args.seed,not apo and args.use_potentials,not apo)
        if not isinstance(self.worker,BatchClient):
            raise RuntimeError('Stage-directory execution requires its checkpoint-aware worker')
        return self.worker

    def _execute(self, directory, pending, args, phase, affinity, checkpoint, apo=False):
        if not pending:
            return
        seeds={spec.get('prediction_seed') for spec in pending.values()}
        if len(seeds)!=1:
            raise ValueError('Stage-directory execution does not support mixed per-input seed overrides')
        batch=directory/'_batches'/(phase+'-'+uuid.uuid4().hex)
        source=batch/'yaml';source.mkdir(parents=True)
        processed=batch/'out/boltz_results_yaml/processed'
        # Freeze membership and operation specs before the worker sees inputs.
        atomic(batch/'batch.json',dict(schema=1,phase=phase,affinity=affinity,
            specifications=pending,seed=args.seed,rng_policy='Boltz request stream; membership and preprocessing retained'))
        for name,spec in pending.items():
            unit=directory/name
            shutil.copy2(unit/'yaml'/f'{name}.yaml',source/f'{name}.yaml')
            if phase=='affinity':
                copy_processed(unit/'out/boltz_results_yaml/processed',processed,name)
                shutil.copytree(unit/'out/boltz_results_yaml/predictions'/name,
                                batch/'out/boltz_results_yaml/predictions'/name)
            else:
                # Reuse preprocessing from interrupted directory requests. This
                # preserves their ligand conformers without trusting raw folds.
                for previous in sorted((directory/'_batches').glob('*/batch.json'),reverse=True):
                    if previous.parent==batch:continue
                    old=json.loads(previous.read_text())
                    cache=previous.parent/'out/boltz_results_yaml/processed'
                    if old['specifications'].get(name)==spec and (cache/'manifest.json').is_file():
                        copy_processed(cache,processed,name);break
        self._worker(args,apo).predict_many(batch,len(pending),affinity,phase,checkpoint,next(iter(seeds)))

    def fold(self,sequences,smiles,directory,args,pocket=None,apo=False):
        import preorg
        from ligand_atoms import audit_atoms
        directory=Path(directory);predictions={};pending={}
        phase='complete' if apo else getattr(args,'boltz_phase','complete')
        if self.settings.get('nesso_screen') and not getattr(args,'skip_nesso',False) and not apo and sequences and all(
                re.fullmatch(r'c\d+_t\d+_n\d+_s\d+',name) for name in sequences):
            from nesso_screen import screen
            sequences=screen(self,sequences,smiles,directory.parent/'nesso',
                allow_empty=self.settings.get('adaptive_proposals',False) or self.settings.get('partial_noising',False))
        def commit(marker):
            name=marker.stem;spec=pending[name];event=verify_event(marker,spec)
            batch=marker.parent.parent;unit=directory/name;out=unit/'out'
            if phase=='structure' and list((batch/'out/boltz_results_yaml/predictions'/name).glob('affinity_*.json')):
                raise RuntimeError('Unexpected affinity output during structure-only folding')
            target=out/'boltz_results_yaml/predictions'/name
            if out.exists():
                out.rename(unit/('interrupted-out-'+uuid.uuid4().hex))
            shutil.copytree(batch/'out/boltz_results_yaml/predictions'/name,target)
            copy_processed(batch/'out/boltz_results_yaml/processed',out/'boltz_results_yaml/processed',name)
            pred=self.science.parse_prediction(out,name)
            if pred is None:raise RuntimeError('Missing batch prediction '+name)
            if phase=='structure':pred.pbind=None
            if phase=='complete' and not apo:self.science.rank_score(pred,'ligand_plddt+pbind')
            self.audit_structure(pred.pdb,spec['sequence'],not apo)
            if not apo:audit_atoms(pred.pdb,self.atom_manifest(smiles))
            values={k:(None if isinstance(v,float) and not math.isfinite(v) else v) for k,v in asdict(pred).items()}
            files=[unit/'yaml'/f'{name}.yaml']+[p for p in out.rglob('*') if p.is_file()]
            self.journal.save(unit/'completed.json',spec,dict(prediction=values,timing=event['timing']),files)
            predictions[name]=pred
            atomic(self.output/'progress.json',dict(message=f'Completed {name}',scheduler=self.settings['scheduler'],submission='stage-directory'))
            print(f'NISE|completed|{name}',flush=True)
        try:
            for name,sequence in sequences.items():
                unit=directory/name;source=unit/'yaml';source.mkdir(parents=True,exist_ok=True)
                spec=dict(sequence=sequence,smiles=None if apo else smiles,pocket=pocket,affinity=not apo,
                    seed=args.seed,potentials=False if apo else args.use_potentials)
                override=getattr(args,'prediction_seeds',{}).get(name)
                if override is not None:spec.update(seed=override,prediction_seed=override)
                if phase!='complete':spec['phase']=phase
                saved=self.journal.load(unit/'completed.json',spec)
                if saved is not None:
                    self.audit_structure(saved['prediction']['pdb'],sequence,not apo)
                    if not apo:audit_atoms(saved['prediction']['pdb'],self.atom_manifest(smiles))
                    predictions[name]=SimpleNamespace(**saved['prediction']);continue
                yaml=source/f'{name}.yaml'
                if apo:preorg.write_apo_yaml(yaml,sequence)
                else:self.science.write_boltz_yaml(yaml,sequence,smiles,affinity=True,pocket=pocket)
                pending[name]=spec
            # Recover atomic native-writer markers even if the controller was
            # cancelled before it copied the last completed prediction.
            for name in list(pending):
                markers=sorted((directory/'_batches').glob(f'*/items/{name}.json'))
                for marker in markers:
                    descriptor=json.loads((marker.parent.parent/'batch.json').read_text())
                    if descriptor['specifications'].get(name)==pending[name] and descriptor['phase']==phase:
                        commit(marker);del pending[name];break
            self._execute(directory,pending,args,phase,not apo and phase=='complete',commit,apo)
        finally:
            if self.settings['scheduler']=='cycle-wave' and phase!='structure':self.close()
        return {name:predictions[name] for name in sequences}

    def affinity(self,predictions,directory,args):
        directory=Path(directory);result={};pending={};structures={}
        for name in predictions:
            unit=directory/name;saved=json.loads((unit/'completed.json').read_text())
            if saved['input'].get('phase')!='structure':raise RuntimeError('Selective affinity requires structure checkpoint')
            self.journal.load(unit/'completed.json',saved['input']);structures[name]=saved
            spec=dict(structure_receipt_sha256=digest(unit/'completed.json'))
            scored=self.journal.load(unit/'affinity_completed.json',spec)
            if scored:result[name]=SimpleNamespace(**scored['prediction'])
            else:pending[name]=spec
        def commit(marker):
            name=marker.stem;event=verify_event(marker,pending[name]);unit=directory/name
            source=marker.parent.parent/'out/boltz_results_yaml/predictions'/name/f'affinity_{name}.json'
            target=Path(structures[name]['result']['prediction']['pdb']).parent/source.name
            shutil.copy2(source,target)
            pred=self.science.parse_prediction(unit/'out',name);self.science.rank_score(pred,'ligand_plddt+pbind')
            self.journal.load(unit/'completed.json',structures[name]['input'])
            values=dict(structures[name]['result']['prediction'],pbind=pred.pbind)
            self.journal.save(unit/'affinity_completed.json',pending[name],dict(prediction=values,timing=event['timing']),[target])
            result[name]=SimpleNamespace(**values)
        for name in list(pending):
            for marker in sorted((directory/'_batches').glob(f'affinity-*/items/{name}.json')):
                if json.loads((marker.parent.parent/'batch.json').read_text())['specifications'].get(name)==pending[name]:
                    commit(marker);del pending[name];break
        self._execute(directory,pending,args,'affinity',True,commit)
        return {name:result[name] for name in predictions}
