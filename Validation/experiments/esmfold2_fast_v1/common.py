"""Validation utilities for a bounded, benign monomer runtime comparison."""
from __future__ import annotations
import hashlib
import json
from pathlib import Path

def sha(path):
    h = hashlib.sha256()
    with Path(path).open('rb') as f:
        for part in iter(lambda: f.read(8 * 1024 * 1024), b''):
            h.update(part)
    return h.hexdigest()

def atomic(path, value):
    path = Path(path); path.parent.mkdir(parents=True, exist_ok=True)
    temp = path.with_suffix(path.suffix + '.tmp')
    temp.write_text(json.dumps(value, indent=2, sort_keys=True, allow_nan=False)+'\n')
    temp.replace(path)

def align(reference, candidate):
    import numpy as np
    x, y = np.asarray(reference, dtype=float), np.asarray(candidate, dtype=float)
    if x.shape != y.shape or x.ndim != 2 or x.shape[1] != 3 or len(x) < 3:
        raise ValueError('Coordinate shape mismatch')
    if not np.isfinite(x).all() or not np.isfinite(y).all():
        raise ValueError('Nonfinite coordinate')
    x0, y0 = x-x.mean(0), y-y.mean(0)
    u, _, vt = np.linalg.svd(y0.T @ x0)
    d = np.eye(3); d[-1, -1] = np.linalg.det(u @ vt)
    aligned = y0 @ u @ d @ vt + x.mean(0)
    return float(np.sqrt(np.mean(np.sum((x-aligned)**2, axis=1))))

AA = dict(zip('ALA ARG ASN ASP CYS GLN GLU GLY HIS ILE LEU LYS MET PHE PRO SER THR TRP TYR VAL'.split(), 'ARNDCQEGHILKMFPSTWYV'))

def pdb_audit(path, sequence):
    import numpy as np
    residues = {}; atom_count = 0
    for line in Path(path).read_text().splitlines():
        if not line.startswith('ATOM  '): continue
        if line[16] not in (' ', 'A'): raise ValueError('Unexpected alternate location')
        key=(line[21],line[22:27]); name=line[12:16].strip()
        xyz=[float(line[30:38]),float(line[38:46]),float(line[46:54])]
        if not np.isfinite(xyz).all(): raise ValueError('Nonfinite atom')
        r=residues.setdefault(key, {'aa':AA.get(line[17:20], '?'),'atoms':{}})
        if name in r['atoms']: raise ValueError('Duplicate atom')
        r['atoms'][name]=xyz; atom_count+=1
    if len({k[0] for k in residues}) != 1: raise ValueError('Expected one chain')
    actual=''.join(r['aa'] for r in residues.values())
    if actual != sequence: raise ValueError('Sequence or output cardinality mismatch')
    if not all({'N','CA','C'}.issubset(r['atoms']) for r in residues.values()):
        raise ValueError('Incomplete backbone')
    ca=np.array([r['atoms']['CA'] for r in residues.values()])
    distances=np.linalg.norm(np.diff(ca,axis=0),axis=1)
    return dict(sequence_exact=True,atom_count=atom_count,ca=ca.tolist(),
                backbone_complete=True,ca_breaks=int(((distances<2.5)|(distances>4.5)).sum()),
                ca_neighbor_min=float(distances.min()),ca_neighbor_max=float(distances.max()))

def verify_inventory(entries):
    for entry in entries:
        if sha(entry['path']) != entry['sha256']:
            raise RuntimeError('Provenance mismatch: '+entry['path'])
