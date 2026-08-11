---
entry: 0002
title: Inherited Apple-Silicon speed lessons from NanoHunter and RFD3
date: 2026-08-10
author: claude-opus-5
type: port
status: complete
machine: Apple M4 Max, 40-core GPU, 64 GB unified memory, macOS 26.x
tags: [performance, predictors, rfd3, scheduling, reference]
---

## Context

Studio's job is to hand a novice the *measured* best settings without asking them to
understand any of this. Before writing a line of scheduling code, this entry captures
what the sibling repos already established empirically, so that later Studio entries can
cite a number instead of re-deriving it.

**Every number below was measured in the sibling repos, not in Studio.** Sources are
`/Users/thomasfryer/NanoHunter/output/Paper` (tables `T01`–`T20`, curated by
`scripts/organise_paper_outputs.py`), `NanoHunter/docs/{MPS_OPTIMIZATION,
PREDICTOR_SPEED_INTERPRETATION,DEVICE_THROUGHPUT_CALIBRATION}.md`, and
`/Users/thomasfryer/RFD3/README.md`. All are the same M4 Max as this header. Anything
Studio measures itself will get its own entry.

The single most important framing, which the rest of this entry keeps returning to:

> **Process parallelism and native batching are different dimensions and must be
> calibrated separately.** Process parallelism runs several model instances so their
> host work and GPU command streams overlap; it duplicates weights and contends for one
> GPU. Native batching feeds several inputs to *one* loaded process, amortising model
> load and shape compilation. "Use 12" is meaningless — 12 could be one loaded model or
> three competing ones, and those have opposite memory behaviour.

## Results

### 1. There is no single best predictor setting — each has a different optimum

96-aa SUMO monomer, each predictor's own default recycles (Boltz-2 and OpenFold-3 use 3;
IntelliFold and AF3 use 10), 3 measurement blocks. Source: `T01`.

| Predictor | Best process count | s/prediction | Peak unified memory | p1 | p2 | p4 |
|---|---:|---:|---:|---:|---:|---:|
| Boltz-2 | **1** | **10.90** | 9.98 GiB | 10.90 | 12.50 | 12.90 |
| Boltz-2 + potentials | **2** | **21.44** | 17.72 GiB | 24.06 | 21.44 | 21.80 |
| AlphaFold 3 | **2** | **27.67** | 18.21 GiB | 29.16 | 27.67 | 32.88 |
| OpenFold-3-MLX | **2** | **27.53** | 29.62 GiB | 31.53 | 27.53 | 31.08 |
| IntelliFold v2-flash (PyTorch) | **4** | **41.46** | 25.24 GiB | 48.64 | 45.79 | 41.46 |

Boltz already saturates the GPU with one process — extra processes bought nothing and
cost 3× the memory. IntelliFold has enough host-side dead time that four processes still
help. **A single global `--max-parallel` for all predictors is wrong.**

Model size does not predict runtime: IntelliFold v2-flash's checkpoint is ~415 MiB
against Boltz's ~2.1 GiB, yet flash is the *slowest* at operational defaults. It loses
the time to ten recycles, fp32-forced MPS execution (Accelerate rejects fp16/bf16 on
that path) and host coordination.

### 2. The optimisations that actually paid, and the ones that did not

Matched-compute comparisons. Source: `T17`, `docs/MPS_OPTIMIZATION.md`.

| Predictor | Change | Before (s) | After (s) | Verdict |
|---|---|---:|---:|---|
| IntelliFold | Exact 96-token bucket | 52.77 | 23.11 | **2.28× — biggest single win** |
| AlphaFold 3 | 128-token bucket (vs 256) | 38.71 | 24.46 | **1.58×** |
| AlphaFold 3 | Native directory batching (b1→b4) | 37.33 | 27.16 | **1.37×** |
| IntelliFold | JAX/MPS backend vs PyTorch/MPS | 11.39 | 9.15 | **1.24×**, but 14.3→26.8 GiB |
| IntelliFold | `OMP/VECLIB_NUM_THREADS=1` | 34.34 | 26.66 | **1.29×** (IntelliFold only) |
| IntelliFold | 3 recycles instead of 10 | 43.49 | 16.43 | 2.65× — but this is a *quality* change |
| OpenFold-3 | MLX kernels | 37.82 | 35.71 | 1.06% — modest |
| AlphaFold 3 | JAX compile cache | 64.24 | 60.36 | 1.06× |
| AlphaFold 3 | Async dispatch | 24.46 | 23.99 | negligible; **hurt** the JAX IntelliFold path |
| Boltz | `OMP/VECLIB_NUM_THREADS=1` | 17.03 | 18.98 | **worse — do not apply to Boltz** |
| Boltz | `PYTORCH_MPS_PREFER_METAL=1` | 17.03 | 17.18 | no gain |
| Boltz | `PYTORCH_MPS_FAST_MATH=1` | 17.03 | 17.33 | no gain, and adds numerical risk |
| Boltz | Steering potentials | 10.90 | 24.06 | 2.2× *cost* — a method, not a toggle |

Three things to carry forward:

- **Token bucket padding is the cheapest large win available.** A 100-aa binder plus a
  96-aa target is 196 tokens and belongs in the 256 bucket, not 512. Getting the bucket
  wrong does avoidable work on every single prediction of a campaign.
- **Thread limiting is predictor-specific and has opposite signs.** It must be applied
  per predictor process, never globally. NanoHunter already does this correctly and
  exposes `NANOHUNTER_INTELLIFOLD_OMP_NUM_THREADS` to override.
- **The generic MPS environment switches are dead ends.** They were tested and rejected.
  Do not re-add them hoping for free speed.

Byte-identical output was confirmed for the thread-limit and MPS-cleanup changes,
including at ten recycles. Those change resource scheduling, not arithmetic.

### 3. AlphaFold 3: batching and concurrency interact

96-aa SUMO, 3 replicates. Source: `T05`.

| processes × native batch | total inputs in flight | s/prediction | peak memory |
|---|---:|---:|---:|
| 1 × 1 | 1 | 37.33 | 9.78 GiB |
| 1 × 4 | 4 | 24.76 | 10.13 GiB |
| 1 × 16 | 16 | 29.20 | 11.47 GiB |
| **2 × 4** | **8** | **22.05** | 18.19 GiB |
| 2 × 5 | 10 | 25.95 | 18.38 GiB |
| 3 × 4 | 12 | 25.21 | 27.66 GiB |

Optimum is **2 processes × native batch 4**. Note that both dimensions have interior
optima and that 1×16 is *worse* than 1×4 — more inputs in flight is not monotonically
better. AF3 pays an XLA compile cost per new token shape, so a persistent compilation
cache (`ALPHAFOLD3_COMPILATION_CACHE_DIR`) and shape-homogeneous batches matter.

The conspicuous `NotImplementedError` in AF3 logs is caught inside AF3/Tokamax capability
selection. It is **not** evidence of CPU fallback; the benchmark found no CPU-fallback
warning signature. Do not "fix" it.

### 4. IntelliFold JAX backend: faster, much hungrier, and there is a frugal setting

96-aa SUMO. Source: `T18`.

| Backend | Configuration | n | s/prediction | Peak effective memory |
|---|---|---:|---:|---:|
| PyTorch/MPS v2-flash | 16 inputs × 4 processes | 3 | 11.388 ± 0.181 | 14.32 GiB |
| **JAX/MPS v2-flash** | 16 inputs × 4 processes | 3 | **9.154 ± 0.200** | 26.82 GiB |
| JAX/MPS v2-flash | 4 inputs × 1 process, async off | 1 | 9.34 | **6.66 GiB** |
| JAX/MPS v2-flash | 4 inputs × 1 process, async **on** | 1 | 11.87 | 6.61 GiB |

The headline is 1.24× for 1.9× the memory. But the single-replicate `p1 × dir4` row is
strategically interesting for Studio: **9.34 s at 6.7 GiB is within 2% of the 26.8 GiB
configuration**. If that holds up under replication it is by far the better default for
a laptop, and it is the first thing Studio should measure itself. Async dispatch was a
clear negative here even though it was neutral for AF3.

The JAX runner is AF3-derived, so its outputs carry AF3 code/legal provenance; NanoHunter
relabels the prediction software as IntelliFold and repairs the converted schema's
NUL-padded model identifier. Mean pLDDT differed slightly between backends (0.8668 JAX
vs 0.8559 PyTorch) — these are **not** bit-identical implementations, unlike the
thread-limit change.

### 5. Length changes the optimum — a monomer profile cannot be extrapolated

Selected schedules per binder length against SUMO. Source: `T07`.

| Predictor | 50 aa (146 tok) | 100 aa (196 tok) | 200 aa (296 tok) | 400 aa (496 tok) |
|---|---|---|---|---|
| Boltz | p2 × b4, 13.4 s | p1 × b4, 28.1 s | p1 × b4, 55.5 s | p1 × b1, 173.1 s |
| Boltz + potentials | p2 × b2, 34.7 s | p2 × b2, 51.9 s | p1 × b2, 93.7 s | p1 × b1, 236.4 s |
| IntelliFold | p2 × b4, 41.4 s | p4 × b4, 40.3 s | p1 × b4, 122.0 s | p1 × b1, 124.1 s |
| AlphaFold 3 | p2 × b2, 56.9 s | p2 × b2, 58.2 s | p1 × b2, 217.4 s | p1 × b1, 221.4 s |
| OpenFold-3 | p2 × b4, 20.4 s | p1 × b4, 38.6 s | p1 × b4, 63.0 s | p1 × b1, 176.4 s |

Concurrency collapses to 1 as designs get long. The device calibrator encodes this and
fingerprints machine, predictor package, model files and runner — a mismatched profile is
**rejected rather than silently reused**. Studio must preserve that behaviour; a stale
profile from another Mac is worse than no profile.

Note the calibrator's profile contains protein–protein probes only (`ligand_atoms=0`).
Ligand jobs deliberately fall back to live one-run memory calibration rather than
inheriting a protein-only optimum.

### 6. RFdiffusion3 on MLX behaves differently again

200 diffusion steps, 2 recycles, bf16. Source: `RFD3/README.md`.

| Target | batch 1 | 2 | 4 | **8** | 16 | 32 |
|---|---:|---:|---:|---:|---:|---:|
| aCbx (protein) | 11.54 | 9.55 | 8.66 | **8.00** | 14.75 | — |
| fluorescein (ligand) | 10.29 | 9.13 | 8.49 | **6.95** | 8.07 | 9.79 |

Here `--batch-size N` is **true native MLX tensor batching** — one process evaluating N
independent trajectories of identical shape — unlike the predictors' "native batching",
which is sequential directory reuse. Designs in one batch share target, binder length and
conditioning but have independent random states, so they are genuinely distinct backbones.

Batch 8 is the optimum for both. Critically, peak physical footprint was only ~4.6–8.6 GB
across batch 1–32, so **the knee is Metal kernel/temporary-tensor behaviour, not memory
capacity. Choosing a batch size from free RAM is unsafe.**

Different lengths cannot share a tensor batch. For a mixed-length queue:

| Concurrent RFD3 processes | Native batch each | s/design | designs/min |
|---:|---:|---:|---:|
| 1 (serial) | 8 | 7.48 | 8.0 |
| **2** | 8 | **6.27** | **9.6** |
| 4 | 8 | 9.79 | 6.1 |

**Two shape queues × native batch 8** is the production rule, +19.2% over serial. Four
processes regressed with ≥39% of system memory still free. bf16 beat both fp32 and int8.

### 7. Design-campaign cost and a warning about how to read it

20 independent runs per condition, 5 redesign cycles, 100-aa de novo binder vs SUMO,
SolubleMPNN, no post-predictor. Source: `T10`, `T11`.

| Design predictor | Wall time | s per structural proposal | Final iPTM (mean ± sd) |
|---|---:|---:|---:|
| Boltz-2 | 3962 s | 33.0 | 0.735 ± 0.137 |
| Boltz-2 + potentials | 7320 s | 61.0 | 0.830 ± 0.075 |
| OpenFold-3 | 7912 s | 65.9 | 0.566 ± 0.110 |
| AlphaFold 3 | 8532 s | 71.1 | 0.470 ± 0.232 |
| IntelliFold | 9032 s | 75.3 | 0.605 ± 0.135 |

**Do not read the iPTM column as a quality ranking.** Each design loop optimises against
its own predictor, so this is self-scored: it measures how readily a predictor can be
satisfied by sequences designed to satisfy it, which is exactly the quantity most at risk
of being gamed. Boltz-2 + potentials being both highest and tightest is consistent with
that reading. Cross-predictor validation is the whole reason Studio offers an orthogonal
post-predictor, and it is the number that should drive user-facing selection.

(OpenFold-3's mean complex pLDDT in that table is 0.296, far below the others. OpenFold
stores pLDDT on a 0–100 scale and the analysis divides by 100, so a residual scale or
field-mapping problem here is more likely than a real quality collapse. **Unresolved —
do not surface OpenFold pLDDT in Studio's UI until this is traced.**)

## Decision and rationale

Studio adopts these as the basis of its scheduling, rather than exposing raw knobs:

1. **Per-predictor scheduling, not one global parallelism setting.** Justified by §1,
   where the optimum ranges from p1 (Boltz) to p4 (IntelliFold).
2. **Prefer NanoHunter's device throughput profile when a valid one exists**, falling
   back to live memory calibration otherwise, and rejecting fingerprint mismatches.
   Rebuilding this logic in Swift would duplicate a validated implementation — §5.
3. **Token bucketing and the compile cache are always on.** They are pure wins with no
   quality cost (§2) and no user could reasonably be expected to choose them.
4. **Boltz-2 stays the default design predictor**; it is 3.4× cheaper per proposal than
   the slowest alternative (§7) and needs only one process. Potentials, AF3, OpenFold-3
   and IntelliFold are offered as explicit, labelled choices with their real cost shown.
5. **RFD3 defaults to native batch 8 with 2 shape queues, bf16**, hard-coded from
   measurement rather than derived from free memory — §6 shows memory-derived choices are
   actively unsafe here.
6. **The IntelliFold JAX backend is offered but not yet the default.** 1.24× for 1.9×
   memory is a bad trade on a 16 GB machine, and the frugal `p1 × dir4` configuration
   that might make it a clear win has n=1.

Rejected: exposing `PYTORCH_MPS_*` switches (measured useless, §2); deriving parallelism
from CPU core count or free RAM (§5, §6); a single "speed slider" mapping to one global
process count (§1 makes it meaningless).

## Reproduce

The measurements themselves live in the sibling repos:

```bash
# Predictor / scheduler benchmarks
cd /Users/thomasfryer/NanoHunter
python3 scripts/benchmark_mps_optimizations.py \
  --out-dir output/mps_optimization_benchmark --suite scheduler --folds 4

# Per-device schedule profile (opt-in; no powermetrics, no password, no energy data)
./calibrate_device.sh --target-msa /absolute/path/to/SUMO_target_full_msa.a3m

# Curated paper tables/figures cited above
MPLCONFIGDIR=/tmp/nanohunter-mpl python3 scripts/organise_paper_outputs.py
# -> output/Paper/{manifest.tsv,tables/,figures/}

# RFD3 batching
cd /Users/thomasfryer/RFD3
.venv/bin/python scripts/benchmark_process_groups.py
```

## Limits and what was not tested

- One machine (M4 Max, 64 GB). Nothing here transfers to an M1/M2 Air or a 16 GB
  machine without recalibration, and the memory-hungry configurations (JAX IntelliFold
  p4, OpenFold-3) will simply not fit on smaller Macs.
- Predictor benchmarks are a **96-aa monomer** or a 161-token two-chain complex. Ligand
  atom counts, steering potentials, and complex topology are separate feature classes and
  were explicitly not transferred.
- The RFD3 batching optimum was measured at 81–131 token fixtures. Longer binders were
  not swept.
- `T18`'s most interesting row (JAX `p1 × dir4`) is a **single replicate**.
- OpenFold-3 pLDDT scaling is unresolved (§7).
- Everything is version-pinned in effect: Boltz 2.2.1, IntelliFold v2-flash, AF3 3.0.4,
  OpenFold-3-MLX, RFD3 Foundry checkpoint `2025_12_01_remapped`. A package bump
  invalidates these numbers and should trigger recalibration.

## Next

- Measure the JAX IntelliFold `p1 × dir4` configuration with n≥3 in Studio's own
  environment; if it replicates, it becomes the IntelliFold default.
- Trace the OpenFold-3 pLDDT scale problem before exposing that metric.
- Extend the device calibration to a ligand/atom-count workload class, which currently
  falls back to conservative live calibration.
- Studio has no measurements of its own yet. The first should be end-to-end campaign
  wall time through the app versus the same campaign launched from the terminal, to
  confirm the GUI adds no scheduling overhead.
