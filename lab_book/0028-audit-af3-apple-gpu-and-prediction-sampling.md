---
entry: 0028
title: Audit AlphaFold 3 Apple-GPU correctness and make prediction sampling explicit
date: 2026-08-20
author: codex-gpt-5
type: audit
status: complete
machine: Apple M4 Max, 40-core GPU, 64 GB unified memory, macOS 26.x
tags: [predictors, ui, install, alphafold3, intellifold, mlx, mps]
---

## Context

A 71-residue cobratoxin prediction looked folded under IntelliFold PyTorch but
looked wrong under AlphaFold 3 and IntelliFold JAX/Metal. The questions were
whether the MSA, recycling or input adapters differed; whether the installed
AlphaFold 3 matched official release 3.0.4; whether the independent
`omrikais/alphafold3-mac` MLX port offered a safer GPU route; why the run was
absent from Predictions Library; and how seeds and diffusion samples should be
controlled without offering a CPU execution mode.

This follows the shared-MSA contract in [[0022-share-msas-and-adopt-py2dmol]]
and the prediction workflow in [[0009-prediction-tab]].

## What was done

- Traced the saved run at
  `~/.iproteinstudio/projects/untitled_design/prediction_runs/prediction-20260820-221505`
  from its config and per-engine logs through every adapter.
- Confirmed that all engines consumed the same 100,798-byte A3M with 1,148
  records, seed 42 and ten recycles. The generated run YAML had pointed back to
  an older external checkout, so `predict_batch.py` now copies every chosen A3M
  into `inputs/msas/` before writing durable YAML.
- Ran controlled same-input diagnostics with the same JSON, MSA, weights,
  recycle count, seed and one diffusion sample. CPU was used only as an audit
  reference and is not exposed or selected by the product.
- Verified the installed AlphaFold source is the clean official v3.0.4 commit
  `85c4d20505fd5cef05eac22b534d4e793971ae69`; installed metadata is
  `alphafold3 3.0.4`, `jax 0.10.2`, `jaxlib 0.10.2`, `jax-mps 0.10.9` and
  `tokamax 0.0.12`. Setup now detects version drift and reinstalls/fails rather
  than accepting any importable package. Fresh setup also fetches and verifies
  the immutable `v3.0.4` tag: AF3 derives its package version from Git metadata,
  while its checked-in fallback still says 3.0.2, so fetching only the release
  commit can otherwise install correctly pinned code with incorrect metadata.
- Isolated `jax-mps 0.10.10` without changing the managed environment and ran
  the real cobratoxin AlphaFold 3 fold. It reproduced the 0.10.9 result exactly.
- Inspected `jax-mps` correctness reports. Release 0.10.10 silently ignores
  secondary sort keys; the fix is an unreleased commit after 0.10.10. AlphaFold
  3's MSA Gumbel sampling uses a single-key `sort_key_val`, so that particular
  fix is not an explanation for this target.
- Audited `omrikais/alphafold3-mac` at commit
  `4da480407c191fff86f3f7d6047948c5bb85ddaa`. It is a handwritten MLX model
  whose package declares version 3.0.1 and pins JAX 0.8.1, not another
  configuration of Studio's official 3.0.4 stack.
- Installed the MLX port into a temporary environment, ran it without genetic
  databases using Studio's precomputed AF3 JSON, and hardened its loader for
  the audit. The stock loader silently ignores unmapped weights. A two-way
  coverage check found 11 active MLX tensors not replaced by official weights,
  including `target_feat_embed.weight`, Evoformer pair input projection,
  single/pair output norms and five Evoformer-conditioning tensors. These
  tensors are used in forward inference. The runner itself seeds MLX so such
  randomly initialised parameters are merely repeatable.
- Added Predict controls for independent seed count and diffusion samples.
  Zero diffusion samples means each engine's prior Studio default; the existing
  run defaults therefore do not change. Native stochastic outputs are retained
  as separate browseable results.
- Merged ordinary prediction runs into Predictions Library. Previously that
  view indexed only Target Prep's structure cache while Activity Center alone
  knew about `prediction_runs`.
- Corrected run-history summary keys (`results`/`failures`) to match what the
  Python runner actually writes.
- Kept AlphaFold 3 and IntelliFold JAX GPU-only. The GUI and adapters label the
  Metal routes experimental and do not offer or silently select CPU.

## Results

All structure-quality rows below are one saved 71-aa target on the machine in
the header, with the same 1,148-record MSA, seed 42, ten recycles and one
diffusion sample unless noted. Times are diagnostic observations, not scheduler
benchmarks.

| Condition | n | Metric | Value |
|---|---:|---|---:|
| IntelliFold PyTorch v2-flash / MPS | 1 | pTM | 0.719 |
| IntelliFold PyTorch v2-flash / MPS | 1 | mean pLDDT | 89.8 |
| IntelliFold JAX v2-flash / MPS, best of its existing 5-sample default | 5 | best pTM | 0.34 |
| IntelliFold JAX v2-flash / controlled reference | 1 | pTM | 0.70 |
| AlphaFold 3 v3.0.4 / jax-mps 0.10.9 | 1 | pTM | 0.31 |
| AlphaFold 3 v3.0.4 / jax-mps 0.10.9 | 1 | mean pLDDT | 43.0 |
| AlphaFold 3 v3.0.4 / jax-mps 0.10.10 | 1 | pTM | 0.31 |
| AlphaFold 3 v3.0.4 / jax-mps 0.10.10 | 1 | mean pLDDT | 43.0 |
| AlphaFold 3 v3.0.4 / controlled reference | 1 | pTM | 0.72 |
| AlphaFold 3 v3.0.4 / controlled reference | 1 | mean pLDDT | 84.3 |
| AlphaFold 3 v3.0.4 / jax-mps 0.10.10 | 1 | model inference | 58.25 s |
| AlphaFold 3 v3.0.4 / controlled reference | 1 | model inference | 104.40 s |
| alphafold3-mac strict official-to-MLX coverage | 3,070 model tensors | active tensors left at initial value | 11 |

The MLX port also completed a deliberately non-scientific one-diffusion-step
smoke run after the stock loader ignored those 11 tensors. That run proves the
code launches on Metal; it does not validate structure quality and its output
must not be compared with full diffusion.

## Decision and rationale

1. **Do not integrate `alphafold3-mac` yet.** Native MLX avoids the incomplete
   JAX/MPS StableHLO bridge and is the most plausible long-term Apple-GPU route,
   but silent active random parameters violate Studio's fail-loud requirement.
   Its public end-to-end parity fixture is only 16 residues, two PairFormer
   layers, zero recycles and five diffusion steps; it is not a full production
   fold. The port declares package version 3.0.1 rather than 3.0.4.
2. **Do not promote the unreleased JAX/MPS patch.** The released update did not
   change this structure, and building a private plugin revision would silently
   diverge from the official AF3 stack without evidence that it fixes the model.
3. **Do not offer CPU.** CPU established that MSA/input/recycle handling was not
   the cause, but it remains a diagnostic reference rather than a user backend.
   GPU routes remain opt-in and explicitly experimental; PyTorch IntelliFold,
   Boltz and OpenFold-3/MLX are the routine Apple-GPU choices.
4. **No genetic databases.** Studio's precomputed/cached A3M is embedded into AF3
   fold input and inference runs with `--norun_data_pipeline`. The MLX port's
   database pipeline and its sequence-only placeholder mode add nothing useful:
   the former is unwanted, while the latter discards a real alignment Studio
   already has.

Useful ideas to retain from the MLX project are its native-MLX direction,
per-sample output browsing, resumable job state and explicit no-database mode.
Studio already has the latter three contracts. Native MLX can be reconsidered
only after all official tensors map fail-loud, the port is rebased to 3.0.4, and
a same-input full-model parity suite passes on real proteins and complexes.

## Reproduce

The saved user paths below are evidence for this machine, not paths embedded in
shipped code.

```bash
# Verify installed source and package stack.
git -C /Users/thomasfryer/.iproteinstudio/src/alphafold3 rev-parse HEAD
/Users/thomasfryer/.iproteinstudio/venvs/NanoHunter_alphafold3/bin/python - <<'PY'
from importlib.metadata import version
for name in ('alphafold3', 'jax', 'jaxlib', 'jax-mps', 'tokamax'):
    print(name, version(name))
PY

# Product contract tests and build (all kept awake).
caffeinate -dimsu env PYTHONPYCACHEPREFIX=/private/tmp/iproteinstudio-pyc \
  /Users/thomasfryer/.iproteinstudio/venvs/NanoHunter_boltz/bin/python \
  Tests/test_workflow_pipelines.py
caffeinate -dimsu swift build
```

Primary upstream evidence:

- AlphaFold 3 release 3.0.4:
  <https://github.com/google-deepmind/alphafold3/releases/tag/v3.0.4>
- Official Apple-Silicon PR and its explicit numerical-certification caveat:
  <https://github.com/google-deepmind/alphafold3/pull/699>
- JAX/MPS multi-key sort wrong-result report:
  <https://github.com/tillahoffmann/jax-mps/issues/224>
- AlphaFold3-Mac source:
  <https://github.com/omrikais/alphafold3-mac>

## Limits and what was not tested

- The controlled quality comparison is one short, disulfide-rich monomer. It
  proves a real regression for this target, not a failure rate for all proteins.
- No ligand, multimer, nucleic-acid or template-bearing MPS/MLX parity campaign
  was run.
- The official AF3 Python test files were attempted, but their source-relative
  example fixtures and default CUDA/MPS device assumptions do not run cleanly
  from this installed native package. Actual inference, package/source identity
  and app contracts were tested instead; this does not convert those upstream
  unit-test failures into passes.
- The unreleased JAX/MPS sort fix was inspected but its full LLVM/StableHLO build
  was stopped after the released 0.10.10 end-to-end fold reproduced the defect.
- The MLX port's one-step smoke output is not scientifically valid. A full
  200-step run was intentionally not treated as useful after strict loading
  proved active random parameters.
- Multiple-seed end-to-end runs were not executed for every engine. CLI lowering
  and result discovery are contract-tested; one-seed GPU inference was run.

## Next

- Track a future `alphafold3-mac` revision for fail-loud 100% active-weight
  coverage, an AF3 3.0.4 rebase and full real-input parity data.
- Expand the saved-input MPS quality panel beyond one monomer before changing
  the experimental label.
- If JAX/MPS becomes numerically certified, repeat the exact cobratoxin input
  before changing any default or scheduler claim.
