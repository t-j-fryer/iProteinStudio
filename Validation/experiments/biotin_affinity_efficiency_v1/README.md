# Biotin affinity and CPU efficiency qualification

Freeze 48 previously affinity-scored complete-sequence biotin designs, 24 from
each generator. Within each generator sample four unique sequences from each
historical P(bind) tertile in Phase 0 and optimization separately. This is a
balanced diagnostic cohort, not a representative hit-rate sample.

One resident Boltz session: 200 affinity steps / five samples versus 50 / one,
five affinity recycles and both heads unchanged. Two different seeded repeats,
matched between settings; reverse setting order for the second repeat. Four-case
real smoke before the main cohort. Eight cases repeated under both settings with
the SAME seed to separate numerical reproducibility from different-seed variation.
192 main + 8 smoke + 16 same-seed + 32 overlap = 248 affinity evaluations.

Original outer structure inference is forbidden; verified saved full-precision
pre-affinity inputs and chemical/MSA caches copied without modification. No model
weights copied. Production cached predict arguments are deliberately updated in
this isolated experimental process when switching settings, with assertions.
Per-case seeds reset at featurization and prediction; hash CPU tensor features.
Checksummed batch checkpoints, preserved interrupted attempts, no source overwrite.

Additional efficiency tests: identical 48 geometry checks with 1/2/4/8 process
pools, two reversed repeats, exact output equality. Then serial versus overlapping
independent CPU work (two LASErMPNN workers, two geometry workers) and eight light
affinity predictions, two reversed repeats. LASEr tasks reuse four previously
prepared structures with one/five sequences, matching the separate queued residency
test. Full FASTA/score equality and geometry equality checked. CPU pool startup,
imports and teardown included. This is an overlap microbenchmark, not a live-cycle
qualification; it excludes protonation. No scientific-budget/default promotion.

Run `python3 test_contract.py` in this directory, then `python3 prepare.py` to freeze.
Review the frozen manifest, then `python3 prepare.py --submit <output>` creates an
immutable Studio preflight plan with runtime/source/checkpoint provenance and calls
the run-profile `job_start`. Shared GPU lease is mandatory; no bypass or background
scientific process outside the managed job. The existing watcher controls the
current owner; this experiment only waits for the shared lease.

Report paired P(bind)/composite score rank and threshold changes, top10 retention,
seed variation, timing, process RAM and MPS allocation counters. MPS counters are
allocations, not measured GPU utilization. Runtime gains are whole-request wall
time, not an estimate from steps alone. Review logs for allowed SVD fallback and
unexpected CPU fallback before any promotion.
