"""Select and verify the RFdiffusion3 inference weight set.

Foundry checkpoints contain both a raw ``model`` and an EMA ``shadow`` network.
The EMA wrapper dispatches to ``shadow`` in eval mode, so deployed inference must
use that branch.  Keep branch selection and artifact provenance in one module so
the exporter, oracle, installer, and MLX runner cannot silently disagree.
"""

from __future__ import annotations

import argparse
import json
import os
import struct
from pathlib import Path


VALID_WEIGHT_SETS = ("model", "shadow")
DEFAULT_WEIGHT_SET = "shadow"
EXPECTED_ARTIFACT_METADATA = {"weight_set": "shadow", "which": "shadow (EMA)"}
_WRAPPER_ATTRS = ("module", "_forward_module", "_original_module", "net", "_model")


class WeightSetError(RuntimeError):
    """Raised instead of silently using an unintended weight set."""


def resolve_weight_set(explicit=None):
    value = explicit if explicit is not None else os.environ.get(
        "RFD3_WEIGHT_SET", DEFAULT_WEIGHT_SET
    )
    if value not in VALID_WEIGHT_SETS:
        raise WeightSetError(
            f"unknown weight set {value!r}; expected one of {VALID_WEIGHT_SETS}. "
            "'shadow' is the EMA copy that inference executes; 'model' is raw."
        )
    return value


def _is_ema(node):
    return hasattr(node, "model") and hasattr(node, "shadow")


def _find_ema(module, max_depth=6):
    node = module
    for _ in range(max_depth):
        if _is_ema(node):
            return node
        nxt = None
        for attr in _WRAPPER_ATTRS:
            candidate = getattr(node, attr, None)
            if candidate is not None and candidate is not node:
                nxt = candidate
                break
        if nxt is None:
            break
        node = nxt
    return None


def select_core(module, weight_set=None):
    """Return the requested network and the provenance label recorded on disk."""
    weight_set = resolve_weight_set(weight_set)
    ema = _find_ema(module)
    if ema is not None:
        core = getattr(ema, weight_set, None)
        if core is None or not hasattr(core, "diffusion_module"):
            raise WeightSetError(
                f"EMA wrapper found but {weight_set!r} is not an RFD3 network; "
                "refusing to fall back to the other branch."
            )
        return core, "shadow (EMA)" if weight_set == "shadow" else "model (raw)"

    node = module
    for _ in range(len(_WRAPPER_ATTRS) + 1):
        if hasattr(node, "diffusion_module"):
            return node, "plain (no EMA wrapper)"
        nxt = None
        for attr in _WRAPPER_ATTRS:
            candidate = getattr(node, attr, None)
            if candidate is not None and candidate is not node:
                nxt = candidate
                break
        if nxt is None:
            break
        node = nxt
    raise WeightSetError(f"could not find an RFD3 network under {type(module).__name__}")


def assert_expected(which, weight_set):
    expected = {
        "shadow": "shadow (EMA)",
        "model": "model (raw)",
    }[resolve_weight_set(weight_set)]
    if which != expected:
        raise WeightSetError(
            f"resolved {which!r}, but {expected!r} was requested; refusing to continue"
        )


def safetensors_metadata(path):
    """Read only the small safetensors JSON header, without importing MLX."""
    path = Path(path)
    try:
        with path.open("rb") as handle:
            size_bytes = handle.read(8)
            if len(size_bytes) != 8:
                raise WeightSetError(f"{path} is not a valid safetensors file")
            header_size = struct.unpack("<Q", size_bytes)[0]
            if header_size < 2 or header_size > 64 * 1024 * 1024:
                raise WeightSetError(f"{path} has an invalid safetensors header size")
            header = handle.read(header_size)
        document = json.loads(header)
    except (OSError, UnicodeDecodeError, json.JSONDecodeError, struct.error) as exc:
        raise WeightSetError(f"could not read safetensors metadata from {path}: {exc}") from exc
    metadata = document.get("__metadata__", {})
    if not isinstance(metadata, dict):
        raise WeightSetError(f"{path} has malformed safetensors metadata")
    return {str(key): str(value) for key, value in metadata.items()}


def assert_ema_artifact(path):
    metadata = safetensors_metadata(path)
    wrong = {
        key: (metadata.get(key), expected)
        for key, expected in EXPECTED_ARTIFACT_METADATA.items()
        if metadata.get(key) != expected
    }
    if wrong:
        details = ", ".join(
            f"{key}={actual!r} (expected {expected!r})"
            for key, (actual, expected) in wrong.items()
        )
        raise WeightSetError(
            f"{Path(path)} is not a verified RFdiffusion3 EMA artifact: {details}. "
            "Re-run RFdiffusion3 setup to export the shadow weights."
        )
    return metadata


def main():
    parser = argparse.ArgumentParser(description="Verify RFdiffusion3 weight provenance")
    parser.add_argument("--check-artifact", type=Path, required=True)
    args = parser.parse_args()
    metadata = assert_ema_artifact(args.check_artifact)
    print(json.dumps(metadata, sort_keys=True))


if __name__ == "__main__":
    main()
