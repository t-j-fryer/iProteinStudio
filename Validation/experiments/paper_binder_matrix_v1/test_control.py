"""CPU-only recovery and asset-integrity checks; no scientific predictions."""
import json
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

from assets import verify
from common import sha

HERE = Path(__file__).resolve().parent


class CampaignControlTests(unittest.TestCase):
    def test_bounded_retry_resume_and_tamper_rejection(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            for name in ('run.py', 'common.py'):
                shutil.copy2(HERE / name, root / name)
            (root / 'worker.py').write_text('''
import json, sys
from pathlib import Path
from common import save, sha
out = Path(sys.argv[3]); out.mkdir(exist_ok=True)
counter = out / 'counter'
n = int(counter.read_text()) + 1 if counter.exists() else 1
counter.write_text(str(n))
save(out / 'active.json', dict(status='running'))
print('UNIT_START test', flush=True)
if n == 1: raise SystemExit(9)
unit = out / 'unit'; unit.mkdir()
measurement = unit / 'measurement.json'
save(measurement, dict(test=True))
save(unit / 'complete.json', dict(files={str(measurement): sha(measurement)}))
save(out / 'completed.json', dict(outputs=[str(measurement)]))
save(out / 'active.json', dict(status='completed'))
print('UNIT test', flush=True)
''')
            (root / 'campaign_report.py').write_text("print('CPU test report stub')\n")
            config = root / 'config.json'
            config.write_text(json.dumps(dict(output=str(root), phase='campaign', arms=[['test', 'baseline']],
                                             analysis_python=sys.executable, engines={'test': {'python': sys.executable}})))
            command = [sys.executable, str(root / 'run.py'), str(config)]
            first = subprocess.run(command, capture_output=True, text=True)
            self.assertEqual(first.returncode, 0, first.stderr)
            progress = json.loads((root / 'progress.json').read_text())['results'][0]
            self.assertEqual([a['exit_code'] for a in progress['attempts']], [9, 0])
            self.assertEqual(len(list(root.glob('test__baseline__*.log'))), 2)
            self.assertIn('UNIT_START test', first.stdout)
            second = subprocess.run(command, capture_output=True, text=True)
            self.assertEqual(second.returncode, 0, second.stderr)
            self.assertEqual((root / 'test__baseline/counter').read_text(), '2')
            (root / 'test__baseline/unit/measurement.json').write_text('{}')
            corrupted = subprocess.run(command, capture_output=True, text=True)
            self.assertNotEqual(corrupted.returncode, 0)
            self.assertEqual((root / 'test__baseline/counter').read_text(), '2')

    def test_asset_guard_rejects_same_size_content_change(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            asset = root / 'asset'
            asset.write_bytes(b'original')
            records = {'asset': dict(size=8, sha256=sha(asset))}
            verify(root, records)
            asset.write_bytes(b'mutated!')
            with self.assertRaises(AssertionError):
                verify(root, records)


if __name__ == '__main__':
    unittest.main()
