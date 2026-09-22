"""Scoring semantics, batch recovery and strict output checks without GPU inference."""
import json,sys,tempfile,unittest,os
from unittest.mock import patch
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'Sources/iProteinStudio/Resources/pipeline/scripts/nise'))
import psichic_contract as contract
from psichic_screen import score_candidates
from screening_registry import select,descriptor
from runtime import Journal,atomic

def scores(p=.6):return dict(predicted_binding_affinity=7.,predicted_nonbinder=1-p,predicted_antagonist=p/2,predicted_agonist=p/2)
class Worker:
 calls=0;fail=False
 def score_many(self,items,smiles):
  type(self).calls+=1
  if self.fail and type(self).calls==2:raise RuntimeError('interrupted')
  saved=[]
  for item in items:
   r=dict(scores=scores(),sequence=item['sequence'],smiles=smiles,protocol=contract.PROTOCOL)
   atomic(Path(item['directory'])/'affinity.json',r);saved.append(r)
  return saved
class Tests(unittest.TestCase):
 def test_scores_and_selection(self):
  self.assertAlmostEqual(contract.placement_score(scores())['score'],.6)
  names={'c001_t001_n001_s001':'ACDE','c001_t001_n002_s001':'ACDF','c001_t002_n001_s001':'ACDG'}
  values={n:scores(.6+i*.1) for i,n in enumerate(names)}
  self.assertEqual(select(names,values,1,'psichic'),[list(names)[2],list(names)[1]])
  self.assertEqual(select(names,values,1,'psichic',{n:'same' for n in names},1),[list(names)[2]])
  self.assertNotIn('entropy_crop_pl',contract.validate_scores(scores()))
  self.assertIn('experimental',descriptor('psichic')['label'])
  with self.assertRaises(ValueError):descriptor('unknown')
 def test_unbound_asset_root_is_not_borrowed(self):
  with patch.dict(os.environ,dict(IPROTEINSTUDIO_RUNTIME_BINDINGS='{}',NANOHUNTER_ROOT='/another-root')):
   self.assertTrue(str(contract.asset_root('/fixture')).startswith('/fixture/models/psichic/'))
 def test_bad_outputs(self):
  for key,value in [('predicted_nonbinder',float('nan')),('predicted_antagonist',-.1),('predicted_agonist',.9),('predicted_binding_affinity',True)]:
   v=scores();v[key]=value
   with self.assertRaises(ValueError):contract.validate_scores(v)
  for s in ('X','A'*701,''):
   with self.assertRaises(ValueError):contract.validate_sequence(s)
 def test_atomic_batches_resume_and_tamper(self):
  with tempfile.TemporaryDirectory() as tmp:
   root=Path(tmp);base=contract.installation(root);base.mkdir(parents=True);(base/'runtime.json').write_text('{}')
   output=root/'campaign';output.mkdir();journal=Journal(output)
   names={f'candidate_{i}':'ACDE' for i in range(65)};worker=Worker();Worker.calls=0;Worker.fail=True
   with self.assertRaisesRegex(RuntimeError,'interrupted'):score_candidates(names,'CCO',output/'scores',journal,lambda:worker,root,17)
   self.assertEqual(len(list(output.rglob('completed.json'))),64)
   Worker.fail=False
   values=score_candidates(names,'CCO',output/'scores',journal,lambda:worker,root,17)
   self.assertEqual(len(values),65);self.assertEqual(Worker.calls,3)
   score_candidates(names,'CCO',output/'scores',journal,lambda:worker,root,17);self.assertEqual(Worker.calls,3)
   (output/'scores/candidate_0/affinity.json').write_text('{}')
   with self.assertRaisesRegex(RuntimeError,'missing or changed'):score_candidates(names,'CCO',output/'scores',journal,lambda:worker,root,17)
if __name__=='__main__':unittest.main()
