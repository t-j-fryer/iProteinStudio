#!/usr/bin/env python3
"""Apply or reverse NanoHunter's small, idempotent IntelliFold MPS patch."""
from __future__ import annotations

import argparse
from pathlib import Path


RUNNER_OLD = """logger = logging.getLogger(__name__)\n \n"""
RUNNER_NEW = '''logger = logging.getLogger(__name__)\n\n\ndef empty_device_cache(accelerator):
    """Clear CUDA's allocator only when CUDA is actually in use.

    The historical runner called ``torch.cuda.empty_cache`` six times per input
    even on Apple MPS.  ``legacy`` is retained for paired benchmarking and rapid
    rollback; ``auto`` is the production-safe default.
    """
    mode = os.environ.get("NANOHUNTER_INTELLIFOLD_MPS_CLEANUP", "auto")
    if mode == "legacy" or accelerator.device.type == "cuda":
        torch.cuda.empty_cache()
\n'''

LOADER_OLD = """    dataloader = DataLoader(\n        dataset,\n        batch_size=1,\n        num_workers=args.num_workers,\n        pin_memory=True,\n"""
LOADER_NEW = '''    cleanup_mode = os.environ.get("NANOHUNTER_INTELLIFOLD_MPS_CLEANUP", "auto")
    # Pinned host memory accelerates CUDA transfers but is unsupported on MPS.
    # Preserve the old behavior only for a paired legacy benchmark.
    pin_memory = cleanup_mode == "legacy" or torch.cuda.is_available()
    dataloader = DataLoader(
        dataset,
        batch_size=1,
        num_workers=args.num_workers,
        pin_memory=pin_memory,
'''


def replace_once(path: Path, old: str, new: str) -> str:
    text = path.read_text()
    if new in text and old not in text:
        return "already applied"
    if text.count(old) != 1:
        raise SystemExit(f"Expected exactly one patch anchor in {path}; found {text.count(old)}")
    path.write_text(text.replace(old, new, 1))
    return "updated"


def patch_runner(path: Path, reverse: bool) -> str:
    old, new = (RUNNER_NEW, RUNNER_OLD) if reverse else (RUNNER_OLD, RUNNER_NEW)
    text = path.read_text()
    target_call = "torch.cuda.empty_cache()" if not reverse else "empty_device_cache(accelerator)"
    replacement_call = "empty_device_cache(accelerator)" if not reverse else "torch.cuda.empty_cache()"
    expected = 6
    already_calls = "torch.cuda.empty_cache()"
    already_count = expected if reverse else 1  # patched helper retains one CUDA call
    if new in text and text.count(already_calls) == already_count:
        return "already applied"
    if text.count(old) != 1:
        raise SystemExit(
            f"Unexpected IntelliFold runner anchors in {path}: "
            f"header={text.count(old)}"
        )
    # On apply, replace the six historical calls before adding the helper's own
    # CUDA call.  On reverse, remove the helper before restoring those six calls.
    if reverse:
        text = text.replace(old, new, 1)
    if text.count(target_call) != expected:
        raise SystemExit(
            f"Unexpected cache call count in {path}: "
            f"expected {expected}, found {text.count(target_call)}"
        )
    text = text.replace(target_call, replacement_call)
    if not reverse:
        text = text.replace(old, new, 1)
    path.write_text(text)
    return "updated"


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("repo", type=Path)
    parser.add_argument("--reverse", action="store_true")
    args = parser.parse_args()
    repo = args.repo.resolve()
    runner = repo / "run_intellifold.py"
    loader = repo / "intellifold/data/module/inference.py"
    if not runner.is_file() or not loader.is_file():
        raise SystemExit(f"Not an IntelliFold source tree: {repo}")

    loader_old, loader_new = (
        (LOADER_NEW, LOADER_OLD) if args.reverse else (LOADER_OLD, LOADER_NEW)
    )
    print(f"runner: {patch_runner(runner, args.reverse)}")
    print(f"loader: {replace_once(loader, loader_old, loader_new)}")


if __name__ == "__main__":
    main()
