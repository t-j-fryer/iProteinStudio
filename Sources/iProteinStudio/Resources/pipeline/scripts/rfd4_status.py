"""Cheap detection; the installer and job preflight verify executable bytes."""
import json
from pathlib import Path
import sys


def detect(root):
    root = Path(root)
    try:
        assets = json.loads(Path(__file__).with_name('runtime_assets.json').read_text())['assets']['rfd4']
        receipt = json.loads((root / 'receipts/rfd4.json').read_text())
        runtime = root / receipt['runtime_path']
        ok = (receipt.get('complete') is True and receipt.get('portable') is True
              and (runtime / 'runtime.json').is_file()
              and (root / 'venvs/NanoHunter_rfd4/bin/python').is_file()
              and all(receipt.get('assets', {}).get(a['path']) == a['sha256']
                      and (root / a['path']).is_file() and (root / a['path']).stat().st_size > 0 for a in assets))
    except (OSError, ValueError, KeyError): ok = False
    print('NHSTATE|rfd4|' + ('ok|Verified portable RFD4 runtime and weights' if ok else
                           'missing|Install or repair the RFD4 runtime in Engines'))


if __name__ == '__main__': detect(sys.argv[1])
