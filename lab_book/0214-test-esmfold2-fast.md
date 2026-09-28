---
entry: 0214
title: Test ESMFold2-Fast on SUMO monomer and complex
date: 2026-09-28
author: Codex
type: benchmark
status: complete
machine: Apple M4 Max, 40-core GPU, 64 GB unified memory
tags: [predictors, esmfold2, mlx, performance]
---

## Context

Follow-up to 0211/0212: test the Fast checkpoint on the same benign yeast SUMO
monomer and user-supplied binder complex. Fast is explicitly sequence-only.
Official model card: https://huggingface.co/biohub/ESMFold2-Fast .

## What was done

Declared `Validation/experiments/esmfold2_fast_v1/manifest.json`. Pinned the
last unbundled Fast revision `c6c7958d63f5f2f1f0fed0bb9462316f8ccceea6`, compatible
with the existing reference PyTorch runtime and updated MLX c26b9af source.
Reuse the sealed ESMC-6B and environments from 0209/0211; download only the
755,416,924-byte Fast head. Verify official LFS SHA256 before use. Its MSA
encoder is disabled, folding trunk has24 layers (Full48). New September bundled
Transformers export is not this experiment's checkpoint/runtime contract.

Fast3loops/50requested steps follows its official example. Full3/50 and
Full20/100 sequence-only controls separate profile and MSA effects from
checkpoint changes. Both contexts × two backends × three profiles × two calls
in one fresh process per block:24 outputs. Seed42, one diffusion sample per call,
foldFP32/ESMC BF16. First call and resident repeat reported separately, not pooled.
Native sampler coefficients and backend conditioning retained; this is not a
claim of identical RNG or numerical equivalence. CPU tiny-SVD calls counted.

Monomer accuracy: fixed exact-sequence 3QHT chainA core21–96 from prior frozen
reference. Complex: compare common ipSAE, target-aligned binder poses, contacts
and geometry with saved Full/Boltz/Protenix; no experimental complex truth.
New predictions deliberately use no cached homolog MSA. Prior MSA digest:
`c5c2ee22f8430f0144c602338fdb250d6ce69e1f851753bf8a8ce5046702f0ff`.

## Results

Native CPU input preparation passed for both contexts:
query-only tensors[1,1,96] and[1,1,194]. Five CPU audit tests passed (including
target-fit sensitivity to a displaced binder). Downloaded Fast head matches
official SHA256 `60ca19f2898188beba92944365f7b909efd9c99212f5018af75cc47cd9a6184a`.
Biotin job18ca87a890d9 stopped through the broker with checkpoints preserved.
Immutable plan2600f69c9aa7ee6b / job2600f69c9aa7 started under the shared exclusive
lease; phase `paired_20260928T221554148700Z`. No direct GPU-worker launch.

## Decision and rationale

Do not change Studio defaults from this small exploratory panel. Use matched
sequence-only Full rather than attributing every difference to Fast when prior
Full results had an MSA and more compute.

## Reproduce

`python3 Validation/experiments/esmfold2_fast_v1/download_assets.py`, then
`python3 Validation/experiments/esmfold2_fast_v1/preflight.py --start` after the
authorized biotin pause through the installed bridge. Runtime inventory and
frozen run config capture absolute asset paths, code hashes and exact host.

## Limits and what was not tested

No other proteins, seeds, assay accuracy, calibration, latest bundled export,
production integration, long-run memory soak, app build or commit. The small
panel cannot establish general accuracy. No toxin-panel replay.

## Next

Broaden benign monomer/complex coverage and assess confidence calibration before
production integration or default promotion. A Fast mode must expose its explicit
sequence-only contract rather than silently discarding a requested MSA.

## Completed results

Broker job2600f69c9aa7 completed without inference failures at22:29:03 UTC.
All24 outputs passed exact sequences, finite coordinates/confidence and complete
N/CA/C backbone checks. No CA-neighbor violations; all12 complex outputs had
zero interchain heavy-atom pairs below1 Å. These are bounded structural audits,
not full stereochemical validation or evidence of binding. Five CPU tests passed.
Host M4 Max/64GB/macOS26.6.1; Studio HEAD
`bb408add8bb84ef525196cd603f8999b38d93167` with pre-existing uncommitted work.

Times below are measured synchronized model calls including ESMC, folding,
confidence and CPU output return. They exclude loading, feature preparation
and PDB decoding. Each row is one process: first call, then one resident repeat
with seed42. Report both rather than treating them as independent fresh runs.

| Context | Backend | Checkpoint/profile | First s | Repeat s | Core RMSD Å / iPTM |
|---|---|---|---:|---:|---:|
| Monomer | PyTorch | Fast3/50 |2.116|1.250|RMSD2.734|
| Monomer | MLX | Fast3/50 |1.180|0.945|RMSD2.227|
| Monomer | PyTorch | Full3/50 |2.804|2.029|RMSD2.728|
| Monomer | MLX | Full3/50 |1.446|1.279|RMSD2.126|
| Monomer | PyTorch | Full20/100 |8.356|7.998|RMSD1.947|
| Monomer | MLX | Full20/100 |4.692|4.865|RMSD2.410|
| Complex | PyTorch | Fast3/50 |5.466|4.769|iPTM0.9196|
| Complex | MLX | Fast3/50 |2.546|2.551|iPTM0.9217|
| Complex | PyTorch | Full3/50 |8.644|8.324|iPTM0.9237|
| Complex | MLX | Full3/50 |3.989|4.188|iPTM0.9191|
| Complex | PyTorch | Full20/100 |43.681|56.610|iPTM0.9187|
| Complex | MLX | Full20/100 |33.904|36.559|iPTM0.9160|

Requested50/100 steps produced34/68 native denoising iterations, independently
counted through the tiny explicit CPU SVD calls. Requested3/20 loops imply4/21
recurrent passes. Native checkpoint sampler coefficients were retained.
Matched first-call Full/Fast ratios at3/50: monomer1.33× PyTorch and1.23× MLX;
complex1.58× PyTorch and1.57× MLX. Larger speed differences versus earlier Full
runs combine checkpoint, compute and MSA changes; they are not a checkpoint-only
speedup. Fixed run ordering and small n limit precision; thermal state was not
measured. No live app latency or throughput claim.

Historical same-hardware Full20/100+MSA values copied explicitly from0211/0212:
monomer PyTorch9.881s/2.523 Å (median two fresh processes), MLX5.002s/2.381 Å
(median two fresh processes); complex PyTorch55.916s/iPTM0.9223 and
MLX25.725s/iPTM0.9190 (one fresh output each). These historical timings are
not contemporaneous paired controls for a causal MSA-speed claim. In particular,
new MLX Full20/100 sequence-only was slower than its old MSA timing.

Complex Fast PyTorch common ipSAE(min)=0.8378; MLX=0.8286. After SUMO21–96 fit,
Fast binder RMSD versus Boltz is1.097 Å PyTorch/1.223 Å MLX; versus Protenix
0.804 Å/1.387 Å. Fast versus its own backend's historical Full+MSA is0.933 Å
PyTorch/1.472 Å MLX. Confidence remains high and poses broadly agree, but there
is no experimental complex reference and no evidence from an assay.

Same-seed MLX repeats had identical coordinates/confidence at saved precision
for all six blocks. PyTorch CA repeat drift ranged up to0.0134 Å within a chain;
maximum absolute pLDDT delta0.001164 on the0–1 scale and PAE delta0.2781 Å.
No gross numerical failure. The Full PyTorch long complex repeat slowed43.681
to56.610s; this two-call test does not establish a cause or long-run stability.
Across Fast backends, monomer-core drift1.342 Å and complex target-aligned
binder drift1.246 Å show that the ports are not numerically equivalent.

## Artifacts and restoration

`Validation/output/esmfold2_fast_v1/REPORT.md`, `analysis.json`,
`analysis_inputs.json`, raw phase directory, CPU test log, frozen manifests,
inventories and broker receipts preserve the evidence. `structures/` exports
first-call PDBs and target-aligned complex overlays. Analysis command:

```bash
PYTHONDONTWRITEBYTECODE=1 Validation/output/esmfold2_mlx_update_v1/venv/bin/python Validation/experiments/esmfold2_fast_v1/analyse.py Validation/output/esmfold2_fast_v1/paired_20260928T221554148700Z
```

Original biotin job18ca87a890d9 resumed through its existing broker plan after
GPU completion; verified running with no error and saved status/log receipts.
No model weights committed or exported. No Studio defaults changed, Swift build
or commit; this work only adds the isolated validation harness and records.
