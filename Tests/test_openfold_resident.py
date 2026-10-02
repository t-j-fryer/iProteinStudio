"""OpenFold adapter transactions without loading a learned model."""
import json,sys,tempfile,types,unittest
from pathlib import Path
from unittest.mock import patch
SCRIPTS=Path(__file__).resolve().parents[1]/'Sources/iProteinStudio/Resources/pipeline/scripts'
sys.path.insert(0,str(SCRIPTS))
from openfold_session import OpenFoldSession

class OpenFoldReceipts(unittest.TestCase):
 def setUp(self):
  self.temp=tempfile.TemporaryDirectory();self.addCleanup(self.temp.cleanup);self.root=Path(self.temp.name)
  self.source=self.root/'input';self.source.mkdir();self.output=self.root/'output'
  for name in ('a','b'):(self.source/(name+'.yaml')).write_text('version: 1\nsequences:\n- protein:\n    id: A\n    sequence: ACD\n    msa: empty\n')
  self.session=OpenFoldSession.__new__(OpenFoldSession);s=self.session
  s.work=self.root/'worker';s.work.mkdir();s.identity={'fixture':'model1'};s.settings=dict(msa_depth=128,recycles=3,diffusion_steps=25);s.seeds=[42,43];s.samples=2
  s.torch=types.SimpleNamespace(manual_seed=lambda _:None,mps=types.SimpleNamespace(synchronize=lambda:None))
  self.calls=0;self.fail=False
  def run(payload):
   self.calls+=1
   if self.fail and self.calls==2:raise RuntimeError('interrupted')
   name=next(iter(payload['queries']))
   for seed in s.seeds:
    d=s.work/'predictions'/name/f'seed_{seed}';d.mkdir(parents=True)
    for sample in range(s.samples):
     (d/f'{name}_{sample}_model.cif').write_text('fixture finite coordinates')
     (d/f'{name}_{sample}_confidences_aggregated.json').write_text('{"iptm":0.5}')
  s.runner=types.SimpleNamespace(run=run)
  module=types.ModuleType('inference_query_format');module.InferenceQuerySet=types.SimpleNamespace(from_json=lambda p:json.loads(p.read_text()))
  self.patch=patch.dict(sys.modules,{'openfold3.projects.of3_all_atom.config.inference_query_format':module});self.patch.start();self.addCleanup(self.patch.stop)
  self.geom=patch('validate_prediction_geometry.inspect_geometry',return_value={'errors':[]});self.geom.start();self.addCleanup(self.geom.stop)
 def test_all_seeds_samples_and_resume(self):
  self.session.predict(self.source,self.output,2);self.assertEqual(self.calls,2)
  self.session.predict(self.source,self.output,2);self.assertEqual(self.calls,2)
  for name in ('a','b'):
   saved=json.loads((self.output/name/'openfold_complete.json').read_text());self.assertEqual(len(saved['files']),10)
  (self.output/'a/pred_min/model_0.cif').unlink()
  with self.assertRaisesRegex(ValueError,'artifacts changed'):self.session.predict(self.source,self.output,2)
 def test_interruption_reuses_only_completed_input(self):
  self.fail=True
  with self.assertRaisesRegex(RuntimeError,'interrupted'):self.session.predict(self.source,self.output,2)
  self.fail=False;self.session.predict(self.source,self.output,2);self.assertEqual(self.calls,3)
 def test_changed_input_and_settings_rejected(self):
  self.session.predict(self.source,self.output,2)
  self.session.identity={'fixture':'model2'}
  with self.assertRaisesRegex(ValueError,'settings changed'):self.session.predict(self.source,self.output,2)
 def test_live_records_keep_original_input_names(self):
  with patch.dict('os.environ',{'IPROTEINSTUDIO_LIVE_RESULTS_ROOT':str(self.root)}):
   self.session.predict(self.source,self.output,2)
  events=[json.loads(p.read_text()) for p in (self.root/'.studio_live_results').glob('*.json')]
  self.assertEqual(len(events),4)
  self.assertEqual({r['job'] for r in events},{'a','b'})
  self.assertTrue(all(len(r['artifacts'])==2 for r in events))
 def test_cardinality_rejected_before_inference(self):
  with self.assertRaisesRegex(ValueError,'cardinality'):self.session.predict(self.source,self.output,3)
  self.assertEqual(self.calls,0)

if __name__=='__main__':unittest.main()
