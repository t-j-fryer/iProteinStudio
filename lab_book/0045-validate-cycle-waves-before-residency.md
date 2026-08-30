---
entry: 0045
title: Validate cycle waves before promoting model residency
date: 2026-08-30
author: codex
type: audit
status: complete
machine: Apple M4 Max, 40-core GPU, 64 GB unified memory, macOS 26.x
tags: [iterative-design, persistence, batching, intellifold, protenix, validation]
---

## Context

The ResidentFold beta experiment reported lower four-input wall time when all
already-materialized inputs were handled by one process instead of two directory
processes. Inspection showed that its `one_load_replay` arm was not a live
iterative worker: all future inputs existed before model load, with no MPNN gap,
cancellation, worker death, mixed length or full campaign. This entry follows
[[0002-inherited-speed-lessons]] and [[0039-resume-provenance-and-persistent-results]].

## What was done

- Audited the beta protocol and separated per-trajectory, cycle-wave directory
  reuse and true campaign residency in `docs/RESIDENT_INFERENCE.md`.
- Corrected GUI wording: cycle-wave reloads once per cycle and is not one tensor
  batch or a campaign-resident model.
- Found and fixed a real mismatch: the runner allowed Protenix cycle-wave at
  validation time but its executor had no Protenix branch. v2, Mini and
  Constraint now route a full YAML directory through the shared adapter and
  normalize each output.
- Added explicit iterative `--predictor-seed` and `--predictor-samples` controls;
  `auto` preserves existing engine defaults. Validation can now hold generated
  work constant at one seed and one sample.
- Preserved cycle-wave batch and campaign timing files on resume; a no-work
  resume previously erased timing provenance.
- Added experimental IntelliFold `length-aware` buckets. For a 96-aa target and
  65–150-aa binders the declared candidates are 192, 224 and 246 total tokens,
  rather than padding every trajectory to 246. This policy is not promoted.
- Created governed `Validation/` experiment, output, audit, Lab Book, Biotite
  P-SEA secondary-structure and publication-SVG contracts. Speed and helix
  contrasts are separate; cycle 00 is excluded from design/structure endpoints.

## Results

The inherited beta numbers were not remeasured here. That beta report gave
one-directory versus two-directory geometric-mean speedups of 1.39× for
IntelliFold v2-flash, 1.15× for Boltz 2, 1.15× for Protenix v2 and 1.34× for
Protenix Constraint on two paired four-input blocks. They remain exploratory
external evidence, not production defaults.

New bounded MPS smoke measurements on this worktree:

| Condition | n | Metric | Value |
|---|---:|---|---:|
| Protenix v2, one 227-token SUMO complex, cycle-wave cycle 00, one sample | 1 | adapter batch wall time | 98.49 s |
| same | 1 | logged model forward time | 68.34 s |
| Boltz 2, one 227-token SUMO complex, cycle 00 | 1 | predictor directory wall time | 37.59 s |
| Boltz 2, same trajectory after SolubleMPNN redesign, cycle 01 | 1 | predictor directory wall time | 36.26 s |
| IntelliFold v2-flash, one SUMO cycle 00 input | 1 | predictor directory wall time | 48.93 s |
| IntelliFold full v2, one SUMO cycle 00 input | 1 | predictor directory wall time | 234.17 s |
| Protenix Mini, one SUMO cycle 00 input | 1 | predictor directory wall time | 17.03 s |
| Protenix Constraint v0.5 before absent-feature fix, 227 tokens | 1 | requested attention buffer | 39.57 GB (failed) |
| Protenix Constraint v0.5 after fix, same 227-token input | 1 | model forward time | 33.83 s |
| same | 1 | adapter directory wall time | 62.58 s |
| same | 1 | synchronized MPS driver allocation | 3.98 GB |

Both predictors logged native Apple GPU use under `caffeinate`; the Protenix
result produced exactly one normalized CIF/confidence pair. The Boltz route
completed predictor → SolubleMPNN → predictor, changed the binder from the
unknown-rich initialization to a 131-aa designed sequence, and a second launch
reused both predictions and the recorded redesign without GPU recomputation.
Biotite P-SEA successfully assigned all 131 cycle-01 binder residues.

The remaining design engines also completed one-input SUMO cycle-wave native-
MPS smokes: IntelliFold v2-flash, IntelliFold full v2 and Protenix Mini. The
Constraint failure was traced to an absent substructure feature: upstream
flattened an all-zero N×N map into an N² Transformer sequence, making attention
memory scale as N⁴. The patch evaluates the identical zero token once and
broadcasts the checkpoint-defined result. On MPS with the official checkpoint,
the explicit and shortcut paths agreed at 2, 8 and 16 tokens with maximum
absolute error 9.54e-7; the same 227-token SUMO input then completed and emitted
exactly one normalized structure/confidence pair.
The installer applies this as a separately fingerprinted, idempotent patch.
Detection marks older Constraint runtimes as needing an update while retaining
already verified checkpoint files; the launch adapter refuses an outdated
receipt instead of risking the original allocation failure.
The managed runtime on the test Mac was repaired through that installer path:
all verified model/data downloads were reused, component detection returned
`ok`, and the updated adapter's native-MPS receipt audit passed.

## Decision and rationale

Directory reuse is worth retaining and Protenix cycle-wave was a correctness bug
that needed repair. A campaign-resident default is not yet justified. A model
server must exist and pass the declared lifecycle gates before the disabled
`resident_*` validation arms can run. Calling directory replay “persistent” or
using it to choose a default would overstate the evidence.

Length-aware padding is relevant to IntelliFold only. Boltz and Protenix iterate
directory records and do not demonstrate padding every record to the longest
record; splitting them into length buckets could add model loads without removing
a real padded-batch cost. Fixed-length nanobody scaffolds need one shape.

## Reproduce

```bash
python3 Validation/experiments/resident_design_v1/campaign.py plan
caffeinate -dimsu python3 Validation/experiments/resident_design_v1/campaign.py run
python3 Validation/experiments/resident_design_v1/campaign.py analyze
bash Tests/test_iterative_cli_contract.sh
SDKROOT=/Library/Developer/CommandLineTools/SDKs/MacOSX15.4.sdk \
  CLANG_MODULE_CACHE_PATH=/tmp/iproteinstudio-clang-cache \
  SWIFTPM_MODULECACHE_OVERRIDE=/tmp/iproteinstudio-swift-cache \
  swift build --disable-sandbox
```

## Limits and what was not tested

The complete 12-trajectory × 5-design-cycle matrix is not yet run. All six
requested engines passed bounded cycle-wave launch tests, but only Boltz was
exercised through a real SolubleMPNN redesign and resume. No live resident
worker was implemented or promoted. The 32-token bucket spacing is a testable
candidate, not a measured optimum. No memory soak, reverse-order equivalence,
cancellation or forced worker-death test has run.

## Next

Run the manifest-frozen full matrix when an uninterrupted validation window is
available. Prototype a campaign-owned request worker separately; enable
resident arms only after lifecycle and resume acceptance.
