#!/usr/bin/env python3
"""Install the pinned experimental NESSO runtime, separately from folding engines."""
import argparse
import json
import os
from pathlib import Path
import platform
import shutil
import subprocess
import sys

from nesso_contract import ASSETS, VERSION, expected_assets, installation, protocol, sha256, validate_installation


def run(argv, **kwargs):
    subprocess.run([str(a) for a in argv], check=True, **kwargs)


def reuse_esm_asset(root, remote, checksum, destination):
    """Reuse exact HF assets, never a different ESM architecture or environment.

    Copy into NESSO's owned directory so repairing another engine cannot change
    NESSO's frozen runtime. APFS may share copy-on-write storage independently.
    """
    if destination.is_file() and sha256(destination) == checksum:
        return True
    hf_home = Path(os.environ.get('HF_HOME', str(Path(os.environ.get('XDG_CACHE_HOME', str(Path.home() / '.cache'))) / 'huggingface')))
    caches = [Path(os.environ.get('HF_HUB_CACHE', str(hf_home / 'hub'))),
              Path(root) / 'cache/huggingface/hub']
    repo = 'models--' + protocol()['assets']['esm_repository'].replace('/', '--')
    for cache in dict.fromkeys(caches):
        for source in sorted((cache / repo / 'snapshots').glob('*/' + remote)):
            if not source.is_file() or sha256(source) != checksum:
                continue
            destination.parent.mkdir(parents=True, exist_ok=True)
            pending = destination.with_name(destination.name + '.reuse-part')
            shutil.copyfile(source, pending)
            if sha256(pending) != checksum:
                pending.unlink()
                raise ValueError('Cached ESM asset changed during copy: ' + remote)
            pending.replace(destination)
            print('Reused checksum-verified ESM-2 asset: ' + remote, flush=True)
            return True
    return False


def install(root, python, uv):
    if platform.system() != 'Darwin' or platform.machine() != 'arm64':
        raise ValueError('NESSO requires Apple-Silicon macOS')
    base = installation(root)
    if (base / 'receipt.json').exists():
        validate_installation(root)
        print('NHSTATE|nesso|ok|NESSO-1 native MPS (experimental)', flush=True)
        return
    base.mkdir(parents=True, exist_ok=True)
    p = protocol()
    source = base / 'source'
    if not source.exists():
        run(['git', 'clone', '--no-checkout', p['upstream']['repository'], source])
    # Only this incomplete install's private checkout is reset; no shared source.
    run(['git', 'checkout', '--detach', '--force', p['upstream']['commit']], cwd=source)
    for name, key in [('LICENSE','license_sha256'), ('nesso/main.py','main_py_sha256'), ('nesso/model/models/nesso1.py','nesso1_py_sha256')]:
        if sha256(source / name) != p['upstream'][key]:
            raise ValueError('NESSO patch preimage mismatch: ' + name)
    run(['git', 'apply', '--check', ASSETS / 'nesso_mps.patch'], cwd=source)
    run(['git', 'apply', ASSETS / 'nesso_mps.patch'], cwd=source)
    venv = base / 'venv'
    if not venv.exists():
        run([uv, 'venv', '--python', python, venv])
    executable = venv / 'bin/python'
    run([uv, 'pip', 'sync', '--python', executable, '--require-hashes', '--only-binary', ':all:', ASSETS / 'requirements.lock'])
    run([uv, 'pip', 'install', '--python', executable, '--no-deps', '--no-build-isolation', source])
    run([uv, 'pip', 'check', '--python', executable])
    run([executable, '-c', "import platform,torch; assert platform.machine()=='arm64'; assert torch.backends.mps.is_built(); import nesso,transformers"])
    # Downloads are resumable and only become visible after digest verification.
    downloader = Path(__file__).resolve().parent.parent / 'download_verified.py'
    for name, checksum in expected_assets().items():
        if name.startswith('esm/'):
            repository, revision, remote = p['assets']['esm_repository'], p['assets']['esm_commit'], name[4:]
            if reuse_esm_asset(root, remote, checksum, base / name):
                continue
        else:
            repository, revision = 'recursionpharma/nesso', p['assets']['nesso_hf_commit']
            remote = 'v1.0.0/' + name[6:] if name.startswith('model/') else name
        url = f'https://huggingface.co/{repository}/resolve/{revision}/{remote}'
        run([executable, downloader, '--url', url, '--sha256', checksum, '--output', base / name,
             '--label', 'NESSO ' + name, '--progress-key', 'nesso', '--progress-start', '82', '--progress-end', '90'])
    files = [base / name for name in expected_assets()]
    # Freeze all runtime package code, not only the two patched files.
    files += sorted((venv / 'lib').glob('python*/site-packages/nesso/**/*.py'))
    files += sorted((venv / 'lib').glob('python*/site-packages/transformers/**/*.py'))
    saved = dict(version=VERSION, protocol_sha256=sha256(ASSETS/'protocol.json'),
                 lock_sha256=sha256(ASSETS/'requirements.lock'), patch_sha256=sha256(ASSETS/'nesso_mps.patch'),
                 files={str(f.relative_to(base)):dict(sha256=sha256(f), size=f.stat().st_size) for f in files})
    pending = base / 'receipt.json.part'
    pending.write_text(json.dumps(saved, indent=2) + '\n')
    pending.replace(base / 'receipt.json')
    validate_installation(root)
    print('NHSTATE|nesso|ok|NESSO-1 native MPS (experimental)', flush=True)


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--root', type=Path, required=True)
    parser.add_argument('--python', type=Path)
    parser.add_argument('--uv', type=Path)
    parser.add_argument('--detect', action='store_true')
    args = parser.parse_args()
    if args.detect:
        try:
            validate_installation(args.root, full=False)
            print('NHSTATE|nesso|ok|NESSO-1 native MPS (experimental; full hashes checked at preflight)')
        except (ValueError, OSError, KeyError, TypeError) as e:
            state = 'incomplete' if installation(args.root).exists() else 'missing'
            print(f'NHSTATE|nesso|{state}|{e}')
    else:
        if not args.python or not args.uv:
            parser.error('--python and --uv are required for installation')
        install(args.root.resolve(), args.python, args.uv)
