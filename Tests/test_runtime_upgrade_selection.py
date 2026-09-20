"""Exercise real installer version selection without downloads or GPU imports."""
import json,os,subprocess,tempfile,unittest
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
SETUP=ROOT/'Sources/iProteinStudio/Resources/pipeline/setup_pipeline.sh'
class RuntimeUpgradeSelection(unittest.TestCase):
 def exercise(self,installed,requested):
  with tempfile.TemporaryDirectory() as temp:
   root=Path(temp);old=root/'old';(old/'bin').mkdir(parents=True)
   interpreter=old/'bin/python';interpreter.write_text('#!/bin/sh\nexit 0\n');interpreter.chmod(0o755)
   (old/'transaction.json').write_text(json.dumps(dict(state='ready',component='boltz',version=installed)))
   final=root/'current';final.symlink_to(old)
   (root/'receipts').mkdir()
   source=SETUP.read_text();function=source[source.index('begin_versioned_venv() {'):source.index('\ncommit_versioned_venv() {')]
   script='set -euo pipefail\n'+function+'\nfail() { echo "$1" >&2; exit 1; }\nbegin_versioned_venv boltz "$1" "$2" "$3"\nprintf "REUSED=%s\\n" "$TRANSACTION_REUSED"\n'
   env=dict(os.environ,NANOHUNTER_ROOT=str(root),RECEIPTS_DIR=str(root/'receipts'),RUNTIME_TRANSACTION=str(ROOT/'Sources/iProteinStudio/Resources/pipeline/scripts/runtime_transaction.py'))
   result=subprocess.run(['bash','-c',script,'test',requested,str(final),str(interpreter)],env=env,text=True,capture_output=True)
   self.assertEqual(result.returncode,0,result.stderr)
   self.assertEqual(final.resolve(),old.resolve())
   return result.stdout
 def test_new_version_must_not_reuse_committed_old_runtime(self):
  self.assertIn('REUSED=0',self.exercise('torch2.13','torch2.14'))
 def test_same_version_can_finish_interrupted_receipt(self):
  self.assertIn('REUSED=1',self.exercise('torch2.14','torch2.14'))
if __name__=='__main__':unittest.main()
