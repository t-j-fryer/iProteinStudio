#!/usr/bin/env python
"""
Milestone 0 — RFD3 PyTorch reference oracle.

Runs RFD3 on a tiny unconditional monomer and captures golden fixtures for the
MLX parity work (M1):

  1. The post-AtomWorks feature dict `f`, the noised input `X_noisy_L`, and `t`.
  2. Token-initializer outputs (Q_L_init, C_L, P_LL, S_I, Z_II).
  3. Per-block outputs of the diffusion module (encoder / token-encoder /
     transformer / decoder / sequence-head), captured with forward hooks.
  4. The single diffusion-module step output (X_L, sequence logits/indices).
  5. The full sampler rollout's final coordinates + sequence.

Everything is computed on CPU in fp32 so the fixture is a clean, portable gold
reference. Output: oracle/oracle_<name>.npz  +  oracle/oracle_<name>.manifest.json
plus the generated structure under oracle/out/.

Usage:
  python milestone0_oracle.py --name uncond50 --length 50 --timesteps 20
"""
import argparse
import json
import os
from pathlib import Path

os.environ.setdefault("TOKENIZERS_PARALLELISM", "false")

import contextlib

import numpy as np
import torch

# ---- force pure fp32: disable autocast so the PairformerBlock (which otherwise
# runs bf16 on CPU via force_bfloat16 + torch.amp.autocast) computes in fp32.
# Gives a clean fp32 gold reference; bf16 in the pairformer is a deployment
# precision choice, handled/measured separately in M2, not a parity confound.
torch.amp.autocast = lambda *a, **k: contextlib.nullcontext()

# ---- also force the pairformer attention to NOT cast to bf16 (its hardcoded
# `force_bfloat16=True` otherwise runs those matmuls in bfloat16 on CPU, which
# leaves a ~2.7e-4 artifact in the pair rep). Patch at class-init so every
# instance is fp32 from construction. ----
import rfd3.model.layers.pairformer_layers as _pf_mod

_pf_orig_init = _pf_mod.AttentionPairBiasPairformerDeepspeed.__init__


def _pf_init(self, *a, **k):
    _pf_orig_init(self, *a, **k)
    self.force_bfloat16 = False
    self.use_deepspeed_evo = False


_pf_mod.AttentionPairBiasPairformerDeepspeed.__init__ = _pf_init

# ---- force CPU fp32 (clean gold reference; avoids MPS kernel drift) ----------
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

CAP = {}  # global capture store


class FeaturesCaptured(RuntimeError):
    """Internal early-exit used by --features-only after Foundry preprocessing."""


# ----------------------------- serialization ---------------------------------
def flatten(obj, prefix, arrays, meta):
    """Walk nested dict/list/tuple/tensor -> flat {path: ndarray} + structure meta."""
    if torch.is_tensor(obj):
        a = obj.detach().to("cpu")
        a = a.float().numpy() if a.dtype.is_floating_point else a.numpy()
        arrays[prefix] = a
        meta[prefix] = {"shape": list(a.shape), "dtype": str(a.dtype), "kind": "tensor"}
    elif isinstance(obj, np.ndarray):
        arrays[prefix] = obj
        meta[prefix] = {"shape": list(obj.shape), "dtype": str(obj.dtype), "kind": "ndarray"}
    elif isinstance(obj, dict):
        meta[prefix] = {"kind": "dict", "keys": list(map(str, obj.keys()))}
        for k, v in obj.items():
            flatten(v, f"{prefix}/{k}", arrays, meta)
    elif isinstance(obj, (list, tuple)):
        meta[prefix] = {"kind": type(obj).__name__, "len": len(obj)}
        for i, v in enumerate(obj):
            flatten(v, f"{prefix}/{i}", arrays, meta)
    else:
        meta[prefix] = {"kind": "scalar", "value": repr(obj)[:200]}


class CaptureEngine(RFD3InferenceEngine):
    def _model_forward(self, pipeline_output):
        model = self.trainer.state["model"]
        weight_set = resolve_weight_set()
        core, which = select_core(model, weight_set)
        assert_expected(which, weight_set)
        print(f"[oracle] weight_set={weight_set} -> {which} core={type(core).__name__}")
        core = core.to("cpu").eval()
        # kill the explicit bf16 cast inside the pairformer attention (fp32 reference)
        n_bf16_off = 0
        for m in core.modules():
            if type(m).__name__ == "AttentionPairBiasPairformerDeepspeed":
                m.force_bfloat16 = False
                n_bf16_off += 1
        print(f"[capture] disabled bf16 in {n_bf16_off} pairformer attentions")
        CAP["model_class"] = type(model).__name__
        CAP["core_class"] = type(core).__name__
        CAP["weight_set"] = weight_set
        CAP["which"] = which
        CAP["n_params"] = int(sum(p.numel() for p in core.parameters()))
        CAP["state_dict_keys"] = list(core.state_dict().keys())

        ex = pipeline_output

        def cpu(x):
            return x.to("cpu") if torch.is_tensor(x) else x

        feats = {k: cpu(v) for k, v in ex["feats"].items()}
        Xn = cpu(ex["coord_atom_lvl_to_be_noised"]) + cpu(ex["noise"])
        t = cpu(ex["t"])

        blocks = {}

        def _keep(v):
            # keep tensors; drop the giant shared feats dict `f` and non-tensors
            return torch.is_tensor(v)

        def mk(name):
            def hook(m, args, kwargs, out):
                if name in blocks:
                    return  # capture first (recycle-0) call only
                rec = {
                    "in_args": [v for v in args if _keep(v)],
                    "in_kwargs": {k: v for k, v in kwargs.items()
                                  if _keep(v) and k != "f"},
                    "out": out,
                }
                blocks[name] = rec
            return hook

        # tee the token-level attention-index builder (called once inside the
        # diffusion_transformer's forward, per recycle) so we can verify the DiT
        # math with the exact indices, decoupled from the geometry port.
        import rfd3.model.layers.blocks as _blocks_mod
        _ci_calls = []
        _orig_cai = _blocks_mod.create_attention_indices

        def _cai_tee(*aa, **kk):
            o = _orig_cai(*aa, **kk)
            _ci_calls.append(o.detach().to("cpu"))
            return o

        _blocks_mod.create_attention_indices = _cai_tee

        with torch.no_grad():
            init_out = core.token_initializer(feats)
            handles = []
            dm = core.diffusion_module
            # extra: capture dtok internals to localize the pair-rep path
            dti = {}

            def mk_dti(nm):
                def h(m, args, kwargs, out):
                    if nm not in dti:
                        dti[nm] = out
                return h
            _dtok = dm.diffusion_token_encoder
            for nm, mod in [
                ("process_z", _dtok.process_z),
                ("transition_2_0", _dtok.transition_2[0]),
                ("transition_2_1", _dtok.transition_2[1]),
                ("pairformer_0", _dtok.pairformer_stack[0]),
                ("pairformer_1", _dtok.pairformer_stack[1]),
            ]:
                handles.append(mod.register_forward_hook(mk_dti(nm), with_kwargs=True))
            for name, mod in [
                ("encoder", dm.encoder),
                ("diffusion_token_encoder", dm.diffusion_token_encoder),
                ("diffusion_transformer", dm.diffusion_transformer),
                ("decoder", dm.decoder),
                ("sequence_head", dm.sequence_head),
            ]:
                handles.append(mod.register_forward_hook(mk(name), with_kwargs=True))
            dm_out = dm(X_noisy_L=Xn, t=t, f=feats, n_recycle=2, **init_out)
            for h in handles:
                h.remove()
        _blocks_mod.create_attention_indices = _orig_cai
        print(f"[capture] create_attention_indices calls (blocks ns): "
              f"{[tuple(c.shape) for c in _ci_calls]}")
        # DiT token-level call has I tokens on dims 1 and 2-ish; pick the [1,50,*] one
        I_tok = init_out["S_I"].shape[0]
        dit = [c for c in _ci_calls if c.shape[1] == I_tok]
        if dit:
            CAP["dt_indices"] = dit[0]
            print(f"[capture] dt_indices: {tuple(dit[0].shape)}")

        CAP["dtok_internal"] = dti
        CAP["feats"] = feats
        CAP["Xn"] = Xn
        CAP["coord_to_be_noised"] = cpu(ex["coord_atom_lvl_to_be_noised"])
        CAP["t"] = t
        CAP["init_out"] = init_out
        CAP["dm_out"] = dm_out
        CAP["blocks"] = blocks
        print(f"[capture] single-step done. dm_out keys: {list(dm_out.keys())}")
        print(f"[capture] core={CAP['core_class']} params={CAP['n_params']:,}")

        # --- full rollout (produces a real structure + rollout reference) ---
        torch.manual_seed(0)
        outputs = super()._model_forward(pipeline_output)
        try:
            aa = outputs[0].atom_array
            CAP["rollout_coords"] = np.asarray(aa.coord, dtype=np.float32)
            CAP["rollout_resname"] = np.asarray([str(x) for x in aa.res_name])
            CAP["rollout_atom_name"] = np.asarray([str(x) for x in aa.atom_name])
        except Exception as e:
            print("[capture] could not extract rollout coords:", e)
        return outputs


class FeatureOnlyCaptureEngine(CaptureEngine):
    """Capture only tensors consumed by the MLX sampler, skipping CPU diffusion."""

    def _model_forward(self, pipeline_output):
        def cpu(x):
            return x.to("cpu") if torch.is_tensor(x) else x

        CAP["feats"] = {k: cpu(v) for k, v in pipeline_output["feats"].items()}
        CAP["coord_to_be_noised"] = cpu(pipeline_output["coord_atom_lvl_to_be_noised"])
        raise FeaturesCaptured


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--name", default="uncond50")
    ap.add_argument("--length", default="50")
    ap.add_argument("--input_json", default=None,
                    help="Path to a JSON inputs dict (binder/motif design). Overrides --length.")
    ap.add_argument("--timesteps", type=int, default=20)
    ap.add_argument("--n_recycle", type=int, default=2)
    ap.add_argument("--seed", type=int, default=0)
    ap.add_argument("--features-only", action="store_true",
                    help="capture Foundry features for MLX without a redundant CPU diffusion rollout")
    ap.add_argument("--output-dir", type=Path,
                    help="fixture directory (default: the managed runtime's oracle directory)")
    args = ap.parse_args()

    here = Path(__file__).parent
    ckpt = (here / "checkpoints" / "rfd3_latest.ckpt").resolve()
    assert ckpt.exists(), f"checkpoint missing: {ckpt}"

    outdir = args.output_dir.resolve() if args.output_dir else here / "oracle"
    outdir.mkdir(parents=True, exist_ok=True)
    (outdir / "out").mkdir(exist_ok=True)

    # input spec: either a full JSON (binder/motif design) or a tiny uncond monomer
    if args.input_json:
        inputs = json.loads(Path(args.input_json).read_text())
    else:
        inputs = {args.name: {"length": str(args.length)}}
    inputs_path = outdir / f"input_{args.name}.json"
    inputs_path.write_text(json.dumps(inputs, indent=2))

    torch.manual_seed(args.seed)
    np.random.seed(args.seed)

    cfgdir = os.path.join(os.path.dirname(rfd3.__file__), "configs")
    with initialize_config_dir(version_base="1.3", config_dir=cfgdir):
        cfg = compose(
            config_name="inference",
            overrides=[
                f"ckpt_path={ckpt}",
                "diffusion_batch_size=1",
                f"inference_sampler.num_timesteps={args.timesteps}",
                f"inference_sampler.n_recycle={args.n_recycle}",
                f"seed={args.seed}",
                "skip_existing=False",
                "prevalidate_inputs=True",
                "verbose=False",
            ],
        )
    cfg_dict = OmegaConf.to_container(cfg, resolve=True)
    run_keys = {"inputs", "n_batches", "out_dir", "_target_"}
    init_cfg = {k: v for k, v in cfg_dict.items() if k not in run_keys}

    engine_cls = FeatureOnlyCaptureEngine if args.features_only else CaptureEngine
    engine = engine_cls(**RFD3InferenceConfig(**init_cfg))
    try:
        engine.run(inputs=str(inputs_path), out_dir=str(outdir / "out"), n_batches=1)
    except FeaturesCaptured:
        print("[capture] Foundry features captured; skipped CPU diffusion rollout")

    # -------- serialize fixtures --------
    arrays, meta = {}, {}
    for key in ["feats", "Xn", "coord_to_be_noised", "t", "init_out", "dm_out",
                "blocks", "dt_indices", "dtok_internal"]:
        if key in CAP:
            flatten(CAP[key], key, arrays, meta)
    for key in ["rollout_coords", "rollout_resname", "rollout_atom_name"]:
        if key in CAP:
            flatten(CAP[key], key, arrays, meta)

    npz_path = outdir / f"oracle_{args.name}.npz"
    np.savez_compressed(npz_path, **arrays)

    manifest = {
        "name": args.name,
        "length": args.length,
        "timesteps": args.timesteps,
        "n_recycle": args.n_recycle,
        "seed": args.seed,
        "features_only": args.features_only,
        "device": "cpu",
        "dtype": "float32",
        "model_class": CAP.get("model_class"),
        "core_class": CAP.get("core_class"),
        "weight_set": CAP.get("weight_set"),
        "which": CAP.get("which"),
        "n_params": CAP.get("n_params"),
        "ckpt": str(ckpt),
        "state_dict_keys_head": CAP.get("state_dict_keys", [])[:40],
        "n_state_dict_keys": len(CAP.get("state_dict_keys", [])),
        "arrays": meta,
    }
    (outdir / f"oracle_{args.name}.manifest.json").write_text(json.dumps(manifest, indent=2))

    print("\n=== ORACLE SAVED ===")
    print("npz:", npz_path, f"({npz_path.stat().st_size/1e6:.1f} MB)")
    print("arrays:", len(arrays))
    print("n_params:", CAP.get("n_params"))
    for k in ["init_out/Q_L_init", "init_out/S_I", "init_out/Z_II", "dm_out/X_L",
              "dm_out/sequence_logits_I", "rollout_coords"]:
        if k in arrays:
            print(f"  {k}: {arrays[k].shape} {arrays[k].dtype}")


if __name__ == "__main__":
    main()
