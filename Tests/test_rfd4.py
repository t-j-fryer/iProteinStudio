"""Model-free contracts for portable RFD4 input and durable search behavior."""
import importlib.util
import json
from pathlib import Path
import sys
import tempfile
import unittest
import subprocess

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'Sources/iProteinStudio/Resources/pipeline/scripts'))
from rfd4.contract import normalize, prediction_budget, sha, verify, seal
from rfd4.search import execute


class FakeEngine:
    def __init__(self, fail=None): self.calls = []; self.fail = fail
    def evaluate(self, proposal, parent, unit, native=False):
        self.calls.append(proposal['id'])
        if len(self.calls) == self.fail: raise RuntimeError('simulated interruption')
        structure = unit / 'model.cif'
        structure.write_text(proposal['id'])
        # Later branches deliberately score below their parents: parents must
        # not be retained by accidental elitism.
        score = 1 / proposal['cycle'] + int(proposal['id'][-3:]) * .01
        return dict(structure=str(structure), structure_sha256=sha(structure), score=score), [structure]


class SearchTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(); self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        parent = self.root / 'start.cif'; parent.write_text('starting structure')
        self.starts = [dict(family='seed_42', id='seed_42', seed=42, structure=str(parent), structure_sha256=sha(parent))]

    def cfg(self, policy):
        return {'settings': normalize(dict(task='protein', source='unused.cif', target_msa='empty',
            search=policy, cycles=3, proposals=3, beam_width=2))}

    def test_counts_ancestry_and_all_losers_retained(self):
        for policy, count in [('fixed', 3), ('iterative', 3), ('greedy', 9), ('beam', 15)]:
            with self.subTest(policy=policy):
                cfg = self.cfg(policy); output = self.root / policy
                engine = FakeEngine(); rows = execute(cfg, self.starts, engine, output)
                self.assertEqual(len(rows), count)
                self.assertEqual(len(rows), prediction_budget(cfg['settings']))
                self.assertEqual(len(list((output / 'candidates').glob('*/completed.json'))), count)
                self.assertEqual(verify(output / 'search_completed.json')['predictions'], count)
                decisions = sorted((output / 'decisions/seed_42').glob('*.json'))
                for path in decisions:
                    decision = json.loads(path.read_text())
                    self.assertFalse(decision['elitism'])
                    self.assertTrue(set(decision['selected']) <= set(decision['candidates']))
                if policy == 'beam':
                    chosen = json.loads(decisions[0].read_text())['selected']
                    self.assertEqual(chosen, ['seed_42_c001_p002', 'seed_42_c001_p001'])
                    self.assertEqual({r['parent_id'] for r in rows if r['cycle'] == 2}, set(chosen))
                resumed = FakeEngine(); execute(cfg, self.starts, resumed, output)
                self.assertEqual(resumed.calls, [])

    def test_resume_after_interruption_and_tamper_refusal(self):
        cfg = self.cfg('beam'); output = self.root / 'resume'
        with self.assertRaisesRegex(RuntimeError, 'interruption'):
            execute(cfg, self.starts, FakeEngine(fail=5), output)
        second = FakeEngine(); rows = execute(cfg, self.starts, second, output)
        self.assertEqual(len(second.calls), 11)
        Path(rows[0]['structure']).write_text('changed')
        with self.assertRaisesRegex(ValueError, 'artifact changed'):
            execute(cfg, self.starts, FakeEngine(), output)

    def test_request_rejects_wrong_designer_or_incomplete_budget(self):
        for request in [dict(task='protein', source='x', search='beam', target_msa='empty', sequence_model='ligandmpnn'),
                        dict(task='protein', source='x', search='beam', target_msa='empty', proposals=1, beam_width=4),
                        dict(count=True), dict(task='protein', source='x', search='iterative')]:
            with self.assertRaises(ValueError): normalize(request)


class PackagingTests(unittest.TestCase):
    def test_native_oracle_preserves_campaign_relative_receipt_contract(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory); leaf = root / 'predictions/item'; leaf.mkdir(parents=True)
            artifact = leaf / 'model.pdb'; artifact.write_text('audited coordinates')
            receipt = leaf / 'completed.json'
            receipt.write_text(json.dumps(dict(schema=1, result={'prediction':{}}, files={str(artifact.relative_to(root)):sha(artifact)})))
            with self.assertRaisesRegex(ValueError, 'explicit campaign root'): verify(receipt)
            outer = root / 'family/completed.json'
            seal(outer, dict(passed=True), [receipt], relative_root=root)
            self.assertTrue(verify(outer)['passed'])
            artifact.write_text('tampered')
            with self.assertRaisesRegex(ValueError, 'artifact changed'): verify(outer)

    def test_generation_only_plan_does_not_pin_dormant_models(self):
        sys.path.insert(0, str(ROOT / 'Sources/iProteinStudio/Resources/pipeline/mcp'))
        from iprotein_mcp.runtime_bindings import capture
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            for name in ('control', 'rfd4', 'esmfold2', 'mpnn'):
                current = root / 'components' / name / 'current'; current.mkdir(parents=True)
                (current / 'runtime.json').write_text(json.dumps(dict(engine=name, schema_version=1)))
            normalized = dict(workflow='rfd4', supporting_engines=['rfd4'],
                              request=dict(predictor='esmfold2-full-mlx', sequence_model='solublempnn'))
            self.assertEqual(set(capture(root, provenance=[], normalized=normalized)), {'control', 'rfd4'})

    def test_structure_handoff_has_no_optional_biology_dependency(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory); source = root / 'parent.pdb'
            source.write_text('ATOM      1  CA  GLY A   1       0.000   0.000   0.000  1.00 90.00           C\n'
                              'ATOM      2  CA  ALA B   1       4.000   0.000   0.000  1.00 90.00           C\nEND\n')
            code = '''import sys,json
from pathlib import Path
sys.path[:0]=sys.argv[1:3]
from rfd4.search_engine import canonical_protein,sequences
source,dest=map(Path,sys.argv[3:5])
cfg={'settings':{'binder_chain':'A','target_chain':'B'},'target_sequence':'G'}
canonical_protein(source,cfg,dest)
assert sequences(dest)=={'A':'A','B':'G'}
'''
            subprocess.run([sys.executable, '-S', '-B', '-c', code,
                str(ROOT / 'Sources/iProteinStudio/Resources/pipeline/scripts'),
                str(ROOT / 'Sources/iProteinStudio/Resources/rfd3'), str(source), str(root / 'roles.pdb')], check=True)

    def test_only_explicit_vendored_paths_can_be_relocated(self):
        spec = importlib.util.spec_from_file_location('runtime_builder', ROOT / 'tools/build_runtime_package.py')
        builder = importlib.util.module_from_spec(spec); spec.loader.exec_module(builder)
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory); original = root / 'source'; original.mkdir()
            out = root / 'package'; target = out / 'sources/upstream'; target.mkdir(parents=True)
            loader = out / 'site/editable.pth'; loader.parent.mkdir()
            loader.write_text(str(original) + '\n')
            builder.relocate_path_file(loader, {'upstream': original}, out)
            self.assertEqual((loader.parent / loader.read_text().strip()).resolve(), target.resolve())
            for content in ['/unregistered/source', 'import arbitrary_code', '../../elsewhere']:
                loader.write_text(content + '\n')
                with self.assertRaises(ValueError): builder.relocate_path_file(loader, {'upstream': original}, out)


if __name__ == '__main__': unittest.main()
