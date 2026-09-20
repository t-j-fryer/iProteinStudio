"""Compare saved parser tensors without invoking an engine or changing raw data."""
import json
from pathlib import Path
import numpy as np
from worker import atomic

def audit(run):
    progress=json.loads((run/'progress.json').read_text())
    if not all(k in progress for k in ('reference','variant')):return None
    rows=[]
    for index,(a,b) in enumerate(zip(*[json.loads((Path(progress[k])/'result.json').read_text())['rows'] for k in ('reference','variant')],strict=True)):
        a,b=[Path(p).parent/'prediction/processed/structures' for p in (a,b)]
        a,b=[np.load(next(p.glob('*.npz'))) for p in (a,b)]
        equal=a.files==b.files and all(np.array_equal(a[k],b[k]) for k in a.files)
        differences=[k for k in a.files if not np.array_equal(a[k],b[k])]
        rows.append(dict(index=index,exact=equal,different_arrays=differences))
    result=dict(all_exact=all(r['exact'] for r in rows),rows=rows)
    atomic(run/'preprocessing_audit.json',result);return result

if __name__=='__main__':
    root=Path(__file__).resolve().parents[3]/'Validation/output/apple_runtime_kernels_v3'
    for run in sorted(root.glob('nesso_*')):
        if (run/'completed.json').exists() and (run/'progress.json').exists():
            result=audit(run)
            if result:print(run.name,result['all_exact'])
