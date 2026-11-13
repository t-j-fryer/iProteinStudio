"""Exercise release validation, rollback prevention and retained bridge provenance."""
import json
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import unittest

PIPE = Path(__file__).resolve().parents[1] / 'Sources/iProteinStudio/Resources/pipeline'
sys.path[:0] = [str(PIPE / 'scripts'), str(PIPE / 'mcp')]
import workflow_release as release
from iprotein_mcp import code_snapshot
from iprotein_mcp.common import StudioError, workflow_release


class ReleaseTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.source = self.root / 'source'
        for name in [release.NAME, 'scripts/workflow_release.py', *release.REQUIRED]:
            target = self.source / name
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(PIPE / name, target)
        (self.source / 'mcp').mkdir()

    def test_release_reports_defaults_and_actual_adapter_checksums(self):
        value = workflow_release(self.source)
        self.assertTrue(value['verified'])
        self.assertEqual(value['esmfold2']['trunk_weight_dtype'], 'bfloat16')
        self.assertEqual(value['generation'], 2026111301)
        (self.source / 'scripts/esmfold2_predict.py').write_text('stale adapter')
        with self.assertRaisesRegex(StudioError, 'differs from its release'):
            workflow_release(self.source)
        with self.assertRaisesRegex(StudioError, 'differs from its release'):
            code_snapshot.capture(self.source, self.root / 'objects', pipeline=self.source)

    def test_equal_update_allowed_newer_installed_and_missing_manifest_rejected(self):
        installed = self.root / 'installed'
        shutil.copytree(self.source, installed)
        release.check_update(self.source, installed)
        value = release.read(installed)
        value['generation'] += 1
        (installed / release.NAME).write_text(json.dumps(value))
        with self.assertRaisesRegex(ValueError, 'older workflows'):
            release.check_update(self.source, installed)
        (self.source / release.NAME).unlink()
        with self.assertRaisesRegex(ValueError, 'older workflows'):
            release.check_update(self.source, installed)

    def test_same_generation_conflict_and_missing_verifier_fail(self):
        installed = self.root / 'installed'
        shutil.copytree(self.source, installed)
        value = release.read(installed)
        value['release'] = 'different implementation'
        (installed / release.NAME).write_text(json.dumps(value))
        with self.assertRaisesRegex(ValueError, 'same release generation'):
            release.check_update(self.source, installed)
        (self.source / 'scripts/workflow_release.py').unlink()
        with self.assertRaisesRegex(StudioError, 'verifier is missing'):
            workflow_release(self.source)

    def test_bridge_freezes_release_and_preserves_historical_snapshots(self):
        spec = code_snapshot.capture(self.source, self.root / 'objects', pipeline=self.source)
        self.assertEqual(spec['workflow_release']['generation'], 2026111301)
        frozen = Path(spec['path'])
        self.assertEqual(release.read(frozen), release.read(self.source))
        (self.source / 'scripts/rfd4/metal.py').write_text('later code')
        code_snapshot.verify(spec)
        legacy = self.root / 'legacy'
        (legacy / 'scripts').mkdir(parents=True)
        (legacy / 'mcp').mkdir()
        (legacy / 'scripts/old.py').write_text('old frozen job')
        old = code_snapshot.capture(legacy, self.root / 'objects', pipeline=legacy)
        self.assertNotIn('workflow_release', old)
        code_snapshot.verify(old)

    def test_cli_doctor_reports_the_executable_release(self):
        result = subprocess.run([sys.executable, str(PIPE / 'mcp/studioctl.py'), 'doctor'],
                                capture_output=True, text=True, check=True)
        self.assertEqual(json.loads(result.stdout)['workflow_release']['generation'], 2026111301)


if __name__ == '__main__':
    unittest.main()
