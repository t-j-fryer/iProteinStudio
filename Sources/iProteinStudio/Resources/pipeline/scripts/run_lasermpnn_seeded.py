#!/usr/bin/env python3
"""Seed every RNG, then execute upstream LASErMPNN batch inference unchanged."""

from __future__ import annotations

import random
import runpy
import sys


def main() -> None:
    if len(sys.argv) < 2:
        raise SystemExit("usage: run_lasermpnn_seeded.py SEED [LASErMPNN arguments...]")
    try:
        seed = int(sys.argv[1])
    except ValueError as exc:
        raise SystemExit("LASErMPNN seed must be an integer") from exc

    import numpy as np
    import torch

    random.seed(seed)
    np.random.seed(seed % (2**32))
    torch.manual_seed(seed)
    if torch.backends.mps.is_available():
        torch.mps.manual_seed(seed)

    sys.argv = ["LASErMPNN.run_batch_inference", *sys.argv[2:]]
    runpy.run_module("LASErMPNN.run_batch_inference", run_name="__main__")


if __name__ == "__main__":
    main()
