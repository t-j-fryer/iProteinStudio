#!/usr/bin/env python3
"""Practical numerical gates; no assumption that baseline equals ground truth."""
import json
from pathlib import Path
import numpy as np


def compare(a, b, limits):
    if a['sequence'] != b['sequence'] or a['atom_identities'] != b['atom_identities']:
        return {'passed': False, 'failures': ['sequence/atom identity mismatch']}
    x, y = np.asarray(a['ca'], dtype=float), np.asarray(b['ca'], dtype=float)
    if x.shape != y.shape or not np.isfinite(x).all() or not np.isfinite(y).all():
        return {'passed': False, 'failures': ['invalid coordinates']}
    x=x-x.mean(0); y=y-y.mean(0)
    u, _, vt = np.linalg.svd(y.T @ x)
    correction=np.eye(3); correction[-1,-1]=np.linalg.det(u @ vt)
    distances=np.linalg.norm(y @ (u @ correction @ vt)-x,axis=1)
    pa, pb = (np.load(r['pae_path'])['pae'].astype(float) for r in (a,b))
    if pa.shape != pb.shape or not np.isfinite(pa).all() or not np.isfinite(pb).all():
        return {'passed': False, 'failures': ['invalid PAE']}
    delta=np.abs(pa-pb)
    metrics={
        'ca_aligned_rmsd_angstrom': float(np.sqrt(np.mean(distances**2))),
        'ca_displacement_p95_angstrom': float(np.percentile(distances,95)),
        'complex_plddt_absolute_change': abs(a['confidence']['complex_plddt']-b['confidence']['complex_plddt']),
        'ptm_absolute_change': abs(a['confidence']['ptm']-b['confidence']['ptm']),
        'pae_mae_angstrom': float(delta.mean()),
        'pae_absolute_change_p95_angstrom': float(np.percentile(delta,95)),
    }
    failures=[k for k,v in metrics.items() if not np.isfinite(v) or v>limits[k+'_max']]
    def keys(row):
        return {tuple(v.get(k) for k in ('model','chain','residue_1','residue_2','atoms'))
                for v in row['geometry']['violations']}
    new=keys(b)-keys(a)
    if new: failures.append('new backbone discontinuities')
    if a['geometry']['errors'] or b['geometry']['errors']: failures.append('geometry input errors')
    return dict(passed=not failures, failures=failures, metrics=metrics,
                baseline_discontinuities=len(keys(a)),candidate_discontinuities=len(keys(b)),
                new_discontinuities=len(new),seconds_baseline=a['seconds'],seconds_candidate=b['seconds'],
                speed_ratio=a['seconds']/b['seconds'])


def measurements(block):
    result=json.loads((Path(block)/'result.json').read_text())
    return [json.loads(Path(p).read_text()) for p in result['rows']]


def compare_blocks(a, b, limits):
    left=measurements(a); right=measurements(b)
    if [(r['name'],r['seed'],r['warmup']) for r in left] != [(r['name'],r['seed'],r['warmup']) for r in right]:
        raise ValueError('Unpaired block cases')
    rows=[]
    for x,y in zip(left,right):
        row=compare(x,y,limits); row.update(name=x['name'],seed=x['seed'],warmup=x['warmup']); rows.append(row)
    return dict(passed=all(r['passed'] for r in rows),pairs=rows)


if __name__=='__main__':
    import argparse
    ap=argparse.ArgumentParser(); ap.add_argument('reference');ap.add_argument('candidate');ap.add_argument('manifest');ap.add_argument('output')
    args=ap.parse_args()
    result=compare_blocks(args.reference,args.candidate,json.loads(Path(args.manifest).read_text())['acceptance'])
    Path(args.output).write_text(json.dumps(result,indent=2,allow_nan=False)+'\n')
    print(json.dumps(result,indent=2))
    raise SystemExit(0 if result['passed'] else 2)
