"""Portable input-motif provenance and one global rigid-fit RMSD report."""
import hashlib
import json
import numpy as np


def checksum(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(',', ':'), allow_nan=False).encode()).hexdigest()


def fit_report(moving, reference, owners):
    p, q = np.asarray(moving, dtype=float), np.asarray(reference, dtype=float)
    if (p.shape != q.shape or p.ndim != 2 or p.shape[1] != 3 or len(p) < 3
            or len(owners) != len(p) or not np.isfinite(p).all() or not np.isfinite(q).all()):
        return None, {}
    pc, qc = p - p.mean(0), q - q.mean(0)
    if min(np.linalg.matrix_rank(pc, tol=1e-6), np.linalg.matrix_rank(qc, tol=1e-6)) < 2:
        return None, {}
    u, _, vt = np.linalg.svd(pc.T @ qc)
    sign = np.eye(3); sign[-1, -1] = np.linalg.det(u @ vt)
    delta = pc @ (u @ sign @ vt) - qc
    squared = np.sum(delta * delta, axis=1)
    return float(np.sqrt(squared.mean())), {
        source: float(np.sqrt(squared[np.array(owners) == source].mean())) for source in sorted(set(owners))}
