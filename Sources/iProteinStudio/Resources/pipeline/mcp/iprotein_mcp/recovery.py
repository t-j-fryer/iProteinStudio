"""Conservative recovery of one job; never delete locks, runtimes or results."""
import fcntl
import os
import signal
import time

from .common import StudioError, agent_root, atomic_json, load_json, utc_now
from .process_tree import snapshot


def _records(job_id):
    from .broker import state_path
    path = state_path(job_id)
    if not path.is_file():
        raise StudioError('This job no longer exists in the registry.')
    state = load_json(path)
    directory = path.parent
    ready = load_json(directory / 'worker_ready.json') if (directory / 'worker_ready.json').is_file() else {}
    receipt = load_json(directory / 'processes.json') if (directory / 'processes.json').is_file() else {}
    return state, ready, receipt


def owned_processes(receipt, rows):
    known = {int(pid): born for pid, born in receipt.get('known', {}).items()}
    owned = {pid for pid, born in known.items() if pid in rows and rows[pid]['born'] == born
             and not rows[pid]['state'].startswith('Z') and pid > 1 and pid != os.getpid()}
    # Adopt descendants only from an identity-verified live parent. No process
    # group guessing, command-name matching, or inference from an open lock file.
    while True:
        children = {pid for pid, row in rows.items() if row['parent'] in owned
                    and not row['state'].startswith('Z') and pid > 1 and pid != os.getpid()}
        if children <= owned:
            break
        owned |= children
    return {pid: rows[pid]['born'] for pid in owned}


def _lock_busy():
    path = agent_root() / 'execution.lock'
    if not path.exists():
        return False
    with path.open('a+') as handle:
        try:
            fcntl.flock(handle, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            return True
        finally:
            # Unlocking this handle cannot release a different process's lease.
            fcntl.flock(handle, fcntl.LOCK_UN)
    return False


def inspect_job(job_id):
    state, ready, receipt = _records(job_id)
    rows = snapshot()
    worker = rows.get(int(state.get('pid') or 0))
    present = bool(worker and not worker['state'].startswith('Z'))
    verified = bool(present and ready.get('pid') == state.get('pid') and
                    ready.get('born') and ready['born'] == worker['born'])
    unknown_worker = bool(present and (ready.get('pid') != state.get('pid') or not ready.get('born')))
    owned = owned_processes(receipt, rows)
    busy = _lock_busy()
    active = state.get('status') in {'queued', 'running', 'stopping'}
    if verified:
        action = 'stop' if active and state.get('cancellation_contract') == 1 else 'none'
        message = ('The job worker is still active. Stop will request cancellation and keep saved results.'
                   if action == 'stop' else 'The worker is still alive. Cleanup will not stop an unverified or incompatible worker.')
    elif unknown_worker:
        action = 'none'
        message = 'This older job has no saved worker identity. Save your work and restart your Mac if the queue remains blocked; Studio cannot safely stop this process automatically.'
    elif owned:
        action = 'cleanup'
        message = f'{len(owned)} leftover job process(es) can be stopped safely. Saved inputs, results and checkpoints will be kept.'
    elif active:
        action = 'cleanup'
        message = 'The job worker has exited. Clear its active status while keeping all saved files.'
    else:
        action = 'none'
        message = 'No recorded job processes remain. No cleanup is needed for this job.'
    if busy and not verified and not owned:
        message += ' The execution lock is in use; it may belong to another job. If no other job is running, save your work and restart your Mac to clear unidentifiable older processes.'
    if not ready.get('born'):
        message += ' To use the latest worker fixes, create a new submission rather than resuming this older saved job.'
    return dict(job_id=job_id, action=action, message=message, process_ids=sorted(owned),
                worker_alive=verified or unknown_worker, execution_lock_busy=busy,
                identity_records_available=bool(receipt.get('known')), checked_at=utc_now())


def cleanup_job(job_id):
    from .broker import registry_lock, cancel_job, state_path, _update
    # Serialize with new submissions and Resume throughout the short cleanup.
    with registry_lock():
        report = inspect_job(job_id)
        if report['action'] == 'stop':
            cancel_job(job_id)
            report['message'] = 'Stop requested. Wait for cancellation, then check again if the job still needs attention.'
            report['action'] = 'none'
            return report
        if report['action'] != 'cleanup':
            return report
        state, ready, receipt = _records(job_id)
        known = dict(receipt.get('known', {}))
        atomic_json(state_path(job_id).parent / 'cancel.json', {'requested_at': utc_now()})
        _update(job_id, status='stopping', stage='recovery', message='Cleaning up this job’s recorded processes; saved files are kept.')
        for sig, grace in ((signal.SIGTERM, 3.), (signal.SIGKILL, 2.)):
            deadline = time.monotonic() + grace
            sent = set()
            while True:
                live = owned_processes({'known': known}, snapshot())
                known.update({str(pid): born for pid, born in live.items()})
                for pid, born in live.items():
                    if (pid, born) in sent:
                        continue
                    # Recheck identity immediately before every signal.
                    row = snapshot().get(pid)
                    if row and row['born'] == born:
                        try:
                            os.kill(pid, sig)
                        except ProcessLookupError:
                            pass
                    sent.add((pid, born))
                if not live or time.monotonic() >= deadline:
                    break
                time.sleep(.1)
            if not live:
                break
        receipt.update(known=known, recovered_at=utc_now())
        atomic_json(state_path(job_id).parent / 'processes.json', receipt)
        remaining = owned_processes(receipt, snapshot())
        if remaining:
            _update(job_id, status='stopping', message='A recorded process has not exited. Save your work and restart your Mac; Studio has kept the lock and saved files.')
        else:
            _update(job_id, status='cancelled', stage='cancelled', finished_at=utc_now(),
                    message='Job cleanup finished. Saved inputs, results and checkpoints were kept.')
        atomic_json(state_path(job_id).parent / 'recovery.json',
                    dict(at=utc_now(), recorded_pids=sorted(map(int, known)), remaining_pids=sorted(remaining)))
        report = inspect_job(job_id)
        if remaining:
            report.update(action='none', message='A recorded process has not exited after cleanup. Save your work and restart your Mac. Saved files and the execution lock were kept.')
        return report
