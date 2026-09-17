"""Actual broker worker tests for engine batches; inert scripts, no model inference."""
import json
import os
from pathlib import Path
import sys
import tempfile
import time
import unittest

MCP = Path(__file__).resolve().parents[1] / 'Sources/iProteinStudio/Resources/pipeline/mcp'
sys.path.insert(0, str(MCP))
from iprotein_mcp import broker, common
from iprotein_mcp.desktop import desktop_plan


class EngineBatch(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(prefix='engine-batch-test-')
        self.root = Path(self.tmp.name).resolve()
        self.env = dict(os.environ)
        os.environ.update(NANOHUNTER_ROOT=str(self.root), IPROTEINSTUDIO_TEST_SUPPORT_ROOT=str(self.root),
                          IPROTEINSTUDIO_AGENT_ROOT=str(self.root / 'agent'))
        self.workspace = self.root / 'projects/demo'
        self.batch = self.workspace / 'engine-batch-fixture'
        self.batch.mkdir(parents=True)
        self.children = []
        self.jobs = []
        for name in ['first', 'second', 'third']:
            child = self.workspace / name
            snapshot = child / '.studio_runtime/pipeline'
            (snapshot / 'scripts').mkdir(parents=True)
            runner = snapshot / 'nanohunter_run.sh'
            runner.write_text('''#!/usr/bin/python3
import json, os, pathlib, sys, time
args=sys.argv[1:]
root=pathlib.Path(os.environ['NANOHUNTER_ROOT'])
name=args[args.index('--run-name')+1]
out=pathlib.Path(args[args.index('--out-root')+1])/name
with (root/'calls').open('a') as f: f.write(name+'\\n')
if (root/('fail-'+name)).exists(): sys.exit(17)
if (root/('wait-'+name)).exists():
 (root/'waiting').touch()
 time.sleep(30)
(out/'summary_all_runs.csv').write_text('run,score\\n1,0.5\\n')
''')
            runner.chmod(0o755)
            template = child / 'design.yaml'
            template.write_text('synthetic fixture only')
            args = ['--out-root', str(self.workspace), '--run-name', name, '--template-yaml', str(template),
                    '--num-runs', '12', '--num-opt-cycles', '5', '--design-scheduler', 'resident']
            common.atomic_json(child / 'studio_run.json', {'pipelineSnapshot': str(snapshot), 'arguments': args,
                                                         'engineBatchRoot': str(self.batch), 'state': 'running'})
            self.children.append(child)
        common.atomic_json(self.batch / 'studio_engine_batch.json', {'version': 1,
            'campaigns': [str(p) for p in self.children], 'engines': ['First', 'Second', 'Third'], 'trajectoriesPerEngine': 12})

    def tearDown(self):
        for job in self.jobs:
            try:
                if broker.load_state(job)['status'] not in broker.TERMINAL:
                    broker.cancel_job(job); self.wait(job)
            except Exception: pass
        os.environ.clear(); os.environ.update(self.env)
        self.tmp.cleanup()

    def plan(self):
        return desktop_plan({'project': 'demo', 'workflow': 'iterative_batch', 'output': str(self.batch)})

    def start(self):
        plan = self.plan()
        state = broker.start_job(plan['id'], plan['sha256'])
        self.jobs.append(state['id'])
        return state['id']

    def wait(self, job):
        deadline = time.monotonic() + 15
        while time.monotonic() < deadline:
            state = broker.load_state(job)
            if state['status'] in broker.TERMINAL and not common.process_alive(state.get('pid')): return state
            time.sleep(.05)
        self.fail('worker did not finish')

    def calls(self):
        return (self.root / 'calls').read_text().splitlines()

    def test_invalid_last_engine_rejects_batch_before_first_engine_runs(self):
        path = self.children[-1] / 'studio_run.json'
        manifest = json.loads(path.read_text())
        manifest['arguments'] += ['--predictor', 'openfold-3-mlx']
        common.atomic_json(path, manifest)
        with self.assertRaisesRegex(common.StudioError, 'OpenFold-3 has no resident worker'):
            self.start()
        self.assertFalse((self.root / 'calls').exists())
        self.assertFalse(list((self.root / 'agent/jobs').glob('*/state.json')))
        manifest['arguments'][manifest['arguments'].index('--design-scheduler') + 1] = 'run'
        common.atomic_json(path, manifest)
        job = self.start()
        self.assertEqual(self.wait(job)['status'], 'completed')
        self.assertEqual(self.calls(), ['first', 'second', 'third'])

    def scaffold_batch(self, budgets=(10, 20, 40)):
        path = self.batch / 'studio_engine_batch.json'
        descriptor = json.loads(path.read_text())
        descriptor.update(version=2, trajectoriesPerEngine=sum(budgets),
                          campaignBudgets=list(budgets), engineIDs=['boltz'] * 3,
                          scaffoldIDs=['framework-a', 'framework-b', 'framework-c'])
        common.atomic_json(path, descriptor)
        for i, child in enumerate(self.children):
            path = child / 'studio_run.json'; manifest = json.loads(path.read_text())
            args = manifest['arguments']; args[args.index('--num-runs') + 1] = str(budgets[i])
            manifest.update(requestedTrajectories=budgets[i], request={
                'designType': 'nanobody', 'designPredictor': 'boltz',
                'scaffoldID': descriptor['scaffoldIDs'][i], 'numDesigns': budgets[i]})
            common.atomic_json(path, manifest)

    def test_scaffold_allocations_execute_and_resume(self):
        self.scaffold_batch()
        fail = self.root / 'fail-second'; fail.touch()
        job = self.start()
        self.assertEqual(self.wait(job)['status'], 'failed')
        fail.unlink(); broker.resume_job(job)
        self.assertEqual(self.wait(job)['status'], 'completed')
        self.assertEqual(self.calls(), ['first', 'second', 'second', 'third'])

    def test_scaffold_budget_and_identity_mismatches_rejected(self):
        self.scaffold_batch()
        self.plan()
        path = self.batch / 'studio_engine_batch.json'
        original = json.loads(path.read_text())
        for field, value in [('campaignBudgets', [10, 20, 39]),
                             ('campaignBudgets', [0, 30, 40]),
                             ('campaignBudgets', [True, 29, 40]),
                             ('scaffoldIDs', ['framework-a'] * 3),
                             ('engineIDs', ['boltz', 'intellifold', 'boltz'])]:
            common.atomic_json(path, {**original, field: value})
            with self.assertRaises(common.StudioError): self.plan()
        common.atomic_json(path, original)
        path = self.children[1] / 'studio_run.json'; manifest = json.loads(path.read_text())
        manifest['request']['scaffoldID'] = 'wrong-framework'
        common.atomic_json(path, manifest)
        with self.assertRaises(common.StudioError): self.plan()
        self.assertFalse((self.root / 'calls').exists())

    def test_preflight_all_children_before_submission(self):
        plan = self.plan()
        children = plan['normalized_request']['engine_campaigns']
        self.assertEqual(len(children), 3)
        self.assertTrue(all('--resume' in child['steps'][0]['command'] for child in children))
        self.assertEqual(len(plan['normalized_request']['child_outputs']), 3)
        (self.children[-1] / 'design.yaml').unlink()
        with self.assertRaises(common.StudioError): self.plan()
        self.assertFalse((self.root / 'calls').exists())

    def test_failure_then_resume_skips_completed_engine(self):
        fail = self.root / 'fail-second'; fail.touch()
        job = self.start()
        state = self.wait(job)
        self.assertEqual(state['status'], 'failed')
        self.assertEqual(self.calls(), ['first', 'second'])
        self.assertEqual(state['active_output'], str(self.children[1]))
        self.assertEqual(state['output_root'], str(self.batch))
        self.assertEqual(json.loads((self.children[0] / 'studio_run.json').read_text())['state'], 'completed')
        # Simulate a quit after writing the receipt but before the manifest.
        first_manifest = self.children[0] / 'studio_run.json'
        interrupted = json.loads(first_manifest.read_text()); interrupted['state'] = 'running'
        common.atomic_json(first_manifest, interrupted)
        fail.unlink()
        broker.resume_job(job)
        self.assertEqual(self.wait(job)['status'], 'completed')
        self.assertEqual(self.calls(), ['first', 'second', 'second', 'third'])
        receipt = json.loads((self.batch / 'engine_batch_progress.json').read_text())
        self.assertEqual(len(receipt['completed']), 3)
        for child in self.children:
            self.assertEqual(json.loads((child / 'studio_job.json').read_text())['id'], job)
            self.assertEqual(json.loads((child / 'studio_run.json').read_text())['state'], 'completed')

    def test_batch_receipt_covers_nesso_json_artifacts(self):
        import hashlib
        stage = self.children[0] / 'nesso_verification'; stage.mkdir()
        raw = stage / 'affinity.json'; raw.write_text('{"score": 0.8}')
        common.atomic_json(stage / 'completed.json', {'files': {'affinity.json': hashlib.sha256(raw.read_bytes()).hexdigest()}})
        (self.root/'fail-second').touch()
        job=self.start(); self.assertEqual(self.wait(job)['status'], 'failed')
        raw.write_text('{"score": 0.9}')
        broker.resume_job(job)
        state=self.wait(job)
        self.assertEqual(state['status'], 'failed')
        self.assertIn('outputs changed', state['message'])

    def test_resume_rejects_changed_completed_outputs(self):
        (self.root / 'fail-second').touch()
        job = self.start(); self.wait(job)
        (self.children[0] / 'summary_all_runs.csv').write_text('changed')
        broker.resume_job(job)
        state = self.wait(job)
        self.assertEqual(state['status'], 'failed')
        self.assertIn('outputs changed', state['message'])
        self.assertEqual(self.calls(), ['first', 'second'])

    def test_stop_prevents_later_engines_and_resume_continues(self):
        pause = self.root / 'wait-second'; pause.touch()
        job = self.start()
        deadline = time.monotonic() + 10
        while not (self.root / 'waiting').exists() and time.monotonic() < deadline: time.sleep(.05)
        self.assertTrue((self.root / 'waiting').exists())
        broker.cancel_job(job)
        self.assertEqual(self.wait(job)['status'], 'cancelled')
        self.assertEqual(self.calls(), ['first', 'second'])
        pause.unlink(); broker.resume_job(job)
        self.assertEqual(self.wait(job)['status'], 'completed')
        self.assertEqual(self.calls(), ['first', 'second', 'second', 'third'])

    def test_reject_duplicate_and_foreign_campaigns(self):
        path = self.batch / 'studio_engine_batch.json'
        descriptor = json.loads(path.read_text())
        descriptor['campaigns'][2] = descriptor['campaigns'][0]
        common.atomic_json(path, descriptor)
        with self.assertRaises(common.StudioError): self.plan()
        descriptor['campaigns'][2] = str(self.root / 'elsewhere')
        common.atomic_json(path, descriptor)
        with self.assertRaises(common.StudioError): self.plan()

    def test_changed_later_engine_script_blocks_entire_plan(self):
        plan = self.plan()
        runner = self.children[2] / '.studio_runtime/pipeline/nanohunter_run.sh'
        runner.write_text(runner.read_text() + '\n# changed after preflight\n')
        with self.assertRaises(common.StudioError):
            broker.start_job(plan['id'], plan['sha256'])
        self.assertFalse((self.root / 'calls').exists())

if __name__ == '__main__': unittest.main()
