"""Exercise publication at the real writer boundary, without loading a model."""
import csv
import json
from pathlib import Path
import sys
import tempfile
from types import SimpleNamespace
import unittest

SCRIPTS = Path(__file__).resolve().parents[1] / 'Sources/iProteinStudio/Resources/pipeline/scripts'
sys.path.insert(0, str(SCRIPTS))
# All fixture inputs are JSON (valid YAML). Also run with managed Boltz Python
# to exercise real PyYAML; keep the dependency-free suite usable on clean Macs.
try:
    import yaml
except ImportError:
    sys.modules['yaml'] = SimpleNamespace(safe_load=json.loads)
from live_iterative_results import LiveIterativeResults, boltz_live_writer
from resident_predictor import BoltzSession

PDB = 'ATOM      1  CA  ALA A   1       0.000   0.000   0.000  1.00 80.00           C  \nEND\n'


class LiveResultsTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(); self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.source = self.root / '_cycle_wave/cycle_00/batch_01/inputs'
        self.source.mkdir(parents=True)
        self.names = ['run_001_cycle_00', 'run_002_cycle_00']
        self.paths = []
        for i, name in enumerate(self.names, 1):
            path = self.root / f'run_{i:03}/cycle_00' / (name + '.yaml')
            path.parent.mkdir(parents=True)
            path.write_text(json.dumps({'sequences': [{'protein': {'id': 'A', 'sequence': 'ACDE'}}]}))
            (self.source / path.name).symlink_to(path)
            self.paths.append(path)
        self.output = self.root / '_cycle_wave/cycle_00/batch_01/boltz/predictions'
        self.publisher = LiveIterativeResults(self.source)

    def write(self, name, pdb=PDB):
        leaf = self.output / name; leaf.mkdir(parents=True, exist_ok=True)
        (leaf / (name + '_model_0.pdb')).write_text(pdb)
        (leaf / ('confidence_' + name + '_model_0.json')).write_text(json.dumps({'iptm': .8, 'complex_plddt': .9}))
        return leaf

    def test_first_result_published_before_second_prediction_and_hook_restored(self):
        test = self
        class Writer:
            def __init__(self): self.output_dir = test.output
            def write_on_batch_end(self, trainer, model, prediction, indices, batch, index, loader):
                if prediction['exception']: return
                # No receipt is visible while upstream is still writing files.
                test.assertFalse((test.paths[0].parent / 'live_prediction.csv').exists())
                test.write(batch['record'][0].id)
        main = SimpleNamespace(BoltzWriter=Writer)
        counts = []
        with boltz_live_writer(main, self.publisher, lambda *x: counts.append(x), 2):
            writer = main.BoltzWriter()
            writer.write_on_batch_end(None, None, {'exception': False}, [],
                                      {'record': [SimpleNamespace(id=self.names[0])]}, 0, 0)
            receipt = self.paths[0].parent / 'live_prediction.csv'
            with receipt.open() as stream:
                row = list(csv.DictReader(stream))[0]
            self.assertEqual(row['binder_sequence'], 'ACDE')
            self.assertEqual(row['cycle'], '0')
            self.assertFalse(Path(row['structure_path']).is_absolute())
            self.assertTrue((self.root / row['structure_path']).is_file())
            self.assertFalse((self.paths[1].parent / 'live_prediction.csv').exists())
            self.assertFalse((self.paths[0].parent / 'pred_min').exists())
        self.assertIs(main.BoltzWriter, Writer)
        self.assertEqual(counts, [(1, 2, 0)])

    def test_incomplete_or_unusable_prediction_is_not_published(self):
        leaf = self.output / self.names[0]; leaf.mkdir(parents=True)
        with self.assertRaisesRegex(ValueError, 'Incomplete'): self.publisher.publish(self.names[0], leaf)
        self.write(self.names[0], 'truncated')
        with self.assertRaisesRegex(ValueError, 'Unusable'): self.publisher.publish(self.names[0], leaf)
        self.assertFalse((self.paths[0].parent / 'live_prediction.csv').exists())

    def test_retry_removes_previous_receipt_and_rejects_changed_input(self):
        leaf = self.write(self.names[0]); self.publisher.publish(self.names[0], leaf)
        receipt = self.paths[0].parent / 'live_prediction.csv'
        self.assertTrue(receipt.is_file())
        publisher = LiveIterativeResults(self.source)
        self.assertFalse(receipt.exists())
        self.paths[0].write_text('{}')
        with self.assertRaisesRegex(ValueError, 'changed'): publisher.publish(self.names[0], leaf)

    def test_exception_and_failed_prediction_do_not_leave_hook_or_receipt(self):
        class Writer:
            def write_on_batch_end(self, *args): pass
        main = SimpleNamespace(BoltzWriter=Writer)
        with self.assertRaisesRegex(RuntimeError, 'interrupted'):
            with boltz_live_writer(main, self.publisher, None, 2):
                main.BoltzWriter().write_on_batch_end(None, None, {'exception': True}, [], {}, 0, 0)
                raise RuntimeError('interrupted')
        self.assertIs(main.BoltzWriter, Writer)
        self.assertFalse((self.paths[0].parent / 'live_prediction.csv').exists())

    def test_resident_session_keeps_first_result_when_later_prediction_fails(self):
        test = self
        class Writer:
            def __init__(self): self.output_dir = test.output
            def write_on_batch_end(self, trainer, model, prediction, indices, batch, index, loader):
                test.write(batch['record'][0].id)
        main = SimpleNamespace(BoltzWriter=Writer, filter_inputs_structure=object(), filter_inputs_affinity=object())
        original_filter = main.filter_inputs_affinity
        def predict(**kwargs):
            main.BoltzWriter().write_on_batch_end(None, None, {'exception': False}, [],
                {'record': [SimpleNamespace(id=self.names[0])]}, 0, 0)
            self.assertTrue((self.paths[0].parent / 'live_prediction.csv').is_file())
            raise RuntimeError('second prediction failed')
        main.predict = SimpleNamespace(main=predict)
        # Force capped staging from symlinked cycle inputs. Display receipts must
        # still belong to the original run/cycle, not the prepared YAML directory.
        for path in self.paths:
            alignment = path.parent / 'scaffold.a3m'
            alignment.write_text(''.join(f'>r{i}\nACDE\n' for i in range(130)))
            data = json.loads(path.read_text())
            data['sequences'][0]['protein']['msa'] = 'scaffold.a3m'
            path.write_text(json.dumps(data))
        session = BoltzSession.__new__(BoltzSession)
        session.prediction_settings = dict(msa_depth=128, diffusion_steps=25, recycles=3)
        session.arguments = []; session.config = {}; session.boltz_main = main
        session.publish_iterative_results = True; session.iterative_binder_chain = 'A'
        with self.assertRaisesRegex(RuntimeError, 'second prediction failed'):
            session.predict(self.source, self.output.parent, 2)
        self.assertIs(main.BoltzWriter, Writer)
        self.assertIs(main.filter_inputs_affinity, original_filter)
        self.assertTrue((self.paths[0].parent / 'live_prediction.csv').is_file())
        self.assertFalse((self.paths[1].parent / 'live_prediction.csv').exists())


if __name__ == '__main__': unittest.main()
