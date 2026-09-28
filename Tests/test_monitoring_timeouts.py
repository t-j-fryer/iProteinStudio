"""Fault injection of the student's ps timeout; no model or real job touched."""
import fcntl
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'Sources/iProteinStudio/Resources/pipeline/mcp'))
from iprotein_mcp import broker, process_tree, recovery
from iprotein_mcp.common import atomic_json, StudioError
from iprotein_mcp.process_tree import ProcessInspectionUnavailable


class MonitoringTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        self.job = 'job-timeout-test'
        self.directory = self.root / 'agent/jobs' / self.job
        self.directory.mkdir(parents=True)
        self.env = patch.dict(os.environ, NANOHUNTER_ROOT=str(self.root), IPROTEINSTUDIO_AGENT_ROOT=str(self.root / 'agent'))
        self.env.start()
        atomic_json(self.directory / 'state.json', dict(id=self.job, status='running', stage='prediction'))
        self.old_fd = broker._EXECUTION_FD

    def tearDown(self):
        broker._EXECUTION_FD = self.old_fd
        self.env.stop()
        self.tmp.cleanup()

    def state(self): return json.loads((self.directory / 'state.json').read_text())

    def test_snapshot_normalizes_timeout_bad_exit_and_empty_output(self):
        for error in [subprocess.TimeoutExpired('ps', 3), subprocess.CalledProcessError(1, 'ps'), OSError('unavailable')]:
            with self.subTest(error=error), patch.object(process_tree.subprocess, 'run', side_effect=error):
                with self.assertRaises(ProcessInspectionUnavailable): process_tree.snapshot()
        for output in ['', 'garbled\n']:
            with patch.object(process_tree.subprocess, 'run', return_value=subprocess.CompletedProcess('ps', 0, output)):
                with self.assertRaises(ProcessInspectionUnavailable): process_tree.snapshot()

    def run_with_failures(self, cancel=False):
        native = process_tree.snapshot
        native()  # Fail promptly if the test sandbox forbids process inspection.
        calls = 0
        lease = self.root / 'agent/execution.lock'
        observed = []
        def inspect():
            nonlocal calls
            calls += 1
            # Includes the very first scan and a later scan after ownership is
            # recorded. A real short-lived child is allowed to finish meanwhile.
            if calls in (1, 2, 4):
                self.assertIn(self.state()['status'], {'running', 'stopping'})
                with lease.open('a+') as contender:
                    with self.assertRaises(BlockingIOError):
                        fcntl.flock(contender, fcntl.LOCK_EX | fcntl.LOCK_NB)
                if calls == 2:
                    observed.append(self.state().get('monitoring_warning'))
                    if cancel: atomic_json(self.directory / 'cancel.json', {'requested': True})
                raise ProcessInspectionUnavailable('Injected ps timeout')
            return native()
        with lease.open('a+') as lock:
            fcntl.flock(lock, fcntl.LOCK_EX)
            broker._EXECUTION_FD = lock.fileno()
            command = [sys.executable, '-c', 'import time; time.sleep(%s); print("completed")' % (20 if cancel else .3)]
            with patch.object(process_tree, 'snapshot', side_effect=inspect):
                code = broker._run_logged(self.job, command, self.root, dict(os.environ))
            # Supervisor returned only after all recorded identities exited.
            receipt = json.loads((self.directory / 'processes.json').read_text())
            self.assertTrue(receipt['known'])
            self.assertEqual(recovery.owned_processes(receipt, native()), {})
        self.assertTrue(observed[0])
        self.assertIsNone(self.state().get('monitoring_warning'))
        self.assertNotEqual(self.state()['status'], 'failed')
        log = (self.directory / 'pipeline.log').read_text()
        self.assertIn('STUDIO_MONITOR_WARNING', log)
        self.assertIn('STUDIO_MONITOR_RECOVERED', log)
        return code

    def test_transient_timeouts_retain_execution_lease_and_finish(self):
        self.assertEqual(self.run_with_failures(), 0)

    def test_cancellation_survives_timeouts_and_stops_real_child(self):
        self.assertEqual(self.run_with_failures(cancel=True), 130)

    def test_worker_readiness_retries_before_launch(self):
        plan = dict(id='plan-fixture', sha256='fixture', kind='desktop_prediction', normalized_request={})
        atomic_json(self.directory / 'plan.json', plan)
        atomic_json(self.directory / 'state.json', dict(id=self.job, status='queued', pid=os.getpid()))
        rows = {os.getpid(): dict(parent=1, group=1, born='worker', state='S')}
        def execute(*args):
            ready = json.loads((self.directory / 'worker_ready.json').read_text())
            self.assertEqual(ready['born'], 'worker')
            self.assertIsNone(self.state().get('monitoring_warning'))
            return 0
        with patch.object(process_tree, 'snapshot', side_effect=[ProcessInspectionUnavailable('timeout'), rows]), \
             patch.object(broker.signal, 'signal'), patch.object(broker, 'load_plan', return_value=plan), \
             patch('iprotein_mcp.runtime_bindings.verify'), patch.object(broker, '_execute_desktop', side_effect=execute), \
             patch.object(broker, '_finish_manifest'):
            self.assertEqual(broker.run_worker(self.job), 0)
        self.assertEqual(self.state()['status'], 'completed')

    def test_no_signals_from_stale_identity_when_inspection_fails(self):
        rows = {10: dict(parent=1, group=10, born='original', state='S')}
        with patch.object(process_tree, 'snapshot', return_value=rows):
            family = process_tree.ProcessTree(10)
        with patch.object(process_tree, 'snapshot', side_effect=ProcessInspectionUnavailable('timeout')), patch.object(process_tree.os, 'kill') as kill:
            with self.assertRaises(ProcessInspectionUnavailable): family.send(15)
        kill.assert_not_called()
        self.assertEqual(family.known, {10: 'original'})

    def test_cleanup_does_not_say_done_when_identity_recheck_fails(self):
        atomic_json(self.directory / 'state.json', dict(id=self.job, status='failed'))
        atomic_json(self.directory / 'processes.json', {'known': {'10': 'original'}})
        rows = {10: dict(parent=1, group=10, born='original', state='S'),
                11: dict(parent=10, group=11, born='child', state='S')}
        with patch.object(recovery, 'snapshot', side_effect=[rows, rows, ProcessInspectionUnavailable('timeout')]), patch.object(recovery.os, 'kill') as kill:
            with self.assertRaisesRegex(StudioError, 'Cleanup is incomplete'): recovery.cleanup_job(self.job)
        kill.assert_not_called()
        self.assertEqual(self.state()['status'], 'stopping')
        self.assertIn('11', json.loads((self.directory / 'processes.json').read_text())['known'])
        self.assertTrue(self.state()['monitoring_warning'])

    def test_initial_recovery_failure_does_not_clear_job(self):
        with patch.object(recovery, 'snapshot', side_effect=ProcessInspectionUnavailable('timeout')):
            with self.assertRaisesRegex(StudioError, 'not been declared complete'): recovery.inspect_job(self.job)
        self.assertEqual(self.state()['status'], 'running')

if __name__ == '__main__': unittest.main()
