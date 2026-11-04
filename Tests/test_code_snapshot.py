import json,sys,tempfile,unittest
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1];PIPE=ROOT/'Sources/iProteinStudio/Resources/pipeline'
sys.path[:0]=[str(PIPE/'mcp'),str(PIPE/'scripts')]
from iprotein_mcp import code_snapshot
import runtime_view
class Tests(unittest.TestCase):
 def test_retained_adapter_and_configuration(self):
  with tempfile.TemporaryDirectory() as tmp:
   root=Path(tmp).resolve()/'root';(root/'scripts').mkdir(parents=True)
   script=root/'scripts/tool.py';script.write_text('old adapter')
   spec=code_snapshot.capture(root,root/'agent/code')
   script.write_text('new adapter')
   view=runtime_view.build(root,root/'agent/job/view',{},spec)
   self.assertEqual((view/'scripts/tool.py').read_text(),'old adapter')
   config=root/'request.json';original=dict(root=str(root),nested=[str(root/'rfd3'),str(root/'scripts/tool.py'),str(root/'models/boltz2')],output=str(root/'projects/output'))
   config.write_text(json.dumps(original))
   command=runtime_view.bind_configs(['python','--config',str(config)],root,view,root/'bound')
   bound=json.loads(Path(command[-1]).read_text())
   self.assertEqual(bound['root'],str(view));self.assertEqual(bound['nested'][0],str(view/'rfd3'));self.assertEqual(bound['nested'][2],str(view/'models/boltz2'))
   self.assertEqual(bound['output'],original['output']);self.assertEqual(json.loads(config.read_text()),original)
   code_snapshot.verify(spec)
   (Path(spec['path'])/'scripts/tool.py').write_text('tampered')
   with self.assertRaisesRegex(Exception,'Retained adapter changed'):code_snapshot.verify(spec)
 def test_explicit_pipeline_survives_stale_installed_scripts(self):
  with tempfile.TemporaryDirectory() as tmp:
   base=Path(tmp).resolve();root=base/'installed';pipeline=base/'bundled'
   for path,text in [(root/'scripts/tool.py','old'),(pipeline/'scripts/tool.py','new'),(pipeline/'mcp/server.py','bridge')]:
    path.parent.mkdir(parents=True,exist_ok=True);path.write_text(text)
   spec=code_snapshot.capture(root,base/'code',pipeline=pipeline)
   view=runtime_view.build(root,base/'view',{},spec)
   command=runtime_view.rewrite([str(root/'scripts/tool.py')],root,view)
   self.assertEqual(Path(command[0]).read_text(),'new')
   original=dict(path=str(pipeline/'scripts/tool.py'),sha256=code_snapshot.file_digest(pipeline/'scripts/tool.py'))
   frozen=code_snapshot.provenance(pipeline,spec,[original])[0]
   self.assertEqual(Path(frozen['path']).read_text(),'new')
   self.assertEqual((root/'scripts/tool.py').read_text(),'old')
 def test_shipped_sibling_helpers_are_retained(self):
  with tempfile.TemporaryDirectory() as tmp:
   root=Path(tmp).resolve();pipeline=root/'resources/pipeline'
   (pipeline/'scripts').mkdir(parents=True);(pipeline/'mcp').mkdir()
   helper=pipeline.parent/'rfd3/ligand_intelligence.py';helper.parent.mkdir();helper.write_text('new bundled helper')
   old=root/'installed/rfd3_scripts/ligand_intelligence.py';old.parent.mkdir(parents=True);old.write_text('old installed helper')
   spec=code_snapshot.capture(root/'installed',root/'code',pipeline=pipeline)
   frozen=Path(spec['path'])/'rfd3_scripts/ligand_intelligence.py'
   self.assertEqual(frozen.read_text(),'new bundled helper')
   helper.write_text('later bundle')
   self.assertEqual(frozen.read_text(),'new bundled helper')
 def test_unrelated_prefix_unchanged(self):
  self.assertEqual(runtime_view.rewrite(['/tmp/root/rfd3-other/x'],'/tmp/root','/view'),['/tmp/root/rfd3-other/x'])
if __name__=='__main__':unittest.main()
