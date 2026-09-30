"""Serial governed acceptance; assets come from the broker's preserved runtime."""
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys
import time


def save(path, data):
    path = Path(path)
    temp = path.with_suffix('.part')
    temp.write_text(json.dumps(data, indent=2) + '\n')
    temp.replace(path)


def main():
    config = json.loads(Path(sys.argv[1]).read_text())
    output = Path(config['output'])
    frozen = Path(sys.argv[1]).parent
    root = output / 'runtime'
    root.mkdir(exist_ok=True)
    actual = Path(os.environ['NANOHUNTER_ROOT'])
    for name in ('models', 'venvs', 'src'):
        link = root / name
        if not link.exists(): link.symlink_to(actual / name, target_is_directory=True)
    for name, source in [('scripts', frozen / 'scripts'), ('rfd3_overlay', frozen / 'rfd3_overlay')]:
        link = root / name
        if not link.exists(): link.symlink_to(source, target_is_directory=True)
    for engine, runtime in config['engines'].items():
        dest = output / engine
        dest.mkdir(exist_ok=True)
        receipt = dest / 'complete.json'
        if receipt.exists():
            data = json.loads(receipt.read_text())
            if all(hashlib.sha256(Path(p).read_bytes()).hexdigest() == checksum for p, checksum in data['files'].items()):
                continue
            raise RuntimeError('Changed smoke output: ' + engine)
        log = dest / 'worker.log'
        env = dict(os.environ, NANOHUNTER_ROOT=str(root), PYTHONDONTWRITEBYTECODE='1',
                   PYTORCH_ENABLE_MPS_FALLBACK='0', NUMBA_CACHE_DIR=str(dest / 'numba'),
                   MPLCONFIGDIR=str(dest / 'mpl'), HF_HUB_OFFLINE='1', TRANSFORMERS_OFFLINE='1')
        started = time.time()
        save(output / 'active.json', dict(engine=engine, started=started, status='running'))
        with log.open('w') as stream:
            process = subprocess.run([str(root / 'venvs' / runtime / 'bin/python'), str(frozen / 'worker.py'),
                                      str(root), str(frozen / 'config.json'), engine, str(dest)],
                                     env=env, stdout=stream, stderr=subprocess.STDOUT)
        if process.returncode:
            save(output / 'active.json', dict(engine=engine, status='failed', returncode=process.returncode, log=str(log)))
            raise RuntimeError(f'{engine} failed; see {log}')
        if not receipt.exists(): raise RuntimeError('Missing audited receipt: ' + engine)
    save(output / 'active.json', dict(status='completed', engines=list(config['engines'])))


if __name__ == '__main__': main()
