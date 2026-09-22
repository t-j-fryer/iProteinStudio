import csv,json,sys,time
from pathlib import Path
cfg=json.loads(Path(sys.argv[1]).read_text());output=Path(cfg['output']);scripts=Path(cfg['scripts']);sys.path.insert(0,str(scripts/'nise'))
from psichic_screen import PsichicClient,score_candidates,screen
from runtime import Journal,atomic
from psichic_contract import SCALARS
rows=list(csv.DictReader(Path(cfg['inputs']).open()));names={str(i):r['Protein'] for i,r in enumerate(rows)};smiles=rows[0]['Ligand'];holder=[]
def factory():
 if not holder:holder.append(PsichicClient(cfg['root'],output,scripts,17))
 return holder[0]
start=time.monotonic()
try:values=score_candidates(names,smiles,output/'scores',Journal(output),factory,cfg['root'],17)
finally:
 for worker in holder:worker.close()
seconds=time.monotonic()-start
# Complete resume must audit checkpoints without loading another model.
def forbidden():raise AssertionError('Completed resume attempted inference')
assert values==score_candidates(names,smiles,output/'scores',Journal(output),forbidden,cfg['root'],17)
reference=list(csv.DictReader(Path(cfg['reference']).open()));byseq={r['Protein']:r for r in reference}
errors={k:max(abs(v[k]-float(byseq[names[n]][k])) for n,v in values.items()) for k in SCALARS}
atomic(output/'audit.json',dict(count=len(values),max_absolute_errors=errors,seconds=seconds,completed_resume_without_inference=True,passed=max(errors.values())<=.001))
assert max(errors.values())<=.001,errors
# Exercise production screening dispatch/lineage caps with the audited scores.
# A second worker is unnecessary: expose the already measured scores through a
# receipt-writing fixture; engine execution itself was real above.
from types import SimpleNamespace
class RecordedWorker:
    def score_many(self,items,ligand):
        answers=[]
        for item in items:
            v=next(v for n,v in values.items() if names[n]==item['sequence'])
            saved=dict(scores=v,sequence=item['sequence'],smiles=ligand,protocol='recorded-integration-fixture')
            atomic(Path(item['directory'])/'affinity.json',saved);answers.append(saved)
        return answers
    def close(self):pass
backend=SimpleNamespace(root=Path(cfg['root']),output=output,scripts=scripts,journal=Journal(output),nesso_worker=RecordedWorker(),nesso_scores={},settings=dict(seed=17,nesso_top_k=2,scheduler='resident',screening_engine='psichic'))
seqs={rows[int(n)]['ID'] if 'ID' in rows[int(n)] else 'c01_t0_n0_s'+n:seq for n,seq in names.items()}
selected=screen(backend,seqs,smiles,output/'selection-check/nesso',owners={n:'lineage' for n in seqs},per_lineage=2,total=2)
assert len(selected)==2 and (output/'psichic_screening.csv').is_file()
assert all(v['engine']=='psichic' for v in backend.nesso_scores.values())
atomic(output/'adapter_audit.json',dict(lineage_shortlist=len(selected),csv=True,no_second_model_load=True))
print(json.dumps(dict(count=len(values),errors=errors,seconds=seconds)),flush=True)
