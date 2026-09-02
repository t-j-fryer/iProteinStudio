#!/usr/bin/env python3
"""Boltz MPS launcher for comparing PyTorch runtimes without a cache reset."""

from __future__ import annotations

import os
from pathlib import Path
import sys
from typing import Any


def die(message: str) -> None:
    raise SystemExit(f"Boltz runtime experiment: {message}")


def main() -> None:
    if os.environ.get("PYTORCH_ENABLE_MPS_FALLBACK") == "1":
        die("PYTORCH_ENABLE_MPS_FALLBACK=1 is forbidden")
    os.environ["PYTORCH_ENABLE_MPS_FALLBACK"] = "0"
    import torch
    import boltz.main as boltz_main

    if not torch.backends.mps.is_built() or not torch.backends.mps.is_available():
        die("Apple MPS is unavailable; CPU prediction is forbidden")

    original_trainer = boltz_main.Trainer

    def fp32_trainer(*args: Any, **kwargs: Any) -> Any:
        kwargs["precision"] = 32
        print(f"RUNTIME_LAB|torch={torch.__version__}|precision=32|reset=0", flush=True)
        return original_trainer(*args, **kwargs)

    def managed_assets(cache: Path) -> None:
        cache = Path(cache)
        if not (cache / "boltz2_conf.ckpt").is_file():
            die(f"missing read-only checkpoint in {cache}")
        mols = cache / "mols"
        if not mols.is_dir() or not any(mols.iterdir()):
            die(f"missing read-only chemical-component data in {mols}")

    boltz_main.Trainer = fp32_trainer
    boltz_main.download_boltz2 = managed_assets
    boltz_main.cli.main(
        args=sys.argv[1:], prog_name="boltz-runtime-lab", standalone_mode=False
    )


if __name__ == "__main__":
    main()
