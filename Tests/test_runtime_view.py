import json,os,sys,tempfile,unittest
from pathlib import Path
from unittest.mock import patch
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'Sources/iProteinStudio/Resources/pipeline/scripts'))
import runtime_view
class Tests(unittest.TestCase):
 def test_nested_views_keep_independent_metadata(self):
  with tempfile.TemporaryDirectory() as tmp:
   root=Path(tmp).resolve()/'root';root.mkdir()
   (root/'models').mkdir();(root/'models/test.pt').write_bytes(b'weights')
   package=root/'components/tool';package.mkdir(parents=True)
   registry={'tool':dict(component='tool',model_paths=['models/test.pt'],mappings={})}
   with patch.object(runtime_view,'engines',return_value=registry):
    parent=runtime_view.build(root,root/'parent',{})
    initial={n:(parent/n).read_bytes() for n in ('assets.json','view.json')}
    bound={'tool':dict(path=str(package),manifest_sha256='fixture')}
    child=runtime_view.build(parent,root/'child',bound)
    child_initial={n:(child/n).read_bytes() for n in initial}
    sibling=runtime_view.build(parent,root/'sibling',{})
    for name,data in initial.items():
     self.assertEqual((parent/name).read_bytes(),data)
     self.assertFalse((child/name).is_symlink())
     self.assertFalse((sibling/name).is_symlink())
     self.assertEqual((child/name).read_bytes(),child_initial[name])
    runtime_view.build(parent,child,bound)
    runtime_view.build(parent,sibling,{})
    (child/'models/test.pt').write_bytes(b'tampered')
    with self.assertRaisesRegex(ValueError,'Retained model data changed'):
     runtime_view.build(parent,child,bound)

 def test_binding_preserves_paths_and_source_local_assets(self):
  with tempfile.TemporaryDirectory() as tmp:
   root=Path(tmp).resolve()/'root';source=root/'src/Tool';source.mkdir(parents=True)
   (root/'models/tool').mkdir(parents=True);(root/'models/tool/model.pt').write_bytes(b'model');
   (source/'weight.pt').write_bytes(b'old-weight');(source/'code.py').write_text('old-code')
   package=root/'components/tool/versions/v1';(package/'python/bin').mkdir(parents=True);(package/'source').mkdir()
   (package/'source/code.py').write_text('portable-code');(package/'python/bin/python').write_text('fixture')
   view=root/'agent/job/runtime-view';bound={'tool':dict(path=str(package),manifest_sha256='fixture')}
   with patch.object(runtime_view,'engines',return_value={'tool':dict(component='tool',model_paths=['models/tool'],mappings={'venvs/Tool':'python','src/Tool':'source'})}):runtime_view.build(root,view,bound)
   self.assertEqual((view/'models/tool/model.pt').read_bytes(),b'model')
   (root/'models/tool/model.pt').write_bytes(b'changed-model')
   self.assertEqual((view/'models/tool/model.pt').read_bytes(),b'model')
   self.assertEqual((view/'src/Tool/code.py').read_text(),'portable-code')
   (source/'weight.pt').write_bytes(b'changed')
   self.assertEqual((view/'src/Tool/weight.pt').read_bytes(),b'old-weight')
   self.assertEqual((view/'venvs/Tool/bin/python').resolve(),package/'python/bin/python')
   cmd=[str(root/'venvs/Tool/bin/python'),'--root',str(root),str(root/'projects/output.json')]
   rewritten=runtime_view.rewrite(cmd,root,view)
   self.assertEqual(rewritten,[str(view/'venvs/Tool/bin/python'),'--root',str(view),str(root/'projects/output.json')])
if __name__=='__main__':unittest.main()
