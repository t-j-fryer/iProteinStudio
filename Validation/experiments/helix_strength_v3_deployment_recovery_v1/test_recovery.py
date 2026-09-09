import copy
import unittest
from unittest.mock import patch
import recover as r


class RecoveryTests(unittest.TestCase):
    def test_reviewed_runtime_passes_and_original_manifest_remains_valid(self):
        self.assertEqual(r.c.prepare()['config'], r.c.CONFIG)

    def test_unreviewed_scope_is_rejected(self):
        original = r.c.read
        def altered(path):
            value = original(path)
            if path == r.RECOVERY / 'amendment.json':
                value = copy.deepcopy(value)
                value['accepted_files']['scripts/boltz_mps.py'] = {}
            return value
        with patch.object(r.c, 'read', side_effect=altered):
            with self.assertRaisesRegex(RuntimeError, 'Unreviewed deployment scope'):
                r.verify_stage()

    def test_predictor_code_drift_still_blocks(self):
        original = r.c.sha
        def altered(path):
            return 'unexpected' if path == r.c.RUNTIME / 'scripts/boltz_mps.py' else original(path)
        with patch.object(r.c, 'sha', side_effect=altered):
            with self.assertRaisesRegex(RuntimeError, 'Runtime provenance changed'):
                r.verify_stage()


if __name__ == '__main__':
    unittest.main()
