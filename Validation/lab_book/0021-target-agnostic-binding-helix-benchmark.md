---
entry: 0021
title: Declare a target-agnostic binding helix-strength benchmark
date: 2026-09-07
author: Codex
type: benchmark
status: complete; aCbx v7 benchmark audited
machine: Apple M4 Max, 64 GB unified memory, macOS 26.6.1
tags: [secondary-structure, protein-binding, predictors, mcp]
---

## Context

The completed target-free helix benchmark showed engine-dependent effects of
initialization-only helix kill. The next question is whether strength 1 versus
paired strength 0 changes binder secondary structure during target-conditioned
optimization without destroying predicted interface scores. The implementation
was kept target-agnostic so a non-toxin target could be provided, after which
the user selected the shipped aCbx FASTA and MSA for this campaign instance.

## What was done

Declared seven predictor variants, two
strengths, ten paired 90-aa trajectories and five cycles. A one-trajectory pilot
in every arm gates all cohort expansion. Exact target FASTA/MSA bytes, query
identity, source hashes, model/checkpoint inventories, pipeline code, plan
digests, seeds, scheduler and output hashes are fail-closed campaign inputs.

The first v1 planning request was rejected by the managed import-root policy
before inference because its generated template lived in Validation output. No
plan was persisted. V2 corrected the boundary without broadening policy, then
stopped after its first completed pilot when the auditor assumed native resident
output was under the per-run directory. V3 corrected native-link validation but
exposed a second run-vs-cycle-wave exit-receipt assumption. V4 validates either
scheduler layout using complete, zero-valued receipts and a completed broker
state. No inference output is reused between versions.

## Results

Nine declaration/input/audit-regression tests and all 28 production MCP
argument-normalization checks pass. The aCbx target is 71 aa and its query-matched MSA contains 1,148
records (SHA-256
`377a3af41f6816683c9b06241fafd2e0c2bc6b0129c2f4a78387ad36f75f34cf`).
The v4 manifest SHA-256 is
`06c249a12d9c86336456fb9e197097bc860a9636603de6f784cd6b7348f349e0`;
the staged-runtime receipt SHA-256 is
`983671d67bda3ba5b6e30e66fce0056723746462eaec3e229da2edfba58e75ce`.
The full v4 audit replay passed against preserved v3 raw files before v4
preparation. All 14 immutable v4 pilot plans were reviewed. The fresh v4
`boltz_h0` pilot completed all six predictions and passed its independent audit
(receipt SHA-256
`f95d8af921e4da5ad5dd96178360ce1744191e31902d89c6fc474119b787a6f6`).
The v4 controller stopped safely after the first IntelliFold inference because
that engine omits Boltz's `complex_plddt` field. At the user's direction, v5
declares `complex_plddt` and ipSAE(min) optional and engine-conditional while
retaining iPTM as required. Eleven tests pass. The complete revised audit was
replayed with writes intercepted against the preserved IntelliFold pilot and
passed all structure, chain, cardinality, completion, geometry and resident-MPS
checks; all six `complex_plddt` observations were null, ipSAE was present and
final iPTM was 0.507.

The v5 staged-runtime receipt SHA-256 is
`3dc25ec4752d73b42e78d9cbfbf348d8efc53c7fb9edb51b7d15f62ba9ad0850`
and manifest SHA-256 is
`afee13c04e66af09045d35eb9ac54822b21642e130b3ca51841d4ccf8ac57208`.
All 14 pilot plans were reviewed. The full gated controller started at
2026-09-07T20:09:27Z; it will create and start the 126 remaining trajectories
only after all 14 pilot audits pass. No paired scientific contrast is reported
while the campaign is incomplete.

V5 stopped after 12 passing pilots because OpenFold had been planned with an
unsupported resident scheduler. V6 corrected the scheduler to per-run execution
and then stopped fail-closed when OpenFold's upstream reader silently filtered
the valid target A3M by basename; it also revealed that cohort expansion was
gated per arm rather than by the complete pilot matrix. V7 uses a lossless,
private per-chain `colabfold_main` MSA copy for OpenFold and a global 14-arm
pilot gate. Both OpenFold pilots passed first, then all 14 pilots passed before
any of the 126 remaining trajectories started.

The complete v7 audit finished at 2026-09-08T11:05:45Z. All 140/140 declared
trajectories completed, yielding 700 optimized and 140 cycle-00 structures;
28/28 phase-arm audits passed and froze 23,449 raw-file hashes. There were 57
cycle-05 hits at iPTM >= 0.7. Thirteen trajectories had at least one recorded
geometry warning, one retained two warnings at cycle 05, and none had unusable
coordinates.

Strength 1 reduced mean optimized helicity in every predictor variant. Paired
mean differences (percentage points, strength 1 minus 0) were Boltz -21.8,
IntelliFold Flash -32.6, IntelliFold Full -14.4, OpenFold3 -17.1, Protenix v2
-1.8, Protenix Mini -41.4, and Protenix Constraint -29.0. The unadjusted 95%
trajectory-bootstrap interval excluded zero for Boltz, Flash, OpenFold3, Mini,
and Constraint, but crossed zero for IntelliFold Full and Protenix v2. All
seven mean-iPTM intervals crossed zero. These are n=10 computational
comparisons, not experimental binding evidence.

## Decision and rationale

Require a canonical one-record protein FASTA and a query-matched A3M/Stockholm
with at least two records. Do not silently generate, substitute or reuse an
alignment. Use SolubleMPNN and no assumed epitope or target structure. Treat
iPTM/ipSAE as predicted endpoints only and use binder-chain P-SEA over cycles
01-05 as the primary structural endpoint.

## Reproduce

See the v7 experiment README, immutable manifest, 28 audit records, and
`analysis/REPORT.md`. Manifest SHA-256:
`4ba8855fed8f38afe46fb73387b9e9fc73d6a716f814b4d6d21fa4d59e87c391`.
Stage-receipt SHA-256:
`8853fa01eca498828b1514fff476f9ef0b93d163ac07bd58b225c37e864c2088`.

## Limits and what was not tested

The supplied campaign target is aCbx rather than a non-toxin; target agnosticism
applies to the reusable controller. There is no multiplicity correction,
target structure, epitope, orthogonal post-predictor, wet-lab assay, or basis
for cross-engine score/speed comparison. The managed results catalog does not
currently index these external Validation output roots, so the required
`results_overview` attempt failed closed and the immutable audit/report was
reviewed directly. Final checks passed: 13 campaign tests, 17 MCP bridge tests,
the workflow-pipeline contracts, and `swift build`.

## Next

Use a new immutable campaign version for any later non-toxin FASTA/MSA pair,
then compare whether the five supported helix reductions replicate without
treating predictor confidence as measured affinity.
