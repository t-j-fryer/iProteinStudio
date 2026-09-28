---
entry: 0056
date: 2026-09-28
title: ESMFold2-Fast monomer and complex comparison
status: complete; 24 outputs audited
---

Protocol, paired controls, checkpoint fingerprints, host and limitations are
recorded in project book [0214](../../lab_book/0214-test-esmfold2-fast.md) and
`experiments/esmfold2_fast_v1/manifest.json`. Native single-sequence Fast3/50
versus Full3/50 and Full20/100, PyTorch/MPS and MLX, SUMO96 and binder98+SUMO96.
Two same-seed calls in each of12 fresh model processes, first/resident reported
separately. Existing full20/100 MSA runs are historical contextual controls.
No production setting promotion. Biotin was restored after completion.

## Results

M4 Max/64GB/macOS26.6.1, Studio HEADbb408add8bb84ef525196cd603f8999b38d93167.
Broker job2600f69c9aa7, output phase paired_20260928T221554148700Z. All24 exact
sequence/backbone/finite-output audits passed; no CA-neighbor flags and no
interchain heavy-atom pairs below1 Å in any complex. No inference failure.
Five CPU audit tests passed, including binder displacement under target fit.

Fast first calls: monomer2.116s PyTorch/1.180s MLX; complex5.466s/2.546s.
Resident repeats1.250s/0.945s and4.769s/2.551s respectively. Times are synchronized
model inference including encoder, excluding load/preparation/decode. One first
and one same-seed resident call per process, not two independent fresh replicates.
Matched Full3/50 first calls2.804s/1.446s monomer and8.644s/3.989s complex:
Fast's checkpoint-level gain is1.23–1.33× monomer,1.57–1.58× complex on this
small panel. Full20/100 controls and copied historical MSA measurements are in0214
and the report; do not attribute their combined differences solely to Fast.

Fast monomer crystal-core RMSD2.734 Å PyTorch/2.227 Å MLX. Matched Full3/50
2.728 Å/2.126 Å; Full20/100 sequence-only1.947 Å/2.410 Å. No consistent accuracy
winner from one fixture. Fast complex iPTM0.9196/0.9217, common ipSAE(min)
0.8378/0.8286, target-aligned binder RMSD versus Boltz1.097 Å/1.223 Å. Pose and
confidence agreement are not experimental accuracy or binding validation.

Same-seed MLX repeats identical at saved precision; PyTorch maximum per-chain
CA drift0.0134 Å. Fast backends differ by1.342 Å monomer-core and1.246 Å complex
binder pose. Full long PyTorch complex slows43.681→56.610s on its repeat; cause
and memory soak untested. Requested50/100 diffusion steps give34/68 actual
iterations under native cutoff; no silent CPU fallback, explicit tiny SVD counted.

Pinned Fast revision c6c7958d63f5f2f1f0fed0bb9462316f8ccceea6, head SHA256
60ca19f2898188beba92944365f7b909efd9c99212f5018af75cc47cd9a6184a. Shared sealed
runtime and encoder from0053/0054. Current bundled Transformers export not tested.
No new homolog MSA: cached SUMO checksum only identifies the historical control.
Immutable raw outputs, plans and per-block hash receipts remain under ignored
output; derived report/analysis/structures exported separately. Original biotin
job18ca87a890d9 resumed, status verified. No defaults, app code or commits changed.
