#!/usr/bin/env python3
"""Run the qualified LASErMPNN CPU sampler, optionally in an owner-scoped worker.

The --resident DIR OWNER prefix reuses a model within that owner process only.
Without it, the identical sampler/seed policy executes in a fresh interpreter.
"""
from pathlib import Path
import os
import sys


def main():
    args = sys.argv[1:]
    if args[:1] == ['--resident']:
        from mpnn_worker import submit
        directory, owner, *args = args[1:]
        # Imports and each native model stay inside the LASErMPNN interpreter.
        result = submit(directory, int(owner), Path(__file__), args)
        raise SystemExit(result['returncode'])
    if len(args) < 2:
        raise SystemExit('usage: run_lasermpnn_seeded.py [--resident DIR OWNER] SEED [native arguments]')
    seed = int(args[0])
    if not 0 <= seed <= 2**32 - 1:
        raise ValueError('LASErMPNN seed must be a nonnegative 32-bit integer')
    for name in ('OMP_NUM_THREADS','MKL_NUM_THREADS','OPENBLAS_NUM_THREADS','VECLIB_MAXIMUM_THREADS'):
        os.environ[name] = '1'
    from laser_sampling import run
    run(seed, args[1:])


if __name__ == '__main__':
    main()
