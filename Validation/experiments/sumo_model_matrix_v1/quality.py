"""Rigid crystal-core alignment used for both metrics and exported structures."""
import numpy as np

def fit(reference, candidate):
    x, y = np.asarray(reference, dtype=float), np.asarray(candidate, dtype=float)
    if x.shape != y.shape or x.ndim != 2 or x.shape[1] != 3 or len(x) < 3:
        raise ValueError('Coordinate shape mismatch')
    if not np.isfinite(x).all() or not np.isfinite(y).all():
        raise ValueError('Nonfinite coordinate')
    u, _, vt = np.linalg.svd((y-y.mean(0)).T @ (x-x.mean(0)))
    d = np.eye(3)
    d[-1, -1] = np.linalg.det(u @ vt)
    rotation = u @ d @ vt
    return rotation, x.mean(0)-y.mean(0) @ rotation

def align(reference, candidate):
    rotation, translation = fit(reference, candidate)
    return float(np.sqrt(np.mean(np.sum((np.asarray(candidate) @ rotation + translation-reference)**2, axis=1))))
