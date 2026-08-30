#!/usr/bin/env python3
"""Numerically validate the absent-substructure Transformer shortcut on MPS."""

from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path


def atomic_json(path: Path, value: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".part")
    temporary.write_text(json.dumps(value, indent=2, sort_keys=True) + "\n")
    temporary.replace(path)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--runtime-root", type=Path,
        default=Path.home() / ".iproteinstudio",
    )
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()

    os.environ.pop("PYTORCH_ENABLE_MPS_FALLBACK", None)
    root = args.runtime_root.expanduser().resolve()
    source = root / "src/ProtenixConstraint"
    checkpoint = (
        root / "models/protenix_constraint/checkpoint/"
        "protenix_base_constraint_v0.5.0.pt"
    )
    if not source.is_dir() or not checkpoint.is_file():
        raise SystemExit("the managed Protenix Constraint source/checkpoint is missing")
    sys.path.insert(0, str(source))

    import torch
    from protenix.model.modules.embedders import SubstructureEmbedder

    if not torch.backends.mps.is_available():
        raise SystemExit("native Apple MPS is required; CPU validation is not offered")
    device = torch.device("mps")
    document = torch.load(checkpoint, map_location="cpu", weights_only=False)
    prefix = "module.constraint_embedder.substructure_z_embedder."
    state = {
        key[len(prefix):]: value
        for key, value in document["model"].items()
        if key.startswith(prefix)
    }
    model = SubstructureEmbedder(
        n_classes=4, c_pair_dim=128, architecture="transformer",
        hidden_dim=128, n_layers=1,
    ).to(device).eval()
    model.load_state_dict(state, strict=True)

    rows = []
    with torch.inference_mode():
        for tokens in (2, 8, 16):
            features = torch.zeros((1, tokens, tokens, 4), device=device)

            # Explicit upstream path: all N^2 tokens pass through attention.
            full = model.input_proj(features)
            full = full.reshape(1, tokens * tokens, -1)
            full = model.transformer(full)
            full = model.output_proj(full).reshape(1, tokens, tokens, -1)

            # Production shortcut: evaluate one identical token and broadcast.
            short = model.input_proj(torch.zeros((1, 1, 4), device=device))
            short = model.transformer(short)
            short = model.output_proj(short).reshape(1, 1, 1, -1)
            short = short.expand_as(full)
            torch.mps.synchronize()
            delta = (full - short).abs()
            rows.append({
                "tokens": tokens,
                "max_abs_error": float(delta.max().cpu()),
                "mean_abs_error": float(delta.mean().cpu()),
                "allclose_atol_1e-6_rtol_1e-5": bool(
                    torch.allclose(full, short, atol=1e-6, rtol=1e-5)
                ),
            })

    if not all(row["allclose_atol_1e-6_rtol_1e-5"] for row in rows):
        raise SystemExit("absent-substructure shortcut failed numerical equivalence")
    atomic_json(args.output, {
        "device": "mps",
        "torch": torch.__version__,
        "checkpoint": checkpoint.name,
        "cases": rows,
    })
    print(f"PASS: wrote {args.output}")


if __name__ == "__main__":
    main()
