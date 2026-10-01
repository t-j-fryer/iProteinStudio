---
entry: 0251
title: Queue four-target ESMFold2 Full 3/50 validation
date: 2026-10-01
author: Codex
type: benchmark
status: in-progress
machine: Apple M4 Max, 40-core GPU, 64 GB unified memory
tags: [esmfold2, defaults, benchmarking, queue]
---

## Context

User requests Full3loops/50steps, MSA128, five seeds on all four priority targets.
GPU tests in the Add NISE chat must finish first; this block precedes resumption
of Protenix v2 citrate synthase. Follows0250 ESM budget review.

## What was done

Prepared `Validation/experiments/esmfold2_full_3_50_v1`. Retains the original frozen
prediction-scale worker and installed ESMFold2 runtime, weights, input hashes,
profiling, precision and MLX4GiB cache policy. Four cold loads, four warmups,
20 measured predictions. Uses seeds42–46, one output each. Exact paired historical
20/100 controls are receipt-checked. Runtime manifests and checkpoint fingerprints,
current Git revision, input hashes and control receipts are in the frozen manifest.

Registered an immutable normal Studio plan, with no direct GPU launch. A durable
caffeinated queue watcher waits for GPU acceptance, submits the benchmark through
the broker and resumes Protenix afterwards. Shared handoff added to the concurrent
acceptance record; the binder screen follows Protenix.

## Results

No new prediction measurements yet. Two CPU protocol tests pass: missing/failed
and in-progress retry arms hold the queue; valid output receipts pass, while
tampering, wrong MSA depth and mixed resident identities are rejected. Original
control receipts and frozen harness/input hashes passed preflight. Installed
engine detection passed. App source and defaults unchanged.

## Decision and rationale

Evaluate3/50 as a candidate default; do not infer safety from speed alone. This
is a compute-budget comparison, not an implementation-only acceleration claim.
Historical controls are not randomized interleaved measurements. Preserve Smt3
core, MBP domain and dimer assembled-complex comparisons, geometry and memory.

## Reproduce

Use the experiment README and generated manifest/plan in
`Validation/output/esmfold2_full_3_50_v1`. Queue status and handoff are in that
directory. Expensive execution goes through the Studio broker. Output comparisons
will be written to `analysis/comparison.json` and `analysis/REPORT.md`.

## Limits and what was not tested

New GPU outputs and production-default qualification are pending. No new hardware,
ligands or production runtime upgrades. The already interrupted Protenix block
will span resident sessions on resume; its strict single-session figure audit
must not be weakened silently. This is recorded in the handoff for later review.

## Next

Review five-seed speed, crystal agreement, geometry and memory on all four targets
before a separate default promotion. If acceptance scope changes, update/release
the explicit queue gate only once those tests actually finish.

Launch update: latest GPU acceptance receipts all completed, including RFD3 retry and Boltz Full resume check. The watcher submitted plan `plan-86082086db222eb5` as `job-86082086db22` at20:06:42UTC. Broker reports running; first Smt3 block entered. No acceptance work was cancelled.

First-block verification: Smt3 warmup and all five measured seeds finished; paired receipt, exact MSA128 and same-resident audit passed. T4 lysozyme has started. Partial analysis is generated and will refresh at campaign completion.

## Completed benchmark review (2026-10-01)

All20 measured predictions and four warmups completed; all20 measured outputs passed the saved geometry audit, exact MSA128, output-hash and same-resident checks. No OOM. Measured on this Apple M4 Max64GB; historical controls from prediction_scale_v1.

| Target | Median request20/100 →3/50 (s) | Median crystal CA RMSD20/100 →3/50 (Å) |
|---|---:|---:|
| smt3 | 5.819 → 1.466 | 2.360 → 2.295 |
| t4_lysozyme | 18.422 → 3.370 | 1.512 → 1.221 |
| mbp | 102.679 → 33.429 | 1.381 → 3.008 |
| citrate_synthase | 724.468 → 185.878 | 2.304 → 1.572 |

MBP domains remain essentially unchanged: median N-domain RMSD0.457→0.455Å and C-domain0.567→0.563Å. The global difference concerns domain arrangement. It is not a uniform deterioration: three of five paired seeds improved, two worsened. Five seeds do not establish a systematic quality loss or equivalence.

Peak recorded process-tree physical footprint in the new measured outputs was20.14/20.72/22.49/45.80GiB (Smt3/T4/MBP/dimer), broadly unchanged from20.25/20.72/22.29/45.40GiB. These are sampled process-accounting measurements, not total system RAM.

Timing caveat: the other chat started production Swift compilation around20:27UTC while dimer seed45 was running. Possible CPU/host contention affects interpretation of the final dimer seeds. These are instrumented historical-control comparisons, not isolated or randomized idle-host runs.

Queue: ESM job completed20:30:31UTC. The other chat deliberately SIGSTOP-held watcher68597 for final acceptance/app staging; Protenix has not resumed. Respect that hold; the releasing chat is to SIGCONT the same watcher, which retains Protenix→binder ordering.

App defaults remain unchanged pending qualification and review of MBP conformational variability.
