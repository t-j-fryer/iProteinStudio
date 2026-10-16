import hashlib
import json
from pathlib import Path


def sha(path):
    h = hashlib.sha256()
    with Path(path).open('rb') as handle:
        for block in iter(lambda: handle.read(8 * 1024**2), b''):
            h.update(block)
    return h.hexdigest()


def save(path, value):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix('.tmp')
    tmp.write_text(json.dumps(value, indent=2, allow_nan=False) + '\n')
    tmp.replace(path)


def seal(directory, result):
    directory = Path(directory)
    save(directory/'completed.json', dict(result=result, files={
        str(p.relative_to(directory)): sha(p) for p in directory.rglob('*')
        if p.is_file() and p.name != 'completed.json'}))


def verified(directory):
    path = Path(directory)/'completed.json'
    if not path.exists():
        return None
    obj = json.loads(path.read_text())
    if not obj['files']:
        raise RuntimeError('Empty completion receipt')
    for rel, digest in obj['files'].items():
        if sha(path.parent/rel) != digest:
            raise RuntimeError(f'Changed completed output: {path.parent/rel}')
    return obj['result']
