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
 def test_unrelated_prefix_unchanged(self):
  self.assertEqual(runtime_view.rewrite(['/tmp/root/rfd3-other/x'],'/tmp/root','/view'),['/tmp/root/rfd3-other/x'])
if __name__=='__main__':unittest.main()
