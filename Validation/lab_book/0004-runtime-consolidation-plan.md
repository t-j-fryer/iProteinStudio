---
entry: 0004
title: Safely test runtime consolidation and PyTorch 2.14
date: 2026-09-01
status: complete
machine: Apple M4 Max, 40-core GPU, 64 GB unified memory, macOS 26.6.1
---

## Question

Can Studio reduce managed runtime complexity using newer compatible dependency
choices without changing predictions, enabling CPU execution or modifying an
installed runtime? The first candidate is Boltz 2.2.1 with PyTorch 2.14.

## Safety design

The trusted application state was committed and pushed to
`agent/mps-runtime-stabilization`. Experiments occur on
`experiment/runtime-consolidation-pytorch214`. Disposable environments live
under ignored Validation output, while `~/.iproteinstudio` is read-only. Current
checkpoint assets are reused by path to avoid a scientifically irrelevant 1.8 GB
data duplication. Existing experiment output is never overwritten.

## Controlled tests

Interleave three fresh-process current PyTorch 2.13 controls and three isolated
PyTorch 2.14 candidates on the exact same 71-residue input, MSA, seed, sample
count, model checkpoint and FP32/no-reset launcher. Audit package changes, MPS
selection, fallback lines, output cardinality, geometry, confidence and timing.

The initial 2.14 wheel is the official staged test-index wheel because the stable
release is scheduled for 2026-09-02. It cannot be promoted until repeated with
the final stable wheel.

The full lock audit also identified Protenix v2/Mini and Protenix Constraint as
the strongest environment-sharing candidate. A paired native-MPS Constraint run
therefore compared its dedicated environment with the ordinary Protenix
dependency environment and an explicit Constraint source overlay.

## Results

The candidate Boltz environment changed only PyTorch (2.13.0 to 2.14.0), passed
the 69-package consistency check and produced valid, deterministic geometry.
The two warm candidate processes averaged 16.650 s versus 16.925 s for three
controls. Candidate structures differed from control by 0.00001119 A CA RMSD;
pTM differed by approximately 0.00000006 and complex pLDDT was identical. The
three controls each reported the known SVD fallback, while the three candidates
reported none. The first candidate process took 64.845 s; this unexplained cold
penalty is retained and blocks a blanket speed claim.

The Protenix shared-dependency output differed from the dedicated Constraint
control by 0.00004417 A CA RMSD. pLDDT differed by 0.000008, iPTM by 0.00000018
and wall time was 60.999 versus 64.065 s. Both runs proved native MPS, strict
checkpoint loading, exact output cardinality and valid geometry with no CPU
fallback.

The evidence supports a stable-wheel/M1 promotion trial for Boltz and a full
three-model installer regression for a shared Protenix dependency environment.
It does not support merging the remaining runtime boundaries. Exact tables and
interpretation are in
`Validation/experiments/runtime_consolidation_v1/RESULTS.md`; raw manifests are
under ignored `Validation/output/runtime_consolidation_v1/`.

## Not yet tested

Boltz 2.14 has not yet been repeated with the stable release or on M1 Pro.
Multi-batch, ligand, multimer and resident routes remain future Boltz gates. A
shared Protenix installation has not yet run ordinary v2, Mini, repeated-seed or
installer update/rollback/removal acceptance. The production locks and installed
runtime were not modified.
