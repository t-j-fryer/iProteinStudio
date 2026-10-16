"""Qualified CPU LASErMPNN model reuse, preserving the upstream sampler.

Seed policy v2 resets Python/NumPy/Torch AFTER checkpoint loading, identically
in cold and warm calls. Historical NISE sampling did not apply its seed.
"""
from pathlib import Path
import os
import random
import sys

_CACHE = None


def run(seed, arguments):
    global _CACHE
    root = os.environ.get("NANOHUNTER_ROOT") or os.environ.get("IPROTEIN_ROOT")
    if root:
        sys.path.insert(0, str(Path(root) / "src"))
    import numpy as np
    import torch
    from LASErMPNN import run_batch_inference as upstream
    torch.set_num_threads(1)
    if '--device' in arguments and arguments[arguments.index('--device') + 1] != 'cpu':
        raise ValueError('Resident LASErMPNN is CPU-only')
    weights = Path(arguments[arguments.index('--model_weights_path') + 1]).resolve()
    stat = weights.stat()
    key = (str(weights), stat.st_size, stat.st_mtime_ns)
    original = upstream.load_model_from_parameter_dict

    def load(path, device, *args, **kwargs):
        global _CACHE
        if Path(path).resolve() != weights or str(device) != 'cpu':
            raise ValueError('LASErMPNN loader identity differs from recorded request')
        if _CACHE is None or _CACHE[0] != key:
            model, params = original(path, device, *args, **kwargs)
            model.eval()
            _CACHE = (key, model, params)
        random.seed(seed)
        np.random.seed(seed % (2**32))
        torch.manual_seed(seed)
        return _CACHE[1:]

    old_argv = sys.argv
    upstream.load_model_from_parameter_dict = load
    try:
        sys.argv = ['run_batch_inference', *arguments]
        upstream.run_inference(**upstream.parse_args(str(weights)))
    finally:
        sys.argv = old_argv
        upstream.load_model_from_parameter_dict = original
    print(f'LASERMPNN_SAMPLING|policy=post-load-seed-v2|seed={seed}|pid={os.getpid()}|threads=1', flush=True)
