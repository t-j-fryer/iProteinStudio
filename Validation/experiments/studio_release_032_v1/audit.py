"""Read-only acceptance of the six declared routes; never edits scientific output."""
import argparse,json,math,sys
from pathlib import Path
p=argparse.ArgumentParser();p.add_argument('output',type=Path);a=p.parse_args();out=a.output.resolve()
prep=json.loads((out/'preparation.json').read_text());code=Path(prep['code_snapshot']['path'])
sys.path[:0]=[str(code/'scripts'),str(code/'rfd3_scripts')]
from rfd4.contract import verify,prediction_budget,selection_metric
from protein_structure import read_protein_atoms
manifest=json.loads((out/'manifest.json').read_text());expected={r['name'] for r in manifest['routes']}
jobs=json.loads((out/'jobs.json').read_text())
followup=out/'managed-inputs/jobs.json'
if followup.is_file():jobs+=json.loads(followup.read_text())
checks=[]
for job in jobs:
 root=Path(job['output']);result=dict(name=job['name'],passed=False)
 try:
  assert (root/'completed.json').is_file(),'Not completed'
  verify(root/'completed.json')
  cfg=json.loads((root/'settings.json').read_text());rows=json.loads((root/'results.json').read_text())
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
  if cfg.get('ligand_atom_conditions'):
   feature=json.loads((root/'feature_audit.json').read_text());assert feature['passed']
   assert {r['selection_atom'] for r in feature['ligand_conditions']}==set(cfg['ligand_atom_conditions'])
  result.update(passed=True,predictions=len(rows),objective=objective,receipt=str(root/'completed.json'))
 except Exception as exc:result['error']=str(exc)
 checks.append(result)
report=dict(passed={j['name'] for j in jobs}==expected and all(c['passed'] for c in checks),checks=checks,scope='Bounded technical integration, not efficacy or performance',code_sha256=prep['code_snapshot']['sha256'])
(out/'audit.json').write_text(json.dumps(report,indent=2)+'\n');print(json.dumps(report,indent=2))
raise SystemExit(0 if report['passed'] else 1)
