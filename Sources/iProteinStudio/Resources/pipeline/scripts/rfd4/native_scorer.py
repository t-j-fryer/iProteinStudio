"""Synchronous oracle process; the caller retains Studio's shared lease."""
import json
import os
from pathlib import Path
import sys
import time
import traceback
from .contract import atomic, seal, sha, verify


def main(path):
    cfg = json.loads(Path(path).read_text()); queue = Path(cfg['score_queue'])
    sys.path.insert(0, str(Path(os.environ['NANOHUNTER_ROOT']) / 'rfd3_scripts'))
    if cfg['settings']['task'] == 'ligand':
        from .ligand_score import Engine
    else:
        from .search_engine import Engine
        from .msas import resolve
        cfg = resolve(cfg)
    engine = Engine(cfg)
    atomic(queue / 'ready.json', dict(pid=os.getpid()))
    try:
        while not (queue / 'stop.json').exists():
            for request_path in sorted((queue / 'requests').glob('*.json')):
                response = queue / 'responses' / request_path.name
                if response.exists(): continue
                try:
                    request = json.loads(request_path.read_text())
                    if cfg['settings']['task'] == 'ligand':
                        rows = engine.score(request['key'], request['structures'])
                    else:
                        rows = {}
                        for name, structure in request['structures'].items():
                            unit = Path(cfg['output']) / 'native_predictions' / request['key'] / name
                            unit.mkdir(parents=True, exist_ok=True)
                            receipt = unit / 'completed.json'
                            if receipt.exists(): row = verify(receipt)
                            else:
                                from .search_engine import canonical_protein
                                structure = str(canonical_protein(structure, cfg, unit / 'roles.pdb'))
                                proposal = dict(id=name, sequence_seed=42, predictor_seed=42)
                                parent = dict(structure=structure, structure_sha256=sha(structure))
                                row, artifacts = engine.evaluate(proposal, parent, unit, native=True)
                                seal(receipt, row, artifacts)
                            rows[name] = dict(row, metrics={'protein.ipsae_min':row['score']}, receipts=[str(receipt)])
                    atomic(response, dict(ok=True, rows=rows))
                except Exception:
                    atomic(response, dict(ok=False, error=traceback.format_exc()))
                    raise
            time.sleep(.1)
    finally: engine.close()
