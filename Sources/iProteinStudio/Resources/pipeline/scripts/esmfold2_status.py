"""Cheap launch-time component detection; installation verifies file hashes."""
import json
from pathlib import Path
import sys


def detect(root):
    root = Path(root)
    assets = json.loads(Path(__file__).with_name('runtime_assets.json').read_text())['assets']
    shared = False
    for key in ('esmfold2', 'esmfold2_full', 'esmfold2_fast'):
        try:
            receipt = json.loads((root / 'receipts' / (key + '.json')).read_text())
            base = root / receipt['runtime_path']
            ok = (receipt.get('complete') is True and receipt.get('portable') is True
                  and (base / 'python/bin/python3').is_file()
                  and (root / 'venvs/NanoHunter_esmfold2/bin/python').is_file()
                  and all(receipt.get('assets', {}).get(a['path']) == a['sha256']
                          and (root / a['path']).is_file() and (root / a['path']).stat().st_size > 0
                          for a in assets[key]))
        except (OSError, ValueError, KeyError): ok = False
        if key == 'esmfold2': shared = ok
        else: ok = ok and shared
        print('NHSTATE|' + key + ('|ok|Verified portable ESMFold2 assets' if ok else '|missing|Install or repair ESMFold2 in Engines'), flush=True)


if __name__ == '__main__': detect(sys.argv[1])
