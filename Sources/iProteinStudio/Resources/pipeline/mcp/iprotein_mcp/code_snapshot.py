"""Retain the adapter and bridge code accepted by a preflight plan."""
import json
import os
import shutil
import uuid
from pathlib import Path
from .common import canonical_digest, file_digest, StudioError

NAMES = ('scripts', 'rfd3_scripts', 'rfd3_overlay', 'nanohunter_run.sh', 'examples', 'locks', 'PIPELINE_VERSION', 'THIRD_PARTY_NOTICES.md')

def capture(root, store):
    root, store = Path(root), Path(store)
    sources = {name: root / name for name in NAMES if (root / name).exists()}
    sources['mcp'] = Path(__file__).resolve().parents[1]
    files = {}
    for name, source in sources.items():
        for p in ([source] if source.is_file() else sorted(source.rglob('*'))):
            if p.is_file() and '__pycache__' not in p.parts and '.git' not in p.parts and p.suffix != '.pyc':
                rel = name if source.is_file() else name + '/' + str(p.relative_to(source))
                files[rel] = {'source': p, 'sha256': file_digest(p)}
    bridge = Path(__file__).resolve().parents[1]
    support = bridge / 'runtime_support'
    if not support.is_dir(): support = bridge.parent / 'scripts'
    for name in ('runtime_package.py', 'runtime_transaction.py', 'runtime_view.py', 'engine_registry.py', 'engine_registry.json'):
        p = support / name
        if p.is_file(): files['mcp/runtime_support/' + name] = {'source': p, 'sha256': file_digest(p)}
    inventory = {name: item['sha256'] for name, item in files.items()}
    sha = canonical_digest(inventory)
    destination = store / sha
    spec = dict(path=str(destination), sha256=sha, entries=sorted(sources))
    if not destination.exists():
        stage = store / ('.stage-' + uuid.uuid4().hex)
        stage.mkdir(parents=True)
        try:
            for name, item in files.items():
                target = stage / name
                target.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(item['source'], target)
                if file_digest(target) != item['sha256']:
                    raise StudioError('Adapter changed during preflight; retry the request.')
            (stage / 'code.json').write_text(json.dumps(inventory, sort_keys=True) + '\n')
            try: os.rename(stage, destination)
            except OSError:
                if not destination.exists(): raise
        finally:
            if stage.exists(): shutil.rmtree(stage)
    verify(spec)
    return spec

def verify(spec):
    base = Path(spec['path'])
    inventory = json.loads((base / 'code.json').read_text())
    if canonical_digest(inventory) != spec['sha256']:
        raise StudioError('Retained adapter inventory changed.')
    actual = {str(p.relative_to(base)) for p in base.rglob('*') if p.is_file() and p.name != 'code.json' and '__pycache__' not in p.parts}
    if actual != set(inventory): raise StudioError('Retained adapter file inventory changed.')
    for name, expected in inventory.items():
        if file_digest(base / name) != expected:
            raise StudioError('Retained adapter changed: ' + name)
    return inventory

def provenance(root, spec, originals):
    root = Path(root).resolve()
    result = []
    for item in originals:
        try: rel = Path(item['path']).relative_to(root)
        except ValueError: rel = None
        if rel and rel.parts[0] in spec['entries']:
            frozen = Path(spec['path']) / rel
            if not frozen.is_file() or file_digest(frozen) != item['sha256']:
                raise StudioError('Adapter changed during preflight; retry the request.')
            result.append(dict(path=str(frozen), sha256=item['sha256']))
        else: result.append(item)
    return result
