"""Persistent CPU interpreter for upstream Ligand/Soluble/ProteinMPNN.

Keep imports and checkpoint tensors warm. Execute upstream main unchanged for
each request, including model initialization and all three RNG resets. This is
deliberately NOT a replacement sampler or a change to per-proposal seeds.
Workers belong to the enclosing campaign PID and never survive its exit.
"""
import contextlib
import fcntl
import json
import os
from pathlib import Path
import runpy
import subprocess
import sys
import time
import traceback
import uuid


def atomic(path, value):
    tmp = path.with_suffix('.part')
    tmp.write_text(json.dumps(value))
    tmp.replace(path)


def alive(pid):
    try:
        os.kill(int(pid), 0)
        return True
    except ProcessLookupError:
        return False


def serve(directory, owner, script):
    directory, script = Path(directory), Path(script).resolve()
    os.chdir(script.parent)
    sys.path.insert(0, str(script.parent))
    import torch
    if torch.cuda.is_available():
        raise RuntimeError('This worker is qualified for CPU MPNN only')
    original_load = torch.load
    checkpoints = {}

    def cached_load(path, *args, **kwargs):
        # Non-path loads or unusual options retain the upstream behavior.
        if not isinstance(path, (str, Path)):
            return original_load(path, *args, **kwargs)
        p = Path(path).resolve()
        stat = p.stat()
        key = (str(p), stat.st_size, stat.st_mtime_ns, repr(args), repr(sorted(kwargs.items())))
        if key not in checkpoints:
            checkpoints.clear()  # bounded: one selected MPNN checkpoint
            checkpoints[key] = original_load(path, *args, **kwargs)
        return checkpoints[key]

    torch.load = cached_load
    atomic(directory / 'ready.json', dict(pid=os.getpid(), owner=owner, device='cpu', script=str(script)))
    while alive(owner) and not (directory / 'STOP').exists():
        requests = sorted(directory.glob('request-*.json'))
        for path in requests:
            result = path.with_name(path.stem + '.result.json')
            if '.result' in path.stem or result.exists():
                continue
            request = json.loads(path.read_text())
            started = time.perf_counter()
            rc = 0
            with Path(request['log']).open('w') as log, contextlib.redirect_stdout(log), contextlib.redirect_stderr(log):
                old_argv = sys.argv
                try:
                    sys.argv = [str(script), *request['arguments']]
                    runpy.run_path(str(script), run_name='__main__')
                except SystemExit as exc:
                    rc = int(exc.code or 0) if isinstance(exc.code, (int, type(None))) else 1
                except Exception:
                    traceback.print_exc()
                    rc = 1
                finally:
                    sys.argv = old_argv
            atomic(result, dict(returncode=rc, seconds=time.perf_counter()-started, pid=os.getpid(), device='cpu'))
        time.sleep(.05)


def submit(directory, owner, script, arguments):
    directory = Path(directory).resolve()
    directory.mkdir(parents=True, exist_ok=True)
    with (directory / 'startup.lock').open('a') as lock:
        fcntl.flock(lock, fcntl.LOCK_EX)
        ready = directory / 'ready.json'
        state = json.loads(ready.read_text()) if ready.exists() else {}
        if not state or not alive(state['pid']):
            ready.unlink(missing_ok=True)
            (directory / 'STOP').unlink(missing_ok=True)
            # A fresh session cannot replay requests left by a dead worker.
            session = directory / ('session-' + uuid.uuid4().hex)
            session.mkdir()
            with (session / 'worker.log').open('w') as log:
                worker = subprocess.Popen([sys.executable, __file__, 'serve', str(session), str(owner), str(script)], stdout=log, stderr=subprocess.STDOUT)
            deadline = time.monotonic() + 180
            while not (session / 'ready.json').exists():
                if worker.poll() is not None or time.monotonic() > deadline:
                    raise RuntimeError('MPNN worker failed to start; see ' + str(session / 'worker.log'))
                time.sleep(.1)
            state = json.loads((session / 'ready.json').read_text())
            state['session'] = str(session)
            atomic(ready, state)
        if state['owner'] != owner or Path(state['script']) != Path(script).resolve():
            raise ValueError('MPNN worker ownership/script mismatch')
    session = Path(state['session'])
    request = session / ('request-' + uuid.uuid4().hex + '.json')
    log = request.with_suffix('.log')
    atomic(request, dict(arguments=arguments, log=str(log)))
    result = request.with_name(request.stem + '.result.json')
    while not result.exists():
        if not alive(state['pid']) or not alive(owner):
            raise RuntimeError('MPNN worker stopped before completing request: ' + str(request))
        time.sleep(.05)
    print(log.read_text(), end='')
    return json.loads(result.read_text())


if __name__ == '__main__':
    if sys.argv[1] == 'serve':
        serve(sys.argv[2], int(sys.argv[3]), sys.argv[4])
    else:
        result = submit(sys.argv[2], int(sys.argv[3]), sys.argv[4], sys.argv[5:])
        print('MPNN_WORKER|' + json.dumps(result), flush=True)
        raise SystemExit(result['returncode'])
