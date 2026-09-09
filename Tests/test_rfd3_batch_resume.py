"""Exercise RFdiffusion3's durable batch boundary without model inference."""
import json
from pathlib import Path
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'Sources/iProteinStudio/Resources/rfd3_overlay/scripts'))
from rfd3_resume import BatchState


class BatchResumeTests(unittest.TestCase):
    def test_partial_batch_is_archived_and_committed_seeds_and_files_survive(self):
        with tempfile.TemporaryDirectory() as raw:
            root = Path(raw)
            state = BatchState(root, {'num_designs': 3, 'seed': 42})
            for folder, ext in [('backbones', 'pdb'), ('results', 'json')]:
                (root / folder).mkdir()
                (root / folder / ('design_0001.' + ext)).write_text('completed')
            state.commit(1, 2, [{'seed': 43}])
            (root / 'backbones/design_0002.pdb').write_text('uncommitted')
            restored = BatchState(root, {'num_designs': 3, 'seed': 42})
            self.assertEqual((restored.saved['accepted'], restored.saved['attempted']), (1, 2))
            self.assertEqual(restored.saved['rejected'], [{'seed': 43}])
            self.assertFalse((root / 'backbones/design_0002.pdb').exists())
            self.assertEqual(len(list((root / 'interrupted').rglob('design_0002.pdb'))), 1)
            with self.assertRaisesRegex(RuntimeError, 'inputs changed'):
                BatchState(root, {'num_designs': 3, 'seed': 44})
            (root / 'backbones/design_0001.pdb').write_text('tampered')
            with self.assertRaisesRegex(RuntimeError, 'missing or changed'):
                BatchState(root, {'num_designs': 3, 'seed': 42})

    def test_receipt_must_account_for_every_completed_design(self):
        with tempfile.TemporaryDirectory() as raw:
            root = Path(raw)
            state = BatchState(root, {'num_designs': 1})
            doc = state.saved; doc['accepted'] = 1
            state.path.write_text(json.dumps(doc))
            with self.assertRaisesRegex(RuntimeError, 'completion count'):
                BatchState(root, {'num_designs': 1})


if __name__ == '__main__':
    unittest.main(verbosity=2)
