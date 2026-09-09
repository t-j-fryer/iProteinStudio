---
entry: 0096
title: Benchmark secondary-structure controls on unconditioned monomers
date: 2026-09-05
author: gpt-6
type: benchmark
status: complete
machine: Apple M4 Max, 64 GiB unified memory, macOS 26.6.1
tags: [secondary-structure, boltz, validation, mcp, reproducibility]
---

## Context

Following [[0095-monomer-initialization-refinement]], the user requested 90-residue
monomer generation with baseline, helix kill, existing β-oriented prior, mixed
and inspection, ten trajectories of five cycles each using Boltz-2. They
clarified that inspection applies to the β control only, and requested coverage
of the other available controls. Work is in the canonical Studio repository;
unrelated dirty changes are preserved.

## What was done

Declared a 22-condition paired single-factor screen under
`Validation/experiments/monomer_secondary_structure_v1/`. It covers the five
core conditions plus prior scope/strength, β pattern and turn weighting,
masking amount/order, loopkill, first/later MPNN temperature and global bias,
and inspection budget/length/confidence. The first trajectory per arm is the
smoke test and counts in ten; nine more require an operational output audit.
All calls use the public MCP immutable plan/start bridge. Inspection applies
only to initialization, and exhaustion prevents cycling without replacing seeds.

Added validated public MCP arguments for existing mask, loopkill and global
amino-acid bias controls. An explicit `monomer_control_benchmark` field validates
the target-free template and records the common run scheduler for this paired
screen. Added a template-only checker to the existing refinement CLI. Ordinary
planning retains its existing scheduler selection. No execution-lock or
provenance check is bypassed. Runtime staging is restricted to seven declared
files with backups while the shared runtime is idle; model weights are only
fingerprinted. Manifest preparation freezes scientific settings and code.

## Results

Prelaunch software checks passed: six campaign contracts, 14 lifecycle tests,
seven sampler tests, six shell integration tests using synthetic prediction and
MPNN adapters with real Biotite, and the MCP monomer benchmark contract.
The complete 18-test MCP bridge suite also passed. Runtime staging verified MPS
with PyTorch 2.13.0, recorded checkpoint fingerprints and preserved backups.
The real baseline pilot `job-e1f1a39cd186` started at 21:12 UTC; the campaign
is in progress, with no final structural or performance comparison yet.
No commit made.

Baseline pilot completed at 21:14:43 UTC and passed the full output audit:
one original initialization plus five optimized structures, exact 90-residue
sequence checks and seed pairing, MPS execution, documented SVD warnings only.
Measured trajectory wall time including initialization was 111.383646 seconds
on the above M4 Max; this excludes the separately recorded preflight calibration
and is not a comparative throughput result. The β-inspection pilot then started
as `job-1a0fad7a2069`. Both smoke trajectories remain in the declared ten.

The β-inspection pilot completed at 21:17:51 UTC and passed the full audit.
Its original candidate required refinement; a second prediction qualified,
was explicitly selected, and supplied the first MPNN redesign. Five normal
cycles completed, with original artifacts preserved and no initialization bias
carried into cycling. All 22 pilot plans passed public preflight. The declared
one-attempt inspection variant is being checked for explicit exhaustion as
`job-8bf07677f09a` before the detached controller continues the full screen.

The one-attempt pilot completed at 21:19:12 UTC with explicit
`budget_exhausted`, nonzero run/job status, and zero optimization cycles. Its
integrity audit passed while its scientific eligibility remained failed. This
is retained attrition, not a successful initialization or replacement seed.
The full controller launched detached under `caffeinate -dimsu` at 21:19:47 UTC
(PID 89270), reusing those three smoke jobs. Launch identity and live progress
are recorded in `controller_launch.json`, `controller.log` and per-arm
`status/` receipts under the output directory. The controller continues all
remaining smoke arms, then nine further trajectories per arm after audit,
and generates the final report after all declared trajectories are accounted for.

## Decision and rationale

Use β-only inspection against the identical original β initialization. Hold
the run scheduler constant across arms because refinement has a separate stage
handoff. Preserve all ten declared seeds including failed eligibility outcomes;
report conditional structure means with n. A one-factor screen is tractable
and interpretable; exhaustive settings/interaction sweeps are outside this
experiment. Prospective thresholds are exploratory, not validated fold criteria.

## Reproduce

See the experiment [README](../Validation/experiments/monomer_secondary_structure_v1/README.md)
for exact commands. Generated raw results, requests, plans, audits and report:
`Validation/output/monomer_secondary_structure_v1/`. Base commit is
`37cc95497283025191e7d2067cb35d1af9168d72`; generated manifest records the dirty
diff identity, configuration and code hashes. Stage receipt records hardware,
engines/checkpoints and package locks. MSA policy is empty; no cached target MSA.

## Limits and what was not tested

Full comparative results remain pending. Only length 90, one predictor and one paired
seed cohort. No binding targets, other lengths, exhaustive strength sweeps,
experimental folding, default promotion or new hardware performance claims.
Wall time includes initialization for completed trajectories; exhaustion is
reported separately. Bootstrap intervals are exploratory, without multiplicity
correction. Cycle 00 is never counted as an optimized design.

## Next

Completed after the recorded geometry-failure continuation. All 220 outcomes
and 1,070 optimized structures are inspected; final results and limits are in
[[0100-inspect-complete-monomer-benchmark]] and Validation entry 0017.
