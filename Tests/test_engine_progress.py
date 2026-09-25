"""Execute observers and isolated managed Python children; no model inference."""
import contextlib
import io
import json
import os
from pathlib import Path
import random
import subprocess
import sys
import tempfile
import threading
import time
import types
import unittest
from unittest.mock import patch

SCRIPTS = Path(__file__).resolve().parents[1] / 'Sources/iProteinStudio/Resources/pipeline/scripts'
sys.path.insert(0, str(SCRIPTS))
import engine_progress as progress


class ProgressTests(unittest.TestCase):
    def setUp(self):
        self.events = []
        self.emitter = patch.object(progress, 'emit', side_effect=lambda *a, **k: self.events.append((a, k)))
        self.emitter.start()
        progress._reporter = progress.Reporter(interval=3600)

    def tearDown(self):
        progress._reporter.stop.set()
        self.emitter.stop()

    def test_identity_arguments_rng_and_exceptions_preserved(self):
        failure = ValueError('same exception')
        class Model:
            def run(self, x, *, fail=False):
                if fail:
                    raise failure
                return x
        progress.wrap(Model, 'run', 'fixture', 'forward')
        progress.wrap(Model, 'run', 'fixture', 'forward')
        model = Model()
        value = object()
        state = random.getstate()
        self.assertIs(model.run(value), value)
        self.assertEqual(random.getstate(), state)
        with self.assertRaises(ValueError) as caught:
            model.run(value, fail=True)
        self.assertIs(caught.exception, failure)
        self.assertEqual([a[1] for a, _ in self.events], ['host_enter', 'host_return', 'host_enter', 'host_error'])
        self.assertFalse(progress.reporter().active)

    def test_nested_heartbeat_and_idle(self):
        r = progress.reporter()
        outer = r.enter('fixture', 'prediction', 1)
        inner = r.enter('fixture', 'denoising', 1)
        r.heartbeat()
        self.assertEqual(self.events[-1][0], ('fixture', 'heartbeat', 'denoising'))
        self.assertEqual(self.events[-1][1]['compute_progress'], 'unknown')
        r.leave(inner, False)
        r.heartbeat()
        self.assertEqual(self.events[-1][0][2], 'prediction')
        r.leave(outer, False)
        n = len(self.events)
        r.heartbeat()
        self.assertEqual(len(self.events), n)

    def test_rate_limit_counts_calls_without_claiming_steps(self):
        class Model:
            def run(self): return 42
        progress.wrap(Model, 'run', 'fixture', 'denoising', 25)
        model = Model()
        for _ in range(51): self.assertEqual(model.run(), 42)
        starts = [k['call'] for a, k in self.events if a[1] == 'host_enter']
        self.assertEqual(starts, [1, 25, 50])

    def test_all_profiles_execute_real_wrappers(self):
        # Each registered entry exercises the same runtime loader/wrapper contract.
        for name, hooks in progress.HOOKS.items():
            module = types.ModuleType(name)
            for engine, cls, method, stage, every in hooks:
                if not hasattr(module, cls): setattr(module, cls, type(cls, (), {}))
                setattr(getattr(module, cls), method, lambda *args, **kw: kw.get('sentinel'))
            progress.instrument(module)
            for engine, cls, method, stage, every in hooks:
                sentinel = object()
                self.assertIs(getattr(getattr(module, cls), method)(object(), sentinel=sentinel), sentinel)
        self.assertNotIn('hook_unavailable', [a[1] for a, _ in self.events])

    def test_missing_hook_reported(self):
        module = types.ModuleType('runner.inference')
        progress.instrument(module)
        self.assertTrue(all(a[1] == 'hook_unavailable' for a, _ in self.events))

    def test_heartbeat_thread_runs_without_computation_progress(self):
        r = progress.Reporter(interval=.01)
        try:
            token = r.enter('fixture', 'blocked_call', 1)
            deadline = time.monotonic() + 2
            while not any(a[1] == 'heartbeat' for a, _ in self.events) and time.monotonic() < deadline:
                time.sleep(.01)
            self.assertTrue(any(a[1] == 'heartbeat' and k['compute_progress'] == 'unknown' for a, k in self.events))
            r.leave(token, False)
        finally:
            r.stop.set()

    def test_runtime_sitecustomize_preserved(self):
        with tempfile.TemporaryDirectory() as tmp:
            base = Path(tmp)
            (base / 'sitecustomize.py').write_text('import os; os.environ["RUNTIME_POLICY"]="preserved"\n')
            env = progress.environment({**os.environ, 'PYTHONPATH': str(base)}, SCRIPTS)
            result = subprocess.run([sys.executable, '-c', 'import os; assert os.environ["RUNTIME_POLICY"]=="preserved"'], env=env, capture_output=True)
            self.assertEqual(result.returncode, 0, result.stderr)

    @unittest.skipUnless(hasattr(os, 'fork'), 'POSIX fork contract')
    def test_fork_child_has_fresh_reporter(self):
        code = '''import os
from engine_progress import reporter
r=reporter(); token=r.enter('fixture','parent',1)
pid=os.fork()
if pid==0:
 child=reporter()
 assert child is not r and not child.active
 t=child.enter('fixture','child',1); child.leave(t,False)
 os._exit(0)
_,status=os.waitpid(pid,0)
assert status==0
r.leave(token,False)
'''
        env = progress.environment(os.environ, SCRIPTS)
        result = subprocess.run([sys.executable, '-c', code], env=env, capture_output=True, timeout=5)
        self.assertEqual(result.returncode, 0, result.stderr)

    def test_broker_enables_retained_hooks_in_nested_child_log(self):
        sys.path.insert(0, str(SCRIPTS.parent / 'mcp'))
        from iprotein_mcp import broker
        with tempfile.TemporaryDirectory() as tmp:
            base = Path(tmp)
            (base / 'model_utils.py').write_text('class ProteinMPNN:\n def sample(self): return 1\n')
            # Simulate retained code separate from the mutable installation.
            env = {**os.environ, 'NANOHUNTER_ROOT': str(base),
                   'IPROTEINSTUDIO_PIPELINE_SNAPSHOT': str(SCRIPTS.parent),
                   'PYTHONPATH': str(base)}
            code = 'from model_utils import ProteinMPNN; assert ProteinMPNN().sample()==1'
            with patch.object(broker, 'state_path', return_value=base/'state.json'), \
                 patch.object(broker, '_RUNTIME_BINDINGS', {}), \
                 patch.object(broker, '_CODE_SNAPSHOT', None), \
                 patch.object(broker, '_EXECUTION_FD', None), \
                 patch.object(broker, '_update'), \
                 patch.object(broker, '_cancelled', return_value=False):
                rc = broker._run_logged('job-fixture', [sys.executable, '-c', code], base, env)
            self.assertEqual(rc, 0)
            log = (base / 'pipeline.log').read_text()
            self.assertIn('event=host_return', log)
            self.assertEqual(log.count('event=host_enter'), 1)

    def test_environment_preserves_paths_and_old_jobs(self):
        original = {'PYTHONPATH': '/existing', 'OTHER': 'preserved'}
        env = progress.environment(original, SCRIPTS)
        self.assertEqual(env['OTHER'], 'preserved')
        self.assertTrue(env['PYTHONPATH'].endswith('/existing'))
        self.assertEqual(progress.environment(env, SCRIPTS), env)
        self.assertNotIn('IPROTEINSTUDIO_PROGRESS', original)
        with tempfile.TemporaryDirectory() as tmp:
            self.assertEqual(progress.environment(original, Path(tmp)), original)
        self.assertEqual(progress.environment({'IPROTEINSTUDIO_PROGRESS': '0'}, SCRIPTS), {'IPROTEINSTUDIO_PROGRESS': '0'})

    def test_bootstrap_streams_live_through_captured_stderr_and_exits(self):
        with tempfile.TemporaryDirectory() as tmp:
            base = Path(tmp)
            (base / 'model_utils.py').write_text('class ProteinMPNN:\n def sample(self, value): return value\n')
            log = base / 'job.log'
            env = progress.environment({**os.environ, 'PYTHONPATH': str(base)}, SCRIPTS, log)
            code = "import sys,time; from model_utils import ProteinMPNN; assert ProteinMPNN().sample(7)==7; print('READY',flush=True); time.sleep(.5)"
            child = subprocess.Popen([sys.executable, '-c', code], env=env, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
            try:
                self.assertEqual(child.stdout.readline().strip(), 'READY')
                self.assertIsNone(child.poll())
                self.assertIn('event=host_return', log.read_text())
                out, err = child.communicate(timeout=5)
                self.assertEqual(child.returncode, 0, err)
                self.assertEqual(err.count('event=host_enter'), 1)
                self.assertEqual(err.count('event=host_return'), 1)
            finally:
                if child.poll() is None: child.kill(); child.wait()

    def test_json_stdout_clean_and_failed_exit_preserved(self):
        with tempfile.TemporaryDirectory() as tmp:
            base = Path(tmp)
            (base / 'model_utils.py').write_text('class ProteinMPNN:\n def sample(self): raise ValueError("original")\n')
            env = progress.environment({**os.environ, 'PYTHONPATH': str(base)}, SCRIPTS)
            result = subprocess.run([sys.executable, '-c', 'from model_utils import ProteinMPNN; print("{}",flush=True); ProteinMPNN().sample()'], env=env, capture_output=True, text=True)
            self.assertEqual(json.loads(result.stdout), {})
            self.assertEqual(result.returncode, 1)
            self.assertIn('event=host_error', result.stderr)
            self.assertIn('ValueError: original', result.stderr)

    def test_no_duplicate_when_stderr_is_job_log(self):
        with tempfile.TemporaryDirectory() as tmp:
            base = Path(tmp)
            (base / 'model_utils.py').write_text('class ProteinMPNN:\n def sample(self): return 1\n')
            log = base / 'job.log'
            env = progress.environment({**os.environ, 'PYTHONPATH': str(base)}, SCRIPTS, log)
            with log.open('w') as handle:
                result = subprocess.run([sys.executable, '-c', 'from model_utils import ProteinMPNN; ProteinMPNN().sample()'], env=env, stderr=handle)
            self.assertEqual(result.returncode, 0)
            self.assertEqual(log.read_text().count('event=host_enter'), 1)

    def test_broken_log_sink_does_not_change_result(self):
        with tempfile.TemporaryDirectory() as tmp:
            base = Path(tmp)
            (base / 'model_utils.py').write_text('class ProteinMPNN:\n def sample(self): return 9\n')
            env = progress.environment({**os.environ, 'PYTHONPATH': str(base)}, SCRIPTS, base / 'missing/job.log')
            result = subprocess.run([sys.executable, '-c', 'from model_utils import ProteinMPNN; assert ProteinMPNN().sample()==9'], env=env, capture_output=True)
            self.assertEqual(result.returncode, 0, result.stderr)


if __name__ == '__main__': unittest.main()
