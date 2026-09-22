"""PSICHIC adapter with batched requests and per-candidate durable receipts."""
import csv,json,os,subprocess,uuid
from pathlib import Path
from runtime import ResidentClient,atomic,digest
import psichic_contract as contract

class PsichicClient(ResidentClient):
    def __init__(self,root,output,scripts,seed):
        self.queue=Path(output)/'sessions'/('psichic-'+uuid.uuid4().hex);self.queue.mkdir(parents=True)
        self.log=self.queue/'worker.log';self.config=self.queue/'config.json'
        atomic(self.config,dict(root=str(root),output=str(output),queue=str(self.queue),seed=seed,owner_pid=os.getpid()))
        self.stream=self.log.open('w')
        env=dict(os.environ,PYTORCH_ENABLE_MPS_FALLBACK='0',PYTHONNOUSERSITE='1',PYTHONDONTWRITEBYTECODE='1',OMP_NUM_THREADS='4',MKL_NUM_THREADS='4',OPENBLAS_NUM_THREADS='4',VECLIB_MAXIMUM_THREADS='4')
        for key in ('PYTHONPATH','PYTHONHOME','PYTORCH_MPS_FAST_MATH','PYTORCH_MPS_PREFER_METAL'):env.pop(key,None)
        self.process=subprocess.Popen([str(contract.installation(root)/'python/bin/python3'),str(Path(scripts)/'nise/psichic_worker.py'),'--config',str(self.config)],env=env,stdout=self.stream,stderr=subprocess.STDOUT)
        try:
            self.ready=self.wait(self.queue/'ready.json')
            if self.ready.get('protocol')!=contract.PROTOCOL or self.ready.get('pid')!=self.process.pid or self.ready.get('config_sha256')!=digest(self.config) or self.ready.get('fallback')!=0:raise RuntimeError('Invalid PSICHIC readiness receipt')
        except BaseException:self.close();raise

    def score_many(self,items,smiles):
        identifier=uuid.uuid4().hex;path=self.queue/'requests'/('request_'+identifier+'.json')
        atomic(path,dict(request_id=identifier,items=items,smiles=smiles));reply=self.wait(self.queue/'responses'/path.name)
        if not reply.get('ok') or reply.get('request_id')!=identifier or reply.get('input_sha256')!=digest(path):raise RuntimeError('PSICHIC screening failed: '+str(reply.get('error','invalid receipt')))
        results=reply['results']
        if len(results)!=len(items):raise RuntimeError('Incomplete PSICHIC batch')
        for item,result in zip(items,results):
            if result.get('protocol')!=contract.PROTOCOL or result.get('sequence')!=item['sequence'] or result.get('smiles')!=smiles:raise RuntimeError('PSICHIC execution receipt mismatch')
            contract.validate_scores(result['scores'])
        return results

    def score(self,sequence,smiles,directory):return self.score_many([dict(sequence=sequence,directory=str(directory))],smiles)[0]

def score_candidates(sequences,smiles,directory,journal,worker_factory,root,seed):
    directory=Path(directory);scores={};pending=[];worker=None
    package_digest=digest(contract.installation(root)/'runtime.json')
    for name,sequence in sequences.items():
        contract.validate_sequence(sequence);unit=directory/name
        spec=dict(sequence=sequence,smiles=smiles,seed=seed,protocol=contract.PROTOCOL,installation_sha256=package_digest)
        saved=journal.load(unit/'completed.json',spec)
        if saved is None:pending.append((name,sequence,unit,spec))
        else:scores[name]=contract.validate_scores(saved['scores'])
    for start in range(0,len(pending),64):
        chunk=pending[start:start+64]
        if worker is None:worker=worker_factory()
        results=worker.score_many([dict(sequence=s,directory=str(u)) for n,s,u,spec in chunk],smiles)
        for (name,sequence,unit,spec),saved in zip(chunk,results):
            scores[name]=contract.validate_scores(saved['scores']);journal.save(unit/'completed.json',spec,saved,[unit/'affinity.json'])
    return scores

def screen(backend,sequences,smiles,directory,*,owners=None,per_lineage=None,total=None,allow_empty=False):
    from screening_registry import select
    directory=Path(directory).with_name('psichic')
    def worker():
        if backend.nesso_worker is None:backend.nesso_worker=PsichicClient(backend.root,backend.output,backend.scripts,backend.settings['seed'])
        return backend.nesso_worker
    try:
        scores=score_candidates(sequences,smiles,directory,backend.journal,worker,backend.root,backend.settings['seed'])
        count=backend.settings['nesso_top_k'] if owners is None else per_lineage
        chosen=select(sequences,scores,count,'psichic',owners,total)
        spec=dict(engine='psichic',sequences=sequences,scores=scores,top_k=count,owners=owners,total=total,ranking=contract.RANKING_POLICY)
        receipt=directory/'selection.json';prior=backend.journal.load(receipt,spec)
        if prior is None:backend.journal.save(receipt,spec,chosen,[directory/n/'completed.json' for n in sequences])
        elif prior!=chosen:raise RuntimeError('PSICHIC saved selection mismatch')
        for name,v in scores.items():backend.nesso_scores[name]=dict(v,engine='psichic',screening_score=contract.placement_score(v)['score'],ranking_policy=contract.RANKING_POLICY)
        write_report(backend.output)
        return {n:sequences[n] for n in chosen}
    finally:
        if backend.settings['scheduler']=='cycle-wave' and backend.nesso_worker is not None:backend.nesso_worker.close();backend.nesso_worker=None

def write_report(output):
    output=Path(output);rows=[]
    for p in sorted(output.glob('**/psichic/selection.json')):
        v=json.loads(p.read_text());spec=v['input']
        for name,sequence in spec['sequences'].items():rows.append(dict(candidate=name,sequence=sequence,stage=str(p.parent.relative_to(output)),selected_for_boltz=name in v['result'],**spec['scores'][name]))
    destination=output/'psichic_screening.csv';tmp=destination.with_suffix('.csv.part')
    with tmp.open('w',newline='') as f:
        w=csv.DictWriter(f,fieldnames=['candidate','sequence','stage','selected_for_boltz',*contract.SCALARS,'binding_probability_proxy']);w.writeheader();w.writerows(rows)
    tmp.replace(destination)
