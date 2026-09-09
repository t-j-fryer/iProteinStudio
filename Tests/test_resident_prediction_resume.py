"""Exercise the real resident IntelliFold loop and receipts without loading a model.

The subprocess fixture simulates a hard interruption inside multi-seed inference.
Only tensor/model/accelerator operations are faked; checkpointing, validation,
compression, manifest filtering, RNG boundaries and the shell request setup run.
"""
from argparse import Namespace
from dataclasses import dataclass
import gzip
import json
import os
from pathlib import Path
import random
import subprocess
import sys
import tempfile
import types
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = ROOT / 'Sources/iProteinStudio/Resources/pipeline/scripts'
sys.path.insert(0, str(SCRIPTS))
# The fast suite has no scientific dependencies. The same tests also run with
# the managed IntelliFold Python, where real PyYAML and ipSAE are exercised.
try:
    import yaml
except ImportError:
    sys.modules['yaml'] = types.SimpleNamespace(safe_load=json.loads)
try:
    import ipsae_score
except ImportError:
    sys.modules['ipsae_score'] = types.SimpleNamespace(annotate_intellifold=lambda _: None)
from prediction_resume import PredictionLedger, RecordSeedDataset, artifacts, input_identity
from resident_predictor import IntelliFoldSession

PDB = 'ATOM      1  CA  ALA A   1       0.000   0.000   0.000  1.00 80.00           C  \nEND\n'


def write_prediction(root, name, seed=42, sample=0, feature=0.5):
    leaf = root / name
    leaf.mkdir(parents=True, exist_ok=True)
    stem = f'{name}_seed-{seed}_sample-{sample}'
    (leaf / (stem + '.pdb')).write_text(PDB)
    (leaf / (stem + '_summary_confidences.json')).write_text(json.dumps({'ranking_score': feature}))
    (leaf / (stem + '_confidences.json')).write_text(json.dumps({'pae': [[0]], 'token_chain_ids': ['A']}))


@dataclass(frozen=True)
class Manifest:
    records: list

    @classmethod
    def load(cls, path):
        return cls([Namespace(id=name) for name in json.loads(path.read_text())])


class Tensor:
    def long(self): return self
    def float(self): return self


class Loader:
    def __init__(self, dataset, batch_size=1, num_workers=0, collate_fn=None,
                 pin_memory=False, drop_last=False, shuffle=False):
        self.dataset = dataset
        self.batch_size, self.num_workers = batch_size, num_workers
        self.collate_fn, self.pin_memory, self.drop_last = collate_fn, pin_memory, drop_last

    def __iter__(self):
        # Model Accelerate's lookahead, not just an ordinary generator.
        if not len(self.dataset): return
        current = self.dataset[0]
        for i in range(1, len(self.dataset)):
            following = self.dataset[i]
            yield current
            current = following
        yield current


def fake_worker(root, interrupt=False, mutate=False):
    source, output = root / 'inputs', root / 'output'
    def process_inputs(args, data, out_dir, **kwargs):
        processed = out_dir / 'processed'
        processed.mkdir(parents=True, exist_ok=True)
        (processed / 'manifest.json').write_text(json.dumps([p.stem for p in data]))
    def loader(manifest, **kwargs):
        assert manifest.records, 'A fully reused batch must not create an empty Accelerate loader'
        class Dataset:
            def __len__(self): return len(manifest.records)
            def __getitem__(self, index):
                return {'record': [manifest.records[index]], 'structure': None,
                        'msa': Tensor(), 'feature': random.random()}
        return Loader(Dataset())
    def predict(args, model, features, record, structure, out_dir, seed):
        with (root / 'inference_calls.jsonl').open('a') as stream:
            stream.write(json.dumps([record.id, seed]) + '\n')
        for sample in range(args.num_diffusion_samples):
            write_prediction(out_dir / 'predictions', record.id, seed, sample, features['feature'])
        if mutate:
            (source / f'{record.id}.yaml').write_text('{"changed": true}')
        if interrupt and record.id == 'job1' and seed == 42:
            (out_dir / 'predictions/job1/job1_seed-42_sample-0.pdb').write_text('truncated')
            os._exit(73)
    session = IntelliFoldSession.__new__(IntelliFoldSession)
    session.config = {}
    session.root = SCRIPTS.parent
    session.args = Namespace(cache=str(root), use_msa_server=False, msa_server_url='',
                             msa_pairing_strategy='greedy', no_pairing=False,
                             use_template=False, num_diffusion_samples=2, output_format='pdb')
    session.seeds = [42, 43]
    session.resume_identity = {'fixture_model': 'v1', 'buckets': (256, 512),
                               'feature_rng_policy': 'reset-first-seed-before-each-record-v1'}
    session.model = Namespace(generator=Namespace(manual_seed=lambda _: None))
    session.torch = Namespace(utils=Namespace(data=Namespace(DataLoader=Loader)))
    session.accelerator = Namespace(prepare=lambda x: x, device='fixture', wait_for_everyone=lambda: None)
    session.upstream = Namespace(check_inputs=lambda p: sorted(p.glob('*.yaml')),
                                 process_inputs=process_inputs, Manifest=Manifest,
                                 BoltzProcessedInput=Namespace, get_inference_dataloader=loader,
                                 construct_empty_template_features=lambda *a, **k: {}, predict_and_save=predict)
    def progress(completed, total, reused):
        with (root / 'progress.jsonl').open('a') as stream:
            stream.write(json.dumps([completed, total, reused]) + '\n')
    session.report_progress = progress
    functional = types.ModuleType('torch.nn.functional'); functional.one_hot = lambda x, **kw: x
    nn = types.ModuleType('torch.nn'); nn.functional = functional
    torch = types.ModuleType('torch'); torch.nn = nn
    accelerate = types.ModuleType('accelerate')
    utils = types.ModuleType('accelerate.utils'); utils.set_seed = random.seed
    with patch.dict(sys.modules, {'torch': torch, 'torch.nn': nn, 'torch.nn.functional': functional,
                                 'accelerate': accelerate, 'accelerate.utils': utils}):
        session.predict(source, output, len(list(source.glob('*.yaml'))))


class ResumeTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.pred = self.root / 'predictions'
        self.identity = {'model': 'fixture', 'code': 'v1', 'steps': 200, 'buckets': (256, 512)}
        self.inputs = {'job0': {'yaml_sha256': 'first'}, 'job1': {'yaml_sha256': 'second'}}

    def ledger(self, **changes):
        values = dict(output=self.root, prediction_root=self.pred, identity=self.identity,
                      inputs=self.inputs, seeds=[42], samples=1, extension='pdb')
        values.update(changes)
        return PredictionLedger(**values)

    def complete_first(self):
        ledger = self.ledger()
        write_prediction(self.pred, 'job0')
        ledger.commit('job0')
        return ledger

    def prepare_campaign(self, folder):
        (folder / 'inputs').mkdir(parents=True)
        for i in range(3):
            (folder / 'inputs' / f'job{i}.yaml').write_text(json.dumps({'fixture': i}))

    def worker(self, folder, mode='complete'):
        return subprocess.run([sys.executable, __file__, '--worker', str(folder), mode],
                              capture_output=True, text=True, timeout=30)

    def test_hard_interruption_resumes_only_uncommitted_prediction(self):
        resumed, reference = self.root / 'resumed', self.root / 'reference'
        for root in (resumed, reference): self.prepare_campaign(root)
        interrupted = self.worker(resumed, 'interrupt')
        self.assertEqual(interrupted.returncode, 73, interrupted.stderr)
        leaf = resumed / 'output/inputs/predictions/job0'
        before = {p.name: (p.stat().st_mtime_ns, p.read_bytes()) for p in leaf.iterdir()}
        finished = self.worker(resumed)
        self.assertEqual(finished.returncode, 0, finished.stderr)
        self.assertEqual(before, {p.name: (p.stat().st_mtime_ns, p.read_bytes()) for p in leaf.iterdir()})
        calls = [json.loads(x) for x in (resumed / 'inference_calls.jsonl').read_text().splitlines()]
        self.assertEqual(calls, [['job0', 42], ['job0', 43], ['job1', 42], ['job1', 42], ['job1', 43], ['job2', 42], ['job2', 43]])
        self.assertTrue(list((resumed / 'output/.prediction_resume/interrupted').rglob('job1')))
        original = self.worker(reference)
        self.assertEqual(original.returncode, 0, original.stderr)
        for i in range(3):
            name = f'job{i}'
            self.assertEqual(artifacts(resumed / 'output/inputs/predictions' / name, name, [42, 43], 2, 'pdb'),
                             artifacts(reference / 'output/inputs/predictions' / name, name, [42, 43], 2, 'pdb'))
        again = self.worker(resumed)
        self.assertEqual(again.returncode, 0, again.stderr)
        self.assertEqual(len((resumed / 'inference_calls.jsonl').read_text().splitlines()), len(calls))
        progress = [json.loads(x) for x in (resumed / 'progress.jsonl').read_text().splitlines()]
        self.assertEqual(progress, [[0, 3, 0], [1, 3, 0], [1, 3, 1], [2, 3, 1], [3, 3, 1], [3, 3, 3]])
        # Shell already materialized job0: the stored manifest must be filtered.
        (resumed / 'inputs/job0.yaml').unlink()
        subset = self.worker(resumed)
        self.assertEqual(subset.returncode, 0, subset.stderr)
        self.assertEqual(len((resumed / 'inference_calls.jsonl').read_text().splitlines()), len(calls))

    def test_changed_inputs_during_inference_do_not_commit(self):
        self.prepare_campaign(self.root)
        result = self.worker(self.root, 'mutate')
        self.assertNotEqual(result.returncode, 0)
        self.assertIn('changed during prediction', result.stderr)
        self.assertEqual(json.loads((self.root / 'output/.prediction_resume/state.json').read_text())['completed'], {})

    def test_settings_weights_code_and_sample_changes_fail(self):
        self.complete_first()
        for identity in ({**self.identity, 'model': 'different'}, {**self.identity, 'code': 'v2'},
                         {**self.identity, 'steps': 201}):
            with self.assertRaisesRegex(RuntimeError, 'model, settings, or runtime changed'):
                self.ledger(identity=identity)
        for kwargs in ({'seeds': [43]}, {'samples': 2}, {'extension': 'cif'}):
            with self.assertRaisesRegex(RuntimeError, 'model, settings, or runtime changed'):
                self.ledger(**kwargs)

    def test_yaml_dependency_and_membership_changes_fail(self):
        self.complete_first()
        for inputs in ({'job0': {'yaml_sha256': 'changed'}}, {'new_job': {}},
                       {'job0': {**self.inputs['job0'], 'dependencies': {'msa': 'new'}}}):
            with self.assertRaisesRegex(RuntimeError, 'YAML, MSA, template, or batch membership changed'):
                self.ledger(inputs=inputs)

    def test_missing_or_modified_completed_output_is_never_overwritten(self):
        self.complete_first()
        summary = self.pred / 'job0/job0_seed-42_sample-0_summary_confidences.json'
        summary.write_text('{"ranking_score": 0.1}')
        with self.assertRaisesRegex(RuntimeError, 'Completed prediction changed'):
            self.ledger()
        summary.unlink()
        with self.assertRaisesRegex(RuntimeError, 'Missing confidence'):
            self.ledger()
        with gzip.open(summary.with_suffix('.json.gz'), 'wt') as stream:
            stream.write('{"ranking_score": 0.5}')
        with self.assertRaisesRegex(RuntimeError, 'Missing confidence'):
            self.ledger()  # Materialization requires a plain summary.

    def test_compression_equivalent_but_conflicts_and_nan_rejected(self):
        self.complete_first()
        detail = self.pred / 'job0/job0_seed-42_sample-0_confidences.json'
        compressed = detail.with_suffix('.json.gz')
        with gzip.open(compressed, 'wt') as stream: stream.write(detail.read_text())
        detail.unlink()
        self.assertTrue(self.ledger().complete('job0'))
        detail.write_text('{"different": 1}')
        with self.assertRaisesRegex(RuntimeError, 'Conflicting compressed'):
            self.ledger()
        detail.write_text('{"value": NaN}')
        with self.assertRaises(ValueError): self.ledger()

    def test_all_seed_sample_outputs_required_before_commit(self):
        ledger = self.ledger(seeds=[42, 43], samples=2)
        write_prediction(self.pred, 'job0')
        with self.assertRaises(RuntimeError): ledger.commit('job0')
        self.assertEqual(ledger.state['completed'], {})
        for seed in (42, 43):
            for sample in (0, 1): write_prediction(self.pred, 'job0', seed, sample)
        ledger.commit('job0')
        self.assertTrue(ledger.complete('job0'))
        with self.assertRaisesRegex(RuntimeError, 'Refusing to overwrite'): ledger.prepare('job0')

    def test_untracked_outputs_not_adopted_and_unrequested_write_refused(self):
        write_prediction(self.pred, 'job0')
        with self.assertRaisesRegex(RuntimeError, 'no per-prediction resume provenance'): self.ledger()
        self.assertTrue((self.pred / 'job0').is_dir())
        ledger = self.ledger(prediction_root=self.root / 'new')
        for name in ('../outside', 'unknown'):
            with self.assertRaises(RuntimeError): ledger.prepare(name)
            with self.assertRaises(RuntimeError): ledger.commit(name)

    def test_processed_cache_verified_and_partial_cache_archived(self):
        ledger = self.ledger()
        processed = self.root / 'processed'; processed.mkdir()
        (processed / 'partial').write_text('interrupted')
        def build():
            processed.mkdir()
            (processed / 'manifest.json').write_text('{}')
        ledger.prepare_features(processed, build)
        self.assertTrue(list((self.root / '.prediction_resume/interrupted').rglob('partial')))
        ledger = self.ledger()
        ledger.prepare_features(processed, lambda: self.fail('Should reuse processed inputs'))
        (processed / 'manifest.json').write_text('{"changed": true}')
        with self.assertRaisesRegex(RuntimeError, 'Processed prediction inputs changed'):
            ledger.prepare_features(processed, build)

    def test_dependency_contents_and_missing_files(self):
        msa = self.root / 'target.a3m'; msa.write_text('fixture alignment')
        cif = self.root / 'template.cif'; cif.write_text('fixture template')
        manifest = self.root / 'template.json'
        manifest.write_text(json.dumps({'normalized_mmcif': str(cif), 'mappings': [{'a3m': str(msa)}]}))
        path = self.root / 'input.yaml'
        path.write_text(json.dumps({'sequences': [{'protein': {'msa': str(msa)}}],
                                    'target_template_manifest': str(manifest)}))
        original = input_identity(path)
        self.assertEqual(len(original['dependencies']), 3)
        msa.write_text('changed alignment')
        self.assertNotEqual(original, input_identity(path))
        cif.unlink()
        with self.assertRaisesRegex(RuntimeError, 'Resume dependency missing'): input_identity(path)

    def test_cycle_wave_rebuilds_input_links_for_remaining_jobs(self):
        script = (SCRIPTS.parent / 'nanohunter_run.sh').read_text()
        start = script.index('run_cycle_wave_predictor_batch() {')
        stop = script.index('  local start_ts end_ts duration rc', start)
        function = script[start:stop] + '\n}\n'
        campaign = self.root / 'campaign'
        for i in (1, 2):
            folder = campaign / f'run_{i:03d}/cycle_01'; folder.mkdir(parents=True)
            (folder / f'run_{i:03d}_cycle_01.yaml').write_text('{}')
        links = campaign / '_cycle_wave/cycle_01/batch_01/inputs'; links.mkdir(parents=True)
        (links / 'run_001_cycle_01.yaml').symlink_to(campaign / 'run_001/cycle_01/run_001_cycle_01.yaml')
        (links / 'stale.yaml').symlink_to(campaign / 'missing.yaml')
        harness = '''set -euo pipefail
EXPT_ROOT="$1"; PREDICTOR=intellifold; RESUME=1
cycle_prediction_complete() { [[ "$1" == */run_001/* ]]; }
die() { echo "$*" >&2; exit 1; }
''' + function + '\nrun_cycle_wave_predictor_batch 1 1 1 2\n'
        result = subprocess.run(['bash', '-c', harness, 'fixture', str(campaign)], capture_output=True, text=True)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual([p.name for p in links.iterdir()], ['run_002_cycle_01.yaml'])

    def test_shell_reports_durable_progress_and_accepts_resident_receipt(self):
        script = (SCRIPTS.parent / 'nanohunter_run.sh').read_text()
        start = script.index('submit_resident_predictor_request() {')
        stop = script.index('\nrun_cycle_wave_predictor_batch() {', start)
        (self.root / 'inputs').mkdir()
        (self.root / 'inputs/job.yaml').write_text('{}')
        (self.root / 'queue/responses').mkdir(parents=True)
        (self.root / '_cycle_wave').mkdir()
        (self.root / 'queue/progress_cycle_01_batch_01.json').write_text(
            json.dumps({'completed': 1, 'total': 1, 'reused': 1}))
        # Virtualize only waiting: at the next poll after the 10-second progress
        # interval, return a completed response from a model loaded once.
        harness = '''set -euo pipefail
EXPT_ROOT="$1"; RESIDENT_QUEUE="$1/queue"; RESIDENT_LOG="$1/log"
RESIDENT_PID=$$; PREDICTOR=intellifold
die() { echo "$*" >&2; exit 1; }
sleep() {
  if [[ "$tick" -eq 40 ]]; then
    echo '{"ok":true,"request_id":"cycle_01_batch_01","completed_jobs":1,"model_load_count":1,"wall_seconds":0.1}' > "$RESIDENT_QUEUE/responses/request_cycle_01_batch_01.json"
  fi
}
''' + script[start:stop] + '\nsubmit_resident_predictor_request 1 1 "$1/inputs" "$1/output" 1\n'
        result = subprocess.run(['bash', '-c', harness, 'fixture', str(self.root)],
                                capture_output=True, text=True, timeout=10)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(result.stderr.count('1/1 predictions complete (1 reused)'), 1)
        self.assertIn('cycle_01_batch_01,1,1,1,0.1,1',
                      (self.root / '_cycle_wave/resident_requests.csv').read_text())

    @unittest.skipUnless(hasattr(sys.modules['yaml'], '__version__'), 'real PyYAML requires managed engine Python')
    def test_yaml_mapping_and_relative_template_dependency(self):
        (self.root / 'template.cif').write_text('fixture')
        path = self.root / 'job.yaml'
        path.write_text('sequences:\n  - protein:\n      msa: empty\ntemplates:\n  - cif: template.cif\n')
        self.assertEqual(set(input_identity(path)['dependencies']), {str((self.root / 'template.cif').resolve())})

    def test_feature_seeding_survives_actual_accelerate_lookahead(self):
        try:
            import torch
            from accelerate.data_loader import DataLoaderShard
            from accelerate.utils import set_seed
        except ImportError:
            self.skipTest('actual CPU loader requires managed engine Python')
        class Dataset:
            def __init__(self, count): self.count = count
            def __len__(self): return self.count
            def __getitem__(self, index): return torch.rand(4)
        def outputs(count):
            loader = DataLoaderShard(RecordSeedDataset(Dataset(count), 42, set_seed),
                                     batch_size=1, num_workers=0, device=torch.device('cpu'))
            result = []
            for value in loader:
                result.append(value.tolist())
                torch.rand(100)  # unrelated model RNG consumption between items
            return result
        full, remaining = outputs(3), outputs(2)
        self.assertEqual(full[1:], remaining)


if __name__ == '__main__':
    if len(sys.argv) > 1 and sys.argv[1] == '--worker':
        fake_worker(Path(sys.argv[2]), interrupt=sys.argv[3] == 'interrupt', mutate=sys.argv[3] == 'mutate')
    else:
        unittest.main(verbosity=2)
