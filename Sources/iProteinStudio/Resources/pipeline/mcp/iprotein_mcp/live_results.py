"""Read display-only native completion receipts; never advance or resume a job."""
from __future__ import annotations
import json
import re
from pathlib import Path


def records(root):
    root = Path(root).resolve()
    def safe(value):
        if not isinstance(value, str) or Path(value).is_absolute(): raise ValueError('relative artifact required')
        path = (root / value).resolve()
        path.relative_to(root)
        if not path.is_file(): raise ValueError('missing artifact')
        return path
    rows = []
    for receipt in sorted((root / '.studio_live_results').glob('*.json')):
        try:
            receipt.resolve().relative_to(root)
            doc = json.loads(receipt.read_text())
            if doc['schema'] != 1: continue
            for item in doc['artifacts']:
                try:
                    structure = safe(item['structure'])
                    stat = structure.stat()
                    if stat.st_size != item['size'] or str(stat.st_mtime_ns) != item['mtime_ns']: continue
                    confidence = safe(item['confidence']) if item.get('confidence') else None
                    metrics = json.loads(confidence.read_text()) if confidence else {}
                    if not isinstance(metrics, dict) or (not confidence and not doc.get('generation')): continue
                    engine = doc['engine']
                    if engine == 'protenix':
                        engine = next((part for part in Path(item['structure']).parts if part in
                                       {'protenix-mini', 'protenix-v2', 'protenix-constraint-v0.5'}), engine)
                    row = dict(job=doc['job'], predictor=engine, structure_path=item['structure'],
                               confidence_json=item.get('confidence'), sample=item['sample'],
                               generation=doc.get('generation', False), score_status='awaiting_checks',
                               is_hit=None, metrics=metrics)
                    row.update({k: v for k, v in metrics.items() if k not in row and isinstance(v, (int, float))})
                    rows.append(row)
                except (OSError, ValueError, KeyError, TypeError): continue
        except (OSError, ValueError, KeyError, TypeError): continue
    return rows


def iterative_rows(root):
    for raw in records(root):
        path = raw['structure_path']
        if raw['generation'] or 'nesso_verification/' in path: continue
        text = raw['job'] + '/' + path
        run, cycle = re.search(r'run_(\d+)', text), re.search(r'(?:cycle|post)_(\d+)', text)
        if not run or not cycle: continue
        row = dict(raw, run=str(int(run[1])), cycle=str(int(cycle[1])),
                   stage='post' if '/post_' in path else 'design',
                   binder_only='/binder_alone/' in path)
        row.update({key: str(value) for key, value in raw['metrics'].items() if isinstance(value, (int, float))})
        yield row
