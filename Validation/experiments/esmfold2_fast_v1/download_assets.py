"""Fetch the pinned, pre-bundling Fast release used with our reference runtime."""
import hashlib
import json
from pathlib import Path
import urllib.request

ROOT = Path(__file__).resolve().parents[3]
OUT = ROOT / 'Validation/output/esmfold2_fast_v1'
REV = 'c6c7958d63f5f2f1f0fed0bb9462316f8ccceea6'

def main():
    dest = OUT / 'assets/ESMFold2-Fast'
    dest.mkdir(parents=True, exist_ok=True)
    api = 'https://huggingface.co/api/models/biohub/ESMFold2-Fast'
    metadata = json.load(urllib.request.urlopen(api + '/tree/' + REV))
    (OUT/'remote_tree.json').write_text(json.dumps(metadata, indent=2)+'\n')
    records = []
    for name in ['config.json', 'README.md', 'model.safetensors']:
        path = dest/name
        url = f'https://huggingface.co/biohub/ESMFold2-Fast/resolve/{REV}/{name}'
        meta = next(v for v in metadata if v['path'] == name)
        if not path.exists():
            print('Downloading', name, flush=True)
            with urllib.request.urlopen(url) as response, path.with_suffix(path.suffix+'.part').open('wb') as f:
                while chunk := response.read(8*1024*1024):
                    f.write(chunk)
            path.with_suffix(path.suffix+'.part').replace(path)
        digest = hashlib.file_digest(path.open('rb'), 'sha256').hexdigest()
        if path.stat().st_size != meta['size'] or ('lfs' in meta and digest != meta['lfs']['oid']):
            raise RuntimeError('Remote checksum/size mismatch: '+name)
        records.append(dict(path=str(path), sha256=digest, source=url, revision=REV))
        print(name, digest, flush=True)
    (OUT/'fast_inventory.json').write_text(json.dumps(records, indent=2)+'\n')

if __name__ == '__main__':
    main()
