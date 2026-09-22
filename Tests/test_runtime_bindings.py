import importlib.util,json,os,sys,tempfile,unittest
from pathlib import Path
from unittest.mock import patch
ROOT=Path(__file__).resolve().parents[1];PIPE=ROOT/'Sources/iProteinStudio/Resources/pipeline'
sys.path.insert(0,str(PIPE/'mcp'));sys.path.insert(0,str(PIPE/'scripts'))
from iprotein_mcp.runtime_bindings import capture,retain,verify,environment
from engine_registry import pinned_installation
class Tests(unittest.TestCase):
 def test_switch_keeps_exact_runtime_and_tamper_fails(self):
  with tempfile.TemporaryDirectory() as tmp:
   root=Path(tmp).resolve();component=root/'components/psichic';old=component/'versions/old';new=component/'versions/new'
   for base in (old,new):
    base.mkdir(parents=True);(base/'runtime.json').write_text(json.dumps(dict(schema_version=1,engine='psichic',contains_weights=False,files={},version=base.name)))
   pointer=component/'current';pointer.symlink_to(old)
   self.assertEqual(capture(root,provenance=[],normalized={'engine':'other'}),{})
   self.assertIn('psichic',capture(root,provenance=[{'path':str(old/'runtime.json')}]))
   bound=capture(root);retain(dict(id='plan-fixture',sha256='test',runtime_bindings=bound),root)
   pointer.unlink();pointer.symlink_to(new)
   with patch.dict(os.environ,environment(bound)):
    self.assertEqual(pinned_installation(root,'psichic',pointer),old)
   verify(bound);self.assertTrue((root/'runtime_pins/psichic/plan-fixture.json').exists())
   (old/'runtime.json').write_text('{}')
   with self.assertRaisesRegex(RuntimeError,'missing or changed'):verify(bound)
 def test_sequence_model_alias_is_retained(self):
  with tempfile.TemporaryDirectory() as tmp:
   root=Path(tmp).resolve();base=root/'components/mpnn/versions/one';base.mkdir(parents=True)
   (base/'runtime.json').write_text(json.dumps(dict(schema_version=1,engine='mpnn',contains_weights=False,files={})))
   (root/'components/mpnn/current').symlink_to(base)
   for name in ('solublempnn','proteinmpnn','ligandmpnn','abmpnn','soluble_mpnn'):
    self.assertIn('mpnn',capture(root,provenance=[],normalized={'sequence_model':name}))
if __name__=='__main__':unittest.main()
