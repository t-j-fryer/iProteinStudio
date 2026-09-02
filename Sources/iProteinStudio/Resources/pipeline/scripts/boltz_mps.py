#!/usr/bin/env python3
"""Run pinned Boltz-2 safely on Apple MPS.

Boltz 2.2.1 selects bfloat16 mixed precision for every non-Boltz-1 model,
including Apple GPUs.  Studio uses full FP32 on MPS for portability.  PyTorch
2.13 also has an allocator-state-sensitive MPS correctness regression whose
silent numerical errors vary by GPU family and OS build.  Studio clears only
unused cached MPS allocations immediately before every prediction batch and
validates the resulting protein geometry before accepting the run.

The upstream downloader also uses the presence of ``mols.tar`` rather than the
already-extracted ``mols/`` directory as its completion test.  Studio installs
and verifies those assets transactionally, then removes the redundant 1.8 GB
archive.  This launcher treats the managed extracted assets as authoritative
and never silently downloads missing runtime data during a prediction.
"""

from __future__ import annotations

import os
from pathlib import Path
import subprocess
import sys
from typing import Any


def die(message: str) -> None:
    raise SystemExit(f"Boltz Apple-GPU launcher: {message}")


def configure_runtime(boltz_main: Any, torch: Any) -> None:
    """Apply Studio's fail-loud Apple-MPS execution policy idempotently."""
    if getattr(boltz_main, "_iproteinstudio_mps_configured", False):
        return
    if os.environ.get("PYTORCH_ENABLE_MPS_FALLBACK") == "1":
        die("PYTORCH_ENABLE_MPS_FALLBACK=1 is forbidden")
    os.environ["PYTORCH_ENABLE_MPS_FALLBACK"] = "0"
    if not torch.backends.mps.is_built() or not torch.backends.mps.is_available():
        die("Apple MPS is unavailable; CPU execution is forbidden")

    original_trainer = boltz_main.Trainer
    from pytorch_lightning.callbacks import Callback

    class MPSCorrectnessBoundary(Callback):
        """Reset allocator state immediately before model inference.

        ``empty_cache`` never frees live model or input tensors.  It releases
        only unused cached blocks, avoiding the allocator placement that can
        trigger silently wrong MPS matrix multiplication in affected PyTorch
        2.13 installations.
        """

        def on_predict_batch_start(
            self,
            trainer: Any,
            pl_module: Any,
            batch: Any,
            batch_idx: int,
            dataloader_idx: int = 0,
        ) -> None:
            torch.mps.synchronize()
            torch.mps.empty_cache()
            print(
                f"IPROTEINSTUDIO_MPS_ALLOCATOR_RESET|boltz|batch={batch_idx}",
                flush=True,
            )

    def fp32_trainer(*args: Any, **kwargs: Any) -> Any:
        kwargs["precision"] = 32
        callbacks = list(kwargs.get("callbacks") or [])
        callbacks.append(MPSCorrectnessBoundary())
        kwargs["callbacks"] = callbacks
        print("IPROTEINSTUDIO_PRECISION|boltz|mps|32", flush=True)
        return original_trainer(*args, **kwargs)

    def managed_assets(cache: Path) -> None:
        cache = Path(cache)
        mols = cache / "mols"
        checkpoint = cache / "boltz2_conf.ckpt"
        if not mols.is_dir() or not any(mols.iterdir()):
            die(f"managed Boltz chemical-component data are missing: {mols}")
        if not checkpoint.is_file() or checkpoint.stat().st_size == 0:
            die(f"managed Boltz structure checkpoint is missing: {checkpoint}")

    boltz_main.Trainer = fp32_trainer
    boltz_main.download_boltz2 = managed_assets
    boltz_main._iproteinstudio_mps_configured = True


def option(arguments: list[str], name: str) -> str | None:
    for index, value in enumerate(arguments):
        if value == name and index + 1 < len(arguments):
            return arguments[index + 1]
        if value.startswith(name + "="):
            return value.split("=", 1)[1]
    return None


def validate_output(arguments: list[str]) -> None:
    if not arguments or arguments[0] != "predict":
        return
    output_value = option(arguments, "--out_dir")
    if output_value is None:
        die("Studio Boltz predictions require an explicit --out_dir")
    root = Path(__file__).resolve().parents[1]
    validator = root / "scripts" / "validate_prediction_geometry.py"
    completed = subprocess.run([sys.executable, str(validator), output_value])
    if completed.returncode:
        die("prediction produced invalid protein geometry; see the diagnostic above")


def main() -> None:
    os.environ.setdefault("PYTORCH_ENABLE_MPS_FALLBACK", "0")
    import torch
    import boltz.main as boltz_main

    configure_runtime(boltz_main, torch)
    arguments = sys.argv[1:]
    boltz_main.cli.main(args=arguments, prog_name="boltz", standalone_mode=False)
    validate_output(arguments)


if __name__ == "__main__":
    main()
