"""Empty installation must not invoke Apple's developer-tools Python shim."""
import os,subprocess,tempfile,unittest
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
class Tests(unittest.TestCase):
 def test_empty_root_detection(self):
  with tempfile.TemporaryDirectory() as tmp:
   r=subprocess.run(['/bin/bash',str(ROOT/'Sources/iProteinStudio/Resources/pipeline/setup_pipeline.sh'),'--detect'],env=dict(os.environ,NANOHUNTER_ROOT=tmp,PATH='/usr/bin:/bin'),text=True,capture_output=True)
   self.assertEqual(r.returncode,0,r.stderr);self.assertIn('NHSTATE|psichic|missing',r.stdout);self.assertNotIn('xcode',r.stderr.lower())
if __name__=='__main__':unittest.main()
