#!/usr/bin/env python3
"""Durably monitor already-submitted jobs, then audit and summarize their outputs.

This process never launches, resumes, cancels, or changes scientific settings.
Broker status queries retain the broker's standard stale-worker metadata recovery.
"""
import argparse
import fcntl
import json
import os
import subprocess
import sys
import time
from pathlib import Path
from campaign import base, HERE


def worker():
    output = base.OUTPUT / 'analysis/full'
    output.mkdir(parents=True, exist_ok=True)
    with (output / 'monitor.lock').open('a+') as lock:
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        while True:
            states = base.status('full')
            progress = {arm: {key: state.get(key) for key in
                             ('id', 'status', 'error', 'message', 'finished_at')}
                        for arm, state in states.items()}
            base.atomic_json(output / 'monitor_status.json',
                             {'stage': 'waiting', 'jobs': progress, 'pid': os.getpid()})
            print(json.dumps(progress), flush=True)
            if all(state['status'] in base.TERMINAL for state in states.values()):
                break
            time.sleep(30)
        if any(state['status'] != 'completed' for state in states.values()):
            base.atomic_json(output / 'monitor_status.json',
                             {'stage': 'job_failed', 'jobs': progress, 'status_detail': 'status_full.json'})
            return 1
        # The same read bridge function used by the MCP results_overview tool.
        sys.path.insert(0, str(base.STUDIOCTL.parent))
        from iprotein_mcp.catalog import results_overview
        for arm in states:
            overview = results_overview(f'{base.PROJECT}/full__{arm}', False, 100)
            base.atomic_json(output / f'overview_{arm}.json', overview)
        python = base.RUNTIME / 'venvs/NanoHunter_protenix/bin/python'
        environment = dict(os.environ, MPLCONFIGDIR=str(output / '.mplconfig'))
        subprocess.run([str(python), str(HERE / 'audit.py'), '--root', str(base.OUTPUT),
                        '--phase', 'full'], cwd=base.ROOT, env=environment, check=True)
        gate = json.loads((output / 'smoke_passed.json').read_text())
        if not gate.get('passed'):
            base.atomic_json(output / 'monitor_status.json', {'stage': 'audit_failed'})
            return 1
        subprocess.run([sys.executable, str(HERE / 'summary.py'), '--root', str(base.OUTPUT)],
                       cwd=base.ROOT, check=True)
        base.atomic_json(output / 'monitor_status.json',
                         {'stage': 'completed', 'report': str(output / 'comparison.md'),
                          'audited_structures': gate['audited_structures']})
    return 0


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--worker', action='store_true')
    args = parser.parse_args()
    os.environ['NANOHUNTER_ROOT'] = str(base.RUNTIME)
    if args.worker:
        try:
            return worker()
        except BlockingIOError:
            print('An existing monitor already holds the lock; leaving its records intact.')
            return 0
        except (Exception, SystemExit) as error:
            base.atomic_json(base.OUTPUT / 'analysis/full/monitor_status.json',
                             {'stage': 'monitor_error', 'error': str(error)})
            raise
    if not (base.OUTPUT / 'jobs_full.json').is_file():
        base.die('Submit and review full scientific jobs before starting the read/analysis monitor')
    output = base.OUTPUT / 'analysis/full'
    output.mkdir(parents=True, exist_ok=True)
    # Serialize launches until the new worker has acquired its own lifetime lock.
    with (output / 'monitor_launch.lock').open('a+') as launch_lock:
        fcntl.flock(launch_lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        with (output / 'monitor.lock').open('a+') as running_lock:
            try:
                fcntl.flock(running_lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
            except BlockingIOError:
                print('An existing monitor is running; leaving its records intact.')
                return 0
        with (output / 'monitor.log').open('a') as log:
            process = subprocess.Popen(['/usr/bin/caffeinate', '-dimsu', sys.executable,
                                        str(Path(__file__).resolve()), '--worker'],
                                       cwd=base.ROOT, stdout=log, stderr=subprocess.STDOUT,
                                       start_new_session=True)
        for _ in range(20):
            time.sleep(0.25)
            if process.poll() is not None:
                raise RuntimeError('Monitor exited during launch; inspect monitor.log')
            state_path = output / 'monitor_status.json'
            if state_path.exists() and json.loads(state_path.read_text()).get('pid') == process.pid:
                break
        else:
            raise RuntimeError('Monitor did not acknowledge startup; inspect monitor.log before retrying')
        receipt = {'pid': process.pid, 'log': str(output / 'monitor.log'),
                   'purpose': 'Monitor submitted jobs; then results_overview, full audit and summary only'}
        base.atomic_json(output / 'monitor_launch.json', receipt)
        print(json.dumps(receipt, indent=2))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
