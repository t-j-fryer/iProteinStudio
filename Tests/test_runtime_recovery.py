"""Real hard exits at each activation boundary; no mocks of filesystem semantics."""
import importlib.util,subprocess,sys,tempfile,unittest
from pathlib import Path
SCRIPT=Path(__file__).resolve().parents[1]/'Sources/iProteinStudio/Resources/pipeline/scripts/runtime_transaction.py'
spec=importlib.util.spec_from_file_location('transaction',SCRIPT);tx=importlib.util.module_from_spec(spec);spec.loader.exec_module(tx)
class RecoveryTests(unittest.TestCase):
 def test_crashes_and_rollback(self):
  for phase in ['final_renamed','old_moved_0','new_link_0','old_moved_1','new_link_1','current_switched','success']:
   with self.subTest(phase=phase),tempfile.TemporaryDirectory() as tmp:
    root=Path(tmp).resolve();a=root/'venvs/engine';b=root/'src/engine'
    for path in (a,b):path.mkdir(parents=True);(path/'identity').write_text('old')
    stage=tx.prepare(root,'engine','v2')
    for name in ('python','source'):(stage/name).mkdir();(stage/name/'identity').write_text('new')
    script="import importlib.util,os,sys; from pathlib import Path; s=importlib.util.spec_from_file_location('tx',sys.argv[1]); t=importlib.util.module_from_spec(s);s.loader.exec_module(t);t._phase=lambda name:os._exit(75) if name==sys.argv[2] else None;t.commit(Path(sys.argv[3]),'engine','v2',Path(sys.argv[4]),sys.argv[5:])"
    result=subprocess.run([sys.executable,'-c',script,str(SCRIPT),phase,str(root),str(stage),str(a)+'=python',str(b)+'=source'])
    if phase=='success':self.assertEqual(result.returncode,0);self.assertEqual((a/'identity').read_text(),'new');tx.rollback(root,'engine')
    else:self.assertEqual(result.returncode,75);tx.recover(root,'engine')
    tx.recover(root,'engine')
    for path in (a,b):self.assertFalse(path.is_symlink());self.assertEqual((path/'identity').read_text(),'old')
    self.assertFalse((root/'components/engine/current').exists())
 def test_missing_legacy_restores_absence(self):
  with tempfile.TemporaryDirectory() as tmp:
   root=Path(tmp).resolve();stage=tx.prepare(root,'engine','v1');(stage/'python').mkdir()
   tx.commit(root,'engine','v1',stage,[str(root/'venv')+'=python']);tx.rollback(root,'engine')
   self.assertFalse((root/'venv').is_symlink())
if __name__=='__main__':unittest.main()
