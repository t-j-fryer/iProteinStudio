"""Job-specific recovery tests; never touch real Studio job state."""
import fcntl
import json
import os
from pathlib import Path
import signal
import subprocess
import sys
import tempfile
import time
import unittest
from unittest.mock import patch

MCP = Path(__file__).resolve().parents[1] / 'Sources/iProteinStudio/Resources/pipeline/mcp'
sys.path.insert(0, str(MCP))
from iprotein_mcp import broker, recovery
from iprotein_mcp.common import atomic_json
from iprotein_mcp.process_tree import snapshot


def row(born='same', parent=1, state='S'):
    return dict(born=born, parent=parent, group=10, state=state)


class RecoveryTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        self.job = 'job-recovery-fixture'
        self.directory = self.root / 'agent/jobs' / self.job
        self.directory.mkdir(parents=True)
        self.env = patch.dict(os.environ, NANOHUNTER_ROOT=str(self.root), IPROTEINSTUDIO_AGENT_ROOT=str(self.root / 'agent'))
        self.env.start()
        self.state = dict(id=self.job, status='failed', pid=None, worker_contract=2, cancellation_contract=1)
        self.save()

    def tearDown(self):
        self.env.stop(); self.tmp.cleanup()

    def save(self): atomic_json(self.directory / 'state.json', self.state)

    def test_ownership_excludes_reused_pids_and_unrelated_groups(self):
        receipt = {'known': {'10': 'same', '20': 'old'}}
        rows = {10: row(), 11: row(parent=10), 12: row(parent=11), 20: row('new'), 30: row()}
        self.assertEqual(set(recovery.owned_processes(receipt, rows)), {10, 11, 12})
        rows[10]['state'] = 'Z'
        self.assertEqual(recovery.owned_processes(receipt, rows), {})

    def test_reused_worker_pid_is_not_stopped(self):
        self.state['pid'] = 20; self.save()
        atomic_json(self.directory / 'worker_ready.json', {'pid': 20, 'born': 'old'})
        with patch.object(recovery, 'snapshot', return_value={20: row('new')}), patch.object(recovery.os, 'kill') as kill:
            report = recovery.cleanup_job(self.job)
        kill.assert_not_called()
        self.assertEqual(report['action'], 'none')

    def test_legacy_worker_is_never_guessed(self):
        self.state.update(pid=20, status='running'); self.save()
        with patch.object(recovery, 'snapshot', return_value={20: row()}), patch.object(recovery.os, 'kill') as kill:
            report = recovery.cleanup_job(self.job)
        kill.assert_not_called()
        self.assertEqual(report['action'], 'none')
        self.assertIn('restart', report['message'])

    def test_new_worker_readiness_race_does_not_clean_up_live_job(self):
        self.state.update(pid=20, status='queued'); self.save()
        atomic_json(self.directory / 'worker_ready.json', {'pid': 10, 'born': 'old'})
        with patch.object(recovery, 'snapshot', return_value={20: row()}):
            report = recovery.cleanup_job(self.job)
        self.assertEqual(report['action'], 'none')
        self.assertEqual(json.loads((self.directory / 'state.json').read_text())['status'], 'queued')

    def test_live_worker_uses_normal_stop(self):
        self.state.update(pid=20, status='running'); self.save()
        atomic_json(self.directory / 'worker_ready.json', {'pid': 20, 'born': 'same'})
        with patch.object(recovery, 'snapshot', return_value={20: row()}), patch.object(broker, 'cancel_job') as cancel:
            recovery.cleanup_job(self.job)
        cancel.assert_called_once_with(self.job)

    def test_stale_state_cleared_and_files_kept(self):
        self.state['status'] = 'running'; self.save()
        result = self.directory / 'result.cif'; result.write_text('preserved')
        with patch.object(recovery, 'snapshot', return_value={}):
            report = recovery.cleanup_job(self.job)
        self.assertEqual(json.loads((self.directory / 'state.json').read_text())['status'], 'cancelled')
        self.assertEqual(result.read_text(), 'preserved')
        self.assertTrue((self.directory / 'cancel.json').is_file())
        self.assertEqual(report['action'], 'none')

    def test_cleanup_rechecks_identity_before_signal(self):
        atomic_json(self.directory / 'processes.json', {'known': {'20': 'same'}})
        calls = 0
        def changing():
            nonlocal calls
            calls += 1
            return {20: row('same' if calls <= 2 else 'replacement')}
        with patch.object(recovery, 'snapshot', side_effect=changing), patch.object(recovery.os, 'kill') as kill:
            recovery.cleanup_job(self.job)
        kill.assert_not_called()

    def test_locked_file_is_kept_and_unknown_holder_not_killed(self):
        lock = self.root / 'agent/execution.lock'
        with lock.open('a+') as handle:
            fcntl.flock(handle, fcntl.LOCK_EX | fcntl.LOCK_NB)
            inode = lock.stat().st_ino
            with patch.object(recovery, 'snapshot', return_value={}), patch.object(recovery.os, 'kill') as kill:
                report = recovery.cleanup_job(self.job)
            self.assertTrue(report['execution_lock_busy'])
            self.assertEqual(lock.stat().st_ino, inode)
            kill.assert_not_called()

    def test_real_owned_child_terminated_and_unrelated_child_survives(self):
        owned = subprocess.Popen([sys.executable, '-c', 'import time; time.sleep(30)'], start_new_session=True)
        other = subprocess.Popen([sys.executable, '-c', 'import time; time.sleep(30)'], start_new_session=True)
        try:
            rows = snapshot()
            atomic_json(self.directory / 'processes.json', {'known': {str(owned.pid): rows[owned.pid]['born']}})
            report = recovery.cleanup_job(self.job)
            owned.wait(timeout=5)
            self.assertIsNone(other.poll())
            self.assertEqual(report['process_ids'], [])
            self.assertEqual(json.loads((self.directory / 'state.json').read_text())['status'], 'cancelled')
        finally:
            for process in (owned, other):
                if process.poll() is None: process.kill()
                process.wait()

    def test_resume_refuses_owned_survivor(self):
        atomic_json(self.directory / 'processes.json', {'known': {'20': 'same'}})
        with patch('iprotein_mcp.process_tree.snapshot', return_value={20: row()}), patch.object(broker, '_spawn') as spawn:
            with self.assertRaisesRegex(Exception, 'Check & clean up'):
                broker.resume_job(self.job)
        spawn.assert_not_called()

    def test_cli_log_view_is_bounded_and_recovery_check_is_json(self):
        (self.directory / 'pipeline.log').write_text(''.join(f'line {i}\n' for i in range(600)))
        command = [sys.executable, str(MCP / 'studioctl.py')]
        log = subprocess.run(command + ['job-log', self.job], capture_output=True, text=True, check=True)
        report = json.loads(log.stdout)
        self.assertEqual(len(report['lines']), 500)
        self.assertEqual(report['lines'][0], 'line 100')
        check = subprocess.run(command + ['job-recovery-check', self.job], capture_output=True, text=True, check=True)
        self.assertEqual(json.loads(check.stdout)['action'], 'none')
        invalid = subprocess.run(command + ['job-cleanup', '../outside'], capture_output=True, text=True)
        self.assertNotEqual(invalid.returncode, 0)


if __name__ == '__main__': unittest.main()
