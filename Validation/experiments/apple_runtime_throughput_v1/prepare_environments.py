#!/usr/bin/env python3
"""Clone isolated experimental venvs and replace only the candidate Torch wheel.

No installed Studio file or model weight is written. APFS clones are independent
files, not hard links. This is an experiment, not a relocatable release package.
"""
import argparse
import hashlib
import json
import os
from pathlib import Path
import subprocess
import urllib.request

REPO = Path(__file__).resolve().parents[3]


def sha(path):
    h = hashlib.sha256()
    with Path(path).open('rb') as f:
        for b in iter(lambda: f.read(8 * 1024 * 1024), b''):
            h.update(b)
    return h.hexdigest()


def seal(directory):
    directory = Path(directory)
    files = {}
    for p in sorted(directory.rglob('*')):
        if p.is_file() and '__pycache__' not in p.parts and p.suffix != '.pyc':
            files[str(p.relative_to(directory))] = sha(p)
    return {'root': str(directory.resolve()), 'files': files}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--root', type=Path, default=Path.home()/'.iproteinstudio')
    ap.add_argument('--output', type=Path, default=REPO/'Validation/output/apple_runtime_throughput_v1')
    args = ap.parse_args()
    out = args.output.resolve(); out.mkdir(parents=True, exist_ok=True)
    allowed = REPO/'Validation/output'
    if allowed not in out.parents:
        raise SystemExit('Experimental environments must be below Validation/output.')
    root = args.root.resolve()
    source = root/'venvs/NanoHunter_boltz'
    uv = root/'toolchains/uv/0.11.32/uv'
    env = dict(os.environ, UV_CACHE_DIR=str(out/'uv-cache'), UV_PYTHON_DOWNLOADS='never', PYTHONDONTWRITEBYTECODE='1')
    metadata = json.load(urllib.request.urlopen('https://pypi.org/pypi/torch/2.14.0/json', timeout=30))
    choices = [x for x in metadata['urls'] if 'cp311-cp311-macosx' in x['filename'] and 'arm64' in x['filename']]
    if len(choices) != 1:
        raise SystemExit('Expected exactly one CPython 3.11 Apple Silicon Torch 2.14 wheel.')
    wheel = choices[0]
    (out/'torch-wheel.json').write_text(json.dumps(wheel, indent=2)+'\n')
    wheel_path = out/wheel['filename']
    if not wheel_path.exists():
        partial = wheel_path.with_suffix('.part')
        with urllib.request.urlopen(wheel['url'], timeout=60) as r, partial.open('wb') as f:
            while chunk := r.read(8*1024*1024): f.write(chunk)
        if sha(partial) != wheel['digests']['sha256']:
            raise SystemExit('Downloaded wheel checksum mismatch')
        partial.replace(wheel_path)
    if sha(wheel_path) != wheel['digests']['sha256']:
        raise SystemExit('Cached wheel checksum mismatch')
    print('Verified candidate wheel:', wheel['filename'], flush=True)
    for name in ('boltz-torch213', 'boltz-torch214'):
        destination = out/'environments'/name
        receipt = out/(name+'.seal.json')
        if receipt.exists():
            print('Already prepared:', name, flush=True); continue
        if destination.exists():
            raise SystemExit(f'Incomplete environment retained for diagnosis: {destination}')
        subprocess.run([str(uv),'venv','--python',str(source/'bin/python'),str(destination)],env=env,check=True)
        source_site = source/'lib/python3.11/site-packages'
        dest_site = destination/'lib/python3.11/site-packages'
        subprocess.run(['/bin/cp','-cR',str(source_site)+'/.',str(dest_site)],check=True)
        if name.endswith('214'):
            req = out/'candidate-wheel.txt'
            req.write_text(f'torch @ {wheel_path.as_uri()} --hash=sha256:{wheel["digests"]["sha256"]}\n')
            subprocess.run([str(uv),'pip','install','--python',str(destination/'bin/python'),
                            '--no-deps','--require-hashes','--no-build','-r',str(req)],env=env,check=True)
        check = subprocess.run([str(uv),'pip','check','--python',str(destination/'bin/python')],env=env,capture_output=True,text=True)
        (out/(name+'.dependency-check.txt')).write_text(check.stdout+check.stderr)
        if check.returncode: raise SystemExit(check.stdout+check.stderr)
        result = seal(destination)
        receipt.write_text(json.dumps(result,indent=2)+'\n')
        print('Sealed:',name,len(result['files']),'files',flush=True)


if __name__ == '__main__': main()
