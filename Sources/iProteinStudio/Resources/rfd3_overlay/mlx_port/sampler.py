"""RFdiffusion3 MLX sampler with upstream-compatible partial diffusion.

This is the Javier BQ sampler with the `partial_t` schedule contract ported from
Foundry production. `partial_t` is an Angstrom noise magnitude: the normal EDM
schedule is truncated to values <= that magnitude. No CPU inference fallback is
introduced.
"""
from __future__ import annotations

import numpy as np
import mlx.core as mx

import rfd3_mlx as R
from token_init import TokenInitializer
from geom import create_attention_indices_mlx


def edm_noise_schedule(num_timesteps, sigma_data=16, s_min=4e-4, s_max=160, p=7):
    t = np.linspace(0.0, 1.0, num_timesteps)
    a, b = s_max ** (1 / p), s_min ** (1 / p)
    return (sigma_data * (a + t * (b - a)) ** p).astype(np.float64)


def partial_noise_schedule(schedule: np.ndarray, partial_t: float | None) -> np.ndarray:
    """Match Foundry production's schedule filtering and fail loudly."""
    if partial_t is None:
        return schedule
    value = float(partial_t)
    if not np.isfinite(value) or value < 0.1 or value > 15:
        raise ValueError(f"partial_t must be finite and between 0.1 and 15 A; got {value}")
    selected = schedule[schedule <= value]
    if selected.size == 0:
        selected = schedule[-1:]
    if selected.size < 2:
        raise ValueError(
            f"partial_t={value} A selected fewer than two denoising steps; "
            "increase partial_t or the diffusion-step count"
        )
    return selected


def partial_t_from_features(feats) -> float | None:
    raw = feats.get("partial_t")
    if raw is None:
        return None
    values = np.asarray(raw, dtype=float)
    values = values[np.isfinite(values)]
    return float(values.mean()) if values.size else None


class Sampler:
    def __init__(self, w, num_timesteps=200, n_recycle=2, sigma_data=16,
                 gamma_0=0.6, gamma_min=1.0, noise_scale=1.003, step_scale=1.5,
                 s_min=4e-4, s_max=160, p=7, seed=0):
        self.w = w
        self.ti = TokenInitializer(w, "token_initializer", n_pairformer=2, n_head=16)
        self.dm = R.DiffusionModule(w, sigma_data=sigma_data, n_recycle=n_recycle, n_head_atom=4)
        self.schedule = edm_noise_schedule(num_timesteps, sigma_data, s_min, s_max, p)
        self.gamma_0, self.gamma_min = gamma_0, gamma_min
        self.noise_scale, self.step_scale = noise_scale, step_scale
        self.seed = seed

    def generate(self, feats, D=1, coord_to_be_noised=None, verbose=False):
        mx.random.seed(self.seed)
        tok_idx = np.asarray(feats["atom_to_token_map"]).astype(np.int64)
        L = tok_idx.shape[0]
        is_motif = np.asarray(feats["is_motif_atom_with_fixed_coord"]).astype(bool)
        keep = mx.array((~is_motif).astype("float32"))[None, :, None]

        schedule = partial_noise_schedule(self.schedule, partial_t_from_features(feats))
        init_out = self.ti(feats)
        c0 = float(schedule[0])
        base = mx.zeros((D, L, 3)) if coord_to_be_noised is None else mx.array(coord_to_be_noised)
        if base.ndim == 2:
            base = base[None]
        X_L = base + c0 * mx.random.normal((D, L, 3)) * keep

        out = None
        for step, (c_tm1, c_t) in enumerate(zip(schedule, schedule[1:])):
            gamma = self.gamma_0 if c_t > self.gamma_min else 0.0
            t_hat = c_tm1 * (gamma + 1.0)
            eps = self.noise_scale * float(np.sqrt(max(t_hat ** 2 - c_tm1 ** 2, 0.0))) \
                * mx.random.normal((D, L, 3)) * keep
            X_noisy = X_L + eps
            attn_idx = create_attention_indices_mlx(feats, 128, 2, X_noisy)
            t_vec = mx.array(np.full((D,), t_hat, dtype="float32"))
            out = self.dm(X_noisy, t_vec, feats, init_out, attn_idx, None)
            X_den = out["X_L"]
            delta = (X_noisy - X_den) / t_hat
            X_L = X_noisy + self.step_scale * (c_t - t_hat) * delta
            mx.eval(X_L)
            if verbose and step % 20 == 0:
                print(f"  step {step:3d}  t_hat={t_hat:7.3f}  |X|max={float(mx.max(mx.abs(X_L))):.2f}")
        if out is None:
            raise RuntimeError("diffusion schedule contained no denoising step")
        return {"X_L": X_L, "sequence_logits_I": out["sequence_logits_I"],
                "sequence_indices_I": out["sequence_indices_I"]}
