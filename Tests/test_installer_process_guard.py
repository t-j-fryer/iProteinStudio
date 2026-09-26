"""Execute the installer's process guard with real owned, inert child processes."""
import os,subprocess,tempfile,unittest
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
source=(ROOT/'Sources/iProteinStudio/Resources/pipeline/setup_pipeline.sh').read_text()
function=source[source.index('assert_runtime_idle() {'):source.index('\ncheck_sha256() {')]
class InstallerProcessGuard(unittest.TestCase):
    def exercise(self,relative):
        with tempfile.TemporaryDirectory(prefix='studio guard [literal] ') as td:
            root=Path(td);exe=root/relative;exe.parent.mkdir(parents=True);exe.symlink_to('/bin/sleep')
            worker=subprocess.Popen([str(exe),'30'])
            try:
                result=subprocess.run(['/bin/bash','-c','set -euo pipefail\nfail() { echo "$1"; exit 1; }\n'+function+'\nassert_runtime_idle\necho IDLE\n'],env={**os.environ,'NANOHUNTER_ROOT':str(root)},text=True,capture_output=True)
            finally:worker.terminate();worker.wait(timeout=5)
            return result
    def test_control_python_does_not_block_its_own_install_job(self):
        r=self.exercise('components/control/versions/test/python/bin/python3')
        self.assertEqual(r.returncode,0,r.stdout+r.stderr)
        self.assertIn('IDLE',r.stdout)
    def test_real_engine_paths_and_runtime_views_still_block(self):
        for path in ['components/new-engine/versions/test/python/bin/python3','venvs/engine/bin/python','agent/jobs/job-test/runtime_view/engine/bin/python','agent/runtime_views/test/engine/bin/python']:
            with self.subTest(path=path):
                r=self.exercise(path);self.assertNotEqual(r.returncode,0)
                self.assertIn('using the managed runtime',r.stdout)
if __name__=='__main__':unittest.main()
