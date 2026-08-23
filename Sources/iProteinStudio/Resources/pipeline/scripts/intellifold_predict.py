#!/usr/bin/env python3
"""Launch Studio's pinned IntelliFold on native Apple MPS, fail-loudly.

Accelerate 1.1.1 sets ``PYTORCH_ENABLE_MPS_FALLBACK=1`` while selecting MPS.
Studio pins that version for validated IntelliFold, so this drop-in launcher
replaces only its device-selection property, asserts the resulting device, and
verifies that every requested seed/sample produced a structure and confidence
record. The upstream runner and its scientific defaults remain unchanged.
"""

from __future__ import annotations

import importlib.metadata
import os
from pathlib import Path
import runpy
import sys

from ipsae_score import IPSAEError, annotate_intellifold


STRICT_ACCELERATE_VERSION = "1.1.1"
STRICT_TORCH_VERSION = "2.6.0"


def die(message: str) -> None:
    raise SystemExit(f"IntelliFold MPS launcher: {message}")


def option(arguments: list[str], name: str, default: str) -> str:
    for index, value in enumerate(arguments):
        if value == name:
            if index + 1 >= len(arguments):
                die(f"{name} requires a value")
            return arguments[index + 1]
        if value.startswith(name + "="):
            return value.split("=", 1)[1]
    return default


def verify_outputs(arguments: list[str]) -> None:
    if "--only_run_data_process" in arguments:
        return
    if not arguments:
        die("missing IntelliFold input path")
    source = Path(arguments[0]).expanduser().resolve()
    yaml_paths = [source] if source.is_file() else sorted(source.glob("*.yaml"))
    if not yaml_paths:
        die(f"no YAML inputs found at {source}")
    output = Path(option(arguments, "--out_dir", "./")).expanduser().resolve()
    prediction_root = output / source.stem / "predictions"
    seeds = [value.strip() for value in option(arguments, "--seed", "42").split(",")
             if value.strip()]
    try:
        samples = int(option(arguments, "--num_diffusion_samples", "5"))
    except ValueError:
        die("--num_diffusion_samples must be an integer")
    extension = "pdb" if option(arguments, "--output_format", "mmcif") == "pdb" else "cif"

    for yaml_path in yaml_paths:
        job = yaml_path.stem
        job_dir = prediction_root / job
        structures = set(job_dir.glob(f"{job}_seed-*_sample-*.{extension}"))
        summaries = set(job_dir.glob(f"{job}_seed-*_sample-*_summary_confidences.json"))
        detailed = {
            path for path in job_dir.glob(f"{job}_seed-*_sample-*_confidences.json")
            if "summary_confidences" not in path.name
        }
        expected = len(seeds) * samples
        if (len(structures) != expected or len(summaries) != expected
                or len(detailed) != expected):
            die(f"{job} expected exactly {expected} structure/confidence pair(s); "
                f"found {len(structures)} structure(s), {len(summaries)} summary file(s), "
                f"and {len(detailed)} detailed-confidence file(s)")

    try:
        annotate_intellifold(output)
    except (IPSAEError, OSError, ValueError) as exc:
        die(f"ipSAE scoring failed: {exc}")


def main() -> None:
    arguments = sys.argv[1:]
    configured_root = os.environ.get("NANOHUNTER_ROOT") or os.environ.get("IPROTEIN_ROOT")
    root = Path(configured_root).expanduser().resolve() if configured_root \
        else Path(__file__).resolve().parents[1]
    runner = root / "src" / "IntelliFold" / "run_intellifold.py"
    if not runner.is_file():
        die(f"upstream runner is missing: {runner}")
    if os.environ.get("PYTORCH_ENABLE_MPS_FALLBACK") == "1":
        die("PYTORCH_ENABLE_MPS_FALLBACK=1 is forbidden")
    os.environ["PYTORCH_ENABLE_MPS_FALLBACK"] = "0"

    accelerate_version = importlib.metadata.version("accelerate")
    torch_version = importlib.metadata.version("torch")
    if accelerate_version != STRICT_ACCELERATE_VERSION:
        die(f"expected Accelerate {STRICT_ACCELERATE_VERSION}, found {accelerate_version}")
    if torch_version != STRICT_TORCH_VERSION:
        die(f"expected PyTorch {STRICT_TORCH_VERSION}, found {torch_version}")

    import torch
    if not torch.backends.mps.is_built() or not torch.backends.mps.is_available():
        die("Apple MPS is unavailable; CPU execution is forbidden")

    from accelerate import Accelerator
    from accelerate.state import AcceleratorState, PartialState

    strict_device = property(lambda _state: torch.device("mps"))
    PartialState.default_device = strict_device
    AcceleratorState.default_device = strict_device
    original_init = Accelerator.__init__

    def strict_init(self, *positional, **keywords):
        original_init(self, *positional, **keywords)
        if self.device.type != "mps":
            die(f"Accelerate selected forbidden device {self.device}")
        if os.environ.get("PYTORCH_ENABLE_MPS_FALLBACK") != "0":
            die("Accelerate re-enabled forbidden MPS CPU fallback")
        print(f"IPROTEINSTUDIO_DEVICE|intellifold|{self.device}|fallback=0", flush=True)

    Accelerator.__init__ = strict_init
    sys.argv = [str(runner), *arguments]
    runpy.run_path(str(runner), run_name="__main__")
    verify_outputs(arguments)


if __name__ == "__main__":
    main()
