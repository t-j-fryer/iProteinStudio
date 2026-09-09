---
entry: 0099
title: Retain a rejected monomer initialization and continue independent controls
date: 2026-09-06
author: gpt-6
type: audit
status: complete
machine: Apple M4 Max, 64 GiB unified memory, macOS 26.6.1
tags: [secondary-structure, boltz, recovery, validation]
---

## Context

The user requested analysis of the full run from [[0096-monomer-secondary-structure-benchmark]].
The original controller had stopped at 02:06:18 UTC: the remaining
sample-then-mask cohort contained a Boltz cycle-00 geometry rejection at global
trajectory 2. Thirteen full cohorts had passed their original audits; eight
later conditions had only their pilots. No complete 22-condition report existed.

## What was done

Read the recorded job error and pipeline_log_tail, then inspected the earlier
diagnostic in `job-d376ffe43b7b/pipeline.log`. Independently ran the frozen
geometry validator on the rejected coordinates: chain A residues 87–88 have
C–N distance 2.29 Å, exceeding the unchanged 2.2 Å gate. No normal cycle ran
for this trajectory. It remains `geometry_rejected`, with no retry/replacement.

Added a separate recovery/audit/analysis package under
`Validation/experiments/monomer_secondary_structure_recovery_v1/`. Its supplemental
audit ports the original checks for the other eight completed trajectories:
exact sequences and replayed seed/mask plans, six predictions each, finite
coordinates and CA confidence, P-SEA, geometry, MPNN seed/scope, MPS evidence,
confidence/cardinality artifacts and immutable hashes. Combined with the pilot,
sample-then-mask has nine completed trajectories out of ten declared outcomes.
The original failed job and raw files remain intact.

The current managed runtime differed from the campaign's seven staged files,
including missing refinement helpers. Verified all original source identities,
all engine/checkpoint hashes, system_detect and an idle shared execution lock;
backed up the current files and restored the exact original seven identities.
Original manifest/stage receipts remain unchanged. Restoration is recorded in
`recovery_v1/runtime_restore.json` with backups in `runtime_before/`.

A separately recorded controller continues only the eight untouched remaining
conditions through their original public Studio plans, idempotent start and
audit gates. It does not resume or reinterpret the rejected trajectory. The
final analysis accounts separately for geometry rejection and initialization
exhaustion and reports conditional structural means with completed n.

Continuation launched detached at 03:29:53 UTC (PID 11309), with 72 remaining
trajectories across eight conditions. Receipt and progress are in
`recovery_v1/controller_launch.json`, `continuation.json`, and `controller.log`.
The first new cohort is `baseline_loopkill_1`, job `job-1dbffefc8810`.

## Results

At 03:27:14 UTC: 148/220 declared outcomes audited, comprising 145 complete
five-cycle trajectories (725 optimized structures), two initialization
exhaustions in variant pilots and one geometry rejection. Thirteen conditions
have n=10 complete; sample-then-mask has n=9/10. All available original audit
hashes reverified; supplemental audit and actual report generation executed.
P-SEA and confidence aggregates reconciled from per-residue records.
All three sustained-versus-initialization-only pairs have identical original
sequences and cycle-00 P-SEA assignments for all ten matched trajectories.

Compared with initialization-only counterparts, sustained antihelix changes
sheet by +6.3 percentage points (paired bootstrap 95% interval +0.8 to +11.1),
sustained β by +3.9 (+1.2 to +7.2), and sustained mixed by +3.8 (+0.8 to +6.8).
Sustained mixed lowers mean pLDDT by 5.8 points (−10.0 to −1.8).
Removing the β arm's 50% X mask changes sheet by +14.7 pp (+3.7 to +25.3),
but coil also rises 12.3 pp (+2.4 to +20.7). Sample-then-mask has 17.8% mean
sheet in its nine completed trajectories; its paired sheet change versus β is
+10.8 pp (−0.3 to +22.0), conditional on completion. No tested contrast has
established a sheet-enrichment advantage over baseline with these exploratory
intervals. Full tables are in the report below; no setting is promoted.

## Decision and rationale

Keep the observed geometry failure rather than retry until success or relax
the geometry gate. Continue independent predeclared conditions without changing
scientific settings. This extends failure accounting after diagnosis; the
original controller correctly stopped and was not silently modified. The final
benchmark has ten declared outcomes per arm, not necessarily ten valid folds.

## Reproduce

With `NANOHUNTER_ROOT` set to the managed runtime:

```bash
python3 Validation/experiments/monomer_secondary_structure_recovery_v1/recover.py restore
"$NANOHUNTER_ROOT/venvs/NanoHunter_protenix/bin/python" Validation/experiments/monomer_secondary_structure_recovery_v1/recover.py audit
python3 Validation/experiments/monomer_secondary_structure_recovery_v1/recover.py run
"$NANOHUNTER_ROOT/venvs/NanoHunter_protenix/bin/python" Validation/experiments/monomer_secondary_structure_recovery_v1/analyze.py
```

Restoration is deliberately one-time and refuses an existing receipt. The long
controller runs detached under `caffeinate -dimsu`. It writes a complete report
only after all 220 outcomes exist. Current partial report:
`Validation/output/monomer_secondary_structure_v1/recovery_v1/reports/20260906T032714Z/REPORT.md`.
Reports include audit hashes, source copies and original manifest identity.
Base commit `37cc95497283025191e7d2067cb35d1af9168d72`, original dirty manifest
`e437e995d3b66874f07ebad29f4d96b228766d6d96b1178b10aabaa21e8cedc2`.
Engine/checkpoint/lock identities remain in the original stage receipt; empty
MSA, cached-MSA checksum n/a. No weight copies or commit.

## Limits and what was not tested

Eight remaining full cohorts are pending. Recovery itself must complete before
the screen is called complete. Structural comparisons are conditional on
completion, with no multiplicity correction; one seed cohort/length/predictor.
Coil is not experimental disorder, and confidence is not experimental folding.
No new throughput or validated-default claim. New recovery code was executed
on actual artifacts; no new Swift changes or build in this analysis turn.

## Next

The continuation completed all remaining conditions; its full report was
generated at 05:50:37 UTC. Final outcome accounting, independent coordinate
inspection and conclusions are in [[0100-inspect-complete-monomer-benchmark]]
and Validation entry 0017. No declared campaign work remains.
