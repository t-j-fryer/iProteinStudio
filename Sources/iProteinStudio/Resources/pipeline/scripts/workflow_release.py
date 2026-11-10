"""Verify shipped adapter identity and refuse workflow release downgrades."""
import argparse
import hashlib
import json
from pathlib import Path

NAME = 'WORKFLOW_RELEASE.json'
REQUIRED = {'scripts/esmfold2_predict.py', 'scripts/rfd4/metal.py',
            'scripts/rfd4/triangle_metal.py'}


def read(root, verify=True):
    root = Path(root)
    path = root / NAME
    if not path.exists():
        return None  # Historical snapshots remain readable and resumable.
    value = json.loads(path.read_text())
    if value.get('schema') != 1 or type(value.get('generation')) is not int or value['generation'] < 1:
        raise ValueError('Invalid workflow release manifest')
    files = value.get('files', {})
    if set(files) != REQUIRED:
        raise ValueError('Workflow release manifest must identify every optimized adapter')
    for name, expected in files.items():
        if not isinstance(expected, str) or len(expected) != 64:
            raise ValueError('Invalid workflow adapter checksum: ' + name)
        if verify:
            file = root / name
            if not file.is_file() or hashlib.sha256(file.read_bytes()).hexdigest() != expected:
                raise ValueError('Workflow adapter differs from its release: ' + name +
                                 '. Reinstall the matching Studio release before starting new work.')
    return value


def check_update(source, installed):
    incoming = read(source)
    current = read(installed, verify=False)
    if current and (not incoming or current['generation'] > incoming['generation']):
        raise ValueError('This Studio copy contains older workflows than the installed release. '
                         'Update the app or use the matching headless installer; installed workflows were preserved.')
    if current and incoming and current['generation'] == incoming['generation'] and current != incoming:
        raise ValueError('Different workflow contents use the same release generation. '
                         'Install a newer, consistently packaged Studio release.')
    return incoming


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('pipeline', type=Path)
    args = parser.parse_args()
    value = read(args.pipeline)
    if value is None:
        parser.error('Workflow release manifest is missing')
    print(json.dumps(dict(verified=True, **value), indent=2, sort_keys=True))
