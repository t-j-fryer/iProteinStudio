"""Read-only RFD4 and prediction release acceptance; raw outputs stay immutable."""
import argparse,json,math,sys
from pathlib import Path
p=argparse.ArgumentParser();p.add_argument('output',type=Path);a=p.parse_args();out=a.output.resolve()
prep=json.loads((out/'preparation.json').read_text());code=Path(prep['code_snapshot']['path'])
sys.path[:0]=[str(code/'scripts'),str(code/'rfd3_scripts')]
from rfd4.contract import verify,prediction_budget,selection_metric
from protein_structure import read_protein_atoms
manifest=json.loads((out/'manifest.json').read_text());expected={r['name'] for r in manifest['routes']}
jobs=json.loads((out/('jobs_final.json' if (out/'jobs_final.json').exists() else 'jobs.json')).read_text())
followup=out/'managed-inputs/jobs.json'
if followup.is_file():jobs+=json.loads(followup.read_text())
checks=[]
for job in jobs:
 root=Path(job['output']);result=dict(name=job['name'],job_id=job['job_id'],code_sha256=job.get('qualified_code_sha256',prep['code_snapshot']['sha256']),passed=False)
 try:
  state=json.loads((Path.home()/'.iproteinstudio/agent/jobs'/job['job_id']/'state.json').read_text())
  assert state['status']=='completed','Managed job is not completed'
  assert (root/'completed.json').is_file(),'Not completed'
  verify(root/'completed.json')
  cfg=json.loads((root/'settings.json').read_text());rows=json.loads((root/'results.json').read_text())
  native_only = cfg['search']=='native' and not cfg['assess_native'] and not cfg['native_search']
  if native_only:
   assert len(rows)==cfg['count']==1
   assert len(rows[0]['sequences']['A'])==120 and len(rows[0]['sequences']['B'])==164
   assert rows[0]['schedule_steps']==60 and sum(rows[0]['model_recycle_depths'])==180
   assert rows[0]['optimized']==cfg['optimized_kernels']
   assert not (root/'qualification').exists(), 'Unexpected automatic reference inference'
   result.update(passed=True,predictions=0,generated=1,receipt=str(root/'completed.json'))
   checks.append(result);continue
  assert len(rows)==prediction_budget(cfg),'Incomplete prediction count'
  objective=selection_metric(cfg)
  for row in rows:
   assert row['selection_metric']==objective
   assert isinstance(row['score'],(float,int)) and math.isfinite(row['score'])
   atoms=read_protein_atoms(row['structure']);assert atoms
   assert all(math.isfinite(v) for atom in atoms for v in (atom.x,atom.y,atom.z))
   if cfg['task']=='ligand':
    assert len(row['sequence'])==cfg['length']
    if cfg['predictor']!='boltz':assert not list(root.rglob('affinity_completed.json')),'Unexpected affinity call'
   if cfg['task']=='nanobody':assert row['scaffold_id'] in cfg['scaffold_weights']
  indexed={row['id']:row for row in rows}
  for path in (root/'decisions').glob('*/*.json'):
   decision=json.loads(path.read_text());assert decision['metric']==objective
   selected=[indexed[key]['score'] for key in decision['selected']]
   excluded=[indexed[key]['score'] for key in decision['candidates'] if key not in decision['selected']]
   assert selected and (not excluded or min(selected)>=max(excluded)),'Selected inferior objective'
  if cfg.get('scaffold_weights'):
   assert {r['scaffold_id'] for r in rows}==set(cfg['scaffold_weights'])
   assert len(json.loads((root/'scaffold_inputs.json').read_text()))==2
  if cfg.get('ligand_conformers'):
   authored=json.loads((root/'ligand_inputs.json').read_text());assert len(authored)==2
   molecules=[json.loads((Path(path).parent/'molecule.json').read_text()) for lengths in authored.values() for path in lengths.values()]
   assert len({m['conformer_source_sha256'] for m in molecules})==2
   for lengths in authored.values():
    for path in lengths.values():
     audited=json.loads((Path(path).parent/'feature_audit.json').read_text());assert audited['passed']
     assert {r['selection_atom'] for r in audited['ligand_conditions']}==set(cfg['ligand_atom_conditions'])
  if cfg.get('ligand_atom_conditions'):
   feature=json.loads((root/'feature_audit.json').read_text());assert feature['passed']
   assert {r['selection_atom'] for r in feature['ligand_conditions']}==set(cfg['ligand_atom_conditions'])
  result.update(passed=True,predictions=len(rows),objective=objective,receipt=str(root/'completed.json'))
 except Exception as exc:result['error']=str(exc)
 checks.append(result)
report=dict(passed={j['name'] for j in jobs}==expected and len(jobs)==len(expected) and all(c['passed'] for c in checks),checks=checks,scope='Bounded technical integration, not efficacy or performance',initial_code_sha256=prep['code_snapshot']['sha256'])

# The only explicit duplicate generation is this declared paired developer test.
import numpy as np
paired={j['name']:Path(j['output']) for j in jobs if j['name'] in ('optimized-t4','standard-t4')}
try:
 assert len(paired)==2
 a=json.loads((paired['standard-t4']/'generated.json').read_text())[0]
 b=json.loads((paired['optimized-t4']/'generated.json').read_text())[0]
 assert a['seed']==b['seed'] and a['sequences']==b['sequences']
 with np.load(a['tensors']) as x,np.load(b['tensors']) as y:
  assert set(x.files)==set(y.files) and all(np.isfinite(x[k]).all() and np.array_equal(x[k],y[k]) for k in x.files)
 report['kernel_parity']=dict(passed=True,seed=a['seed'],exact=True)
except Exception as exc:report['kernel_parity']=dict(passed=False,error=str(exc));report['passed']=False

predictions=[]
try:
 ledger=json.loads((out/'prediction_jobs.json').read_text())
 assert {j['name'] for j in ledger}=={'t4-template-off','t4-template-on'} and len(ledger)==2
 for job in ledger:
  state=json.loads((Path.home()/'.iproteinstudio/agent/jobs'/job['job_id']/'state.json').read_text());assert state['status']=='completed'
  root=Path(job['output']);summary=json.loads((root/'run_summary.json').read_text())
  assert summary['failures']==0 and summary['jobs']==summary['results']==1
  enabled=job['name'].endswith('-on');assert bool(summary['template'])==enabled
  config=json.loads((root/'prediction_config.json').read_text());sequence=config['jobs'][0]['chains'][0]['sequence']
  assert len(sequence)==164 and config['jobs'][0]['chains'][0]['msa']=='empty'
  structures=list(root.glob('predictions/**/'+job['name']+'_model_0.cif'))
  if not structures:structures=list(root.glob('**/'+job['name']+'_model_0.cif'))
  assert len(structures)==1, 'Unexpected prediction cardinality: '+str(structures)
  atoms=read_protein_atoms(structures[0]);assert atoms and all(math.isfinite(v) for atom in atoms for v in (atom.x,atom.y,atom.z))
  from rfd4.search_engine import sequences
  assert sequences(structures[0])=={'A':sequence}
  confidence=list(root.glob('**/confidence_'+job['name']+'_model_0.json'));assert len(confidence)==1
  metrics=json.loads(confidence[0].read_text());assert math.isfinite(metrics['complex_plddt'])
  predictions.append(dict(name=job['name'],passed=True,template_enabled=enabled,structure=str(structures[0]),structure_sha256=__import__('hashlib').sha256(structures[0].read_bytes()).hexdigest(),confidence=str(confidence[0])))
except Exception as exc:report['passed']=False;report['prediction_error']=str(exc)
report['prediction_checks']=predictions
(out/'audit.json').write_text(json.dumps(report,indent=2)+'\n');print(json.dumps(report,indent=2))
raise SystemExit(0 if report['passed'] else 1)
