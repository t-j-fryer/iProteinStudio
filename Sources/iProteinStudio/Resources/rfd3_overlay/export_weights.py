#!/usr/bin/env python
"""
M1 step 1 — export the exact deployable RFD3 weights to MLX safetensors.

Loads RFD3 through the Foundry engine and explicitly selects the EMA ``shadow``
network used in evaluation mode, then serializes ``core.state_dict()`` to an MLX
.safetensors plus a key->shape manifest. This is a *standalone* artifact: the
MLX/Swift side never needs foundry again.

Also reports whether the deployed weights are the raw `model.*` or the EMA
`shadow.*` copy from the checkpoint (sanity).

Output: weights/rfd3_core.safetensors  +  weights/keys.json
"""
import json
import os
from pathlib import Path

os.environ.setdefault("TOKENIZERS_PARALLELISM", "false")
import numpy as np
import torch

import foundry.inference_engines.base as base_mod

from rfd3_weight_set import assert_expected, resolve_weight_set, select_core


def _force_cpu(cfg):
    cfg.trainer.accelerator = "cpu"
    cfg.trainer.devices_per_node = 1
    cfg.trainer.num_nodes = 1
    if hasattr(cfg.trainer, "precision"):
        cfg.trainer.precision = "32-true"
    return cfg


base_mod.set_accelerator_based_on_availability = _force_cpu

import rfd3  # noqa: E402
from hydra import compose, initialize_config_dir  # noqa: E402
from omegaconf import OmegaConf  # noqa: E402
from rfd3.engine import RFD3InferenceConfig, RFD3InferenceEngine  # noqa: E402
import mlx.core as mx  # noqa: E402


def main():
    here = Path(__file__).parent
    ckpt = (here / "checkpoints" / "rfd3_latest.ckpt").resolve()
    wdir = here / os.environ.get("RFD3_WEIGHTS_DIR", "weights")
    wdir.mkdir(exist_ok=True)

    cfgdir = os.path.join(os.path.dirname(rfd3.__file__), "configs")
    with initialize_config_dir(version_base="1.3", config_dir=cfgdir):
        cfg = compose(config_name="inference", overrides=[
            f"ckpt_path={ckpt}", "diffusion_batch_size=1",
            "inference_sampler.num_timesteps=20", "seed=0",
            "skip_existing=False", "verbose=False",
        ])
    cfg_dict = OmegaConf.to_container(cfg, resolve=True)
    run_keys = {"inputs", "n_batches", "out_dir", "_target_"}
    init_cfg = {k: v for k, v in cfg_dict.items() if k not in run_keys}

    engine = RFD3InferenceEngine(**RFD3InferenceConfig(**init_cfg))
    engine.initialize()
    weight_set = resolve_weight_set()
    model = engine.trainer.state["model"]
    core, which = select_core(model, weight_set)
    assert_expected(which, weight_set)
    core = core.eval()
    sd = core.state_dict()
    print(f"weight_set={weight_set} -> {which}; core={type(core).__name__} n_tensors={len(sd)} "
          f"n_params={sum(v.numel() for v in sd.values()):,}")

    # Verify many tensors independently against the requested checkpoint
    # namespace. A one-tensor probe is not sufficient provenance.
    ck = torch.load(ckpt, map_location="cpu", weights_only=False)["model"]
    matches = {"model": 0, "shadow": 0, "both": 0, "neither": 0}
    for key, value in sd.items():
        if not torch.is_tensor(value) or value.ndim == 0:
            continue
        raw = f"model.{key}" in ck and torch.equal(value, ck[f"model.{key}"])
        ema = f"shadow.{key}" in ck and torch.equal(value, ck[f"shadow.{key}"])
        matches["both" if raw and ema else "model" if raw else "shadow" if ema else "neither"] += 1
    wanted, other = ("shadow", "model") if weight_set == "shadow" else ("model", "shadow")
    if matches[other] or matches["neither"] or not matches[wanted]:
        raise SystemExit(
            f"ABORT: selected tensors do not come cleanly from {wanted}.*: {matches}"
        )
    print(f"checkpoint namespace match: {matches}")

    # --- serialize to MLX safetensors (keep torch layout; per-module handling in MLX) ---
    flat, manifest = {}, {}
    n_scalar = 0
    for k, v in sd.items():
        if not torch.is_tensor(v):
            continue
        if v.ndim == 0:
            # bookkeeping scalars (e.g. use_rmsnorm flags) — record, don't store as weight
            manifest[k] = {"shape": [], "dtype": str(v.dtype), "scalar": v.item()}
            n_scalar += 1
            continue
        arr = v.detach().to(torch.float32).cpu().numpy()
        flat[k] = mx.array(arr)
        manifest[k] = {"shape": list(arr.shape), "dtype": "float32"}

    out = wdir / "rfd3_core.safetensors"
    # A machine-specific absolute source path changes the artifact hash even
    # when every tensor is identical. Record the pinned checkpoint filename so
    # independently installed roots produce byte-identical weights.
    mx.save_safetensors(str(out), flat, metadata={
        "which": which, "weight_set": weight_set, "source": ckpt.name,
    })
    (wdir / "keys.json").write_text(json.dumps(
        {"which": which, "weight_set": weight_set,
         "n_tensors": len(flat), "n_scalars": n_scalar,
         "n_params": int(sum(v.numel() for v in sd.values() if torch.is_tensor(v) and v.ndim > 0)),
         "tensors": manifest}, indent=2))
    print(f"saved {out} ({out.stat().st_size/1e6:.1f} MB), {len(flat)} tensors, {n_scalar} scalars")


if __name__ == "__main__":
    main()
