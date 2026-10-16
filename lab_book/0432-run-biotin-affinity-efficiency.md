---
entry: 0432
title: Run paired biotin affinity and CPU efficiency tests
date: 2026-10-15
author: Codex
type: experiment
status: in-progress
machine: Apple M4 Max, 40-core GPU, 64 GB unified memory
tags: [boltz, biotin, affinity, cpu, residency]
---

## Context

User authorized 50-affinity-step/one-sample testing on previously scored biotin
designs plus the other efficiency qualifications. Their watcher stops the current
GPU owner; this experiment must wait on Studio's shared execution lease.
Follow-up to 0430/0431. The user queried seed variation: use two distinct seeded
repeats with each seed matched across settings, and a separate SAME-seed repeat.

## What was done

Added Validation/experiments/biotin_affinity_efficiency_v1. Freeze 48 complete
sequence designs (24 per generator) from the saved Boltz/RFD3 NISE runs. Twelve
per generator from Phase 0 and twelve from optimization, four per P(bind) tertile
in each stage. Source populations contain6048/5107 affinity-scored candidates.
Verify saved atomic structure/affinity receipts and copied chemical features.
Retain originals unchanged. No new backbone generation or MSA calls.

Reference200steps/5samples versus50/1, two seed repeats with reversed order;
same-seed replay on eight cases, both arms. Five affinity recycles and two output
heads unchanged. Resident weights with explicit assertion/update of experimental
predict args, no outer structure inference. Four-case real smoke gates main work.
192main+8smoke+16same-seed+32overlap =248 affinity evaluations.

Geometry qualification uses48 inputs,1/2/4/8 processes, two reversed repeats,
exact geometry equivalence. CPU/GPU overlap compares identical independent work:
two resident LASErMPNN CPUs, two geometry CPUs and eight light affinity cases,
serial vs concurrent, two reversed repeats. CPU pool startup included.

## Results

Four executed contract tests passed: stratified unique selection, insufficient
diversity rejection, checksum-based resume rejection and preservation of staged
full-precision structures/affinity records. Actual frozen-input audit passed for
all48 structures, sequences, finite coordinates and explicit empty MSA.
Real affinity/geometry/overlap measurements pending managed execution.
No speed claim based on fewer steps. Output:
Validation/output/biotin_affinity_efficiency_v1/20261015T234303Z.

## Decision and rationale

Same-seed replay measures numerical reproducibility; different-seed repeats
measure sensitivity to sampling. Neither is interchangeable with a paired setting
comparison. Keep other settings/structures/features fixed. Report P(bind), composite
ranking, top10 retention, thresholds, raw outputs, process RAM and MPS allocation.
No production default changed. This reduces a scientific budget; label as a
speed/score trade-off, not output-equivalent runtime optimization.

## Reproduce

From Validation/experiments/biotin_affinity_efficiency_v1:
`python3 test_contract.py`; `python3 prepare.py`; review frozen config, then
`python3 prepare.py --submit <output>` via Studio immutable plan and job_start.
Managed runtime/source/weight hashes recorded in plan. Runtime host recorded by
the managed job; sandbox could not read CPU sysctl during preparation.

## Limits and what was not tested

No experimentally validated binding outcomes. Stratified cohort does not estimate
campaign hit prevalence. Overlap uses independent prepared inputs, not live-cycle
dependencies; excludes initial protonation. GPU allocation counters are not GPU
utilization. No long memory soak or production cancellation/resume qualification.

## Next

Review real smoke and final raw/audit/analysis files; compare light-score changes
with same-seed and different-seed variability before any default promotion.

Managed plan8b436ddca9bc3670, SHA2568b436ddca9bc3670c2f2b98600431ee38314f1bc8bbd6db048552829d1838a3d; job-8b436ddca9bc submitted2026-10-15T23:43:53Z. Source cohort input audit passed. Predecessor job-cae46f604ea5 was immediately cancelled before inference to correct geometry settings extraction: these fields live in nise_config.json.request, not the upstream config.json. Its immutable directory remains preserved at20261015T234105Z.

## First progress snapshot (2026-10-15, approximately23:50UTC)

Real four-case smoke completed under both settings; all receipts/hash checks pass,
paired CPU feature hashes identical, actual affinity args200/5 versus50/1 verified,
five recycles and resident model load count2 unchanged (structure+affinity weights).
P(bind) reference/light: boltz_00 .220876/.217141; boltz_23 .954466/.953507;
rfd3_00 .192648/.189010; rfd3_23 .775365/.773445. Mean absolute change .002563,
maximum .003735. This is only four cases, not a qualified full-cohort result.
Smoke request seconds/design: Boltz-origin19.343 vs4.686; RFD3-origin18.737
vs6.186. First reference includes affinity startup, so do not report as a steady
state speedup. First main reference batch8/192 completed in234.673s (29.334s/design);
next batch active, no model failures. Same-seed, geometry and overlap checks pending.

Progress snapshot23:57UTC: all24 Boltz-origin first-repeat reference cases audited complete; aggregate526.141s,21.923s/design. First RFD3-origin reference batch active. No new matched light pairs beyond four-case smoke yet, no tracebacks. Main reference and reduced arms run serially; final score/efficiency conclusions remain pending.

Progress20:05EDT2026-10-15: all48 first-reference cases complete (1038.275s;21.631s/design), first8 full paired cases audited. {"n": 8, "reference_seconds_per_design": 29.33412617185968, "light_seconds_per_design": 8.309377354133176, "speed_ratio": 3.5302435936753507, "mean_absolute_pbind_delta": 0.01047128438949585, "max_absolute_pbind_delta": 0.028134554624557495, "same_order": true}. Paired feature hashes identical; these first8 are Phase0 low/middle P(bind) strata, not the full cohort.

Priority clarification: existing normal-cycling lessons (0420/0422) apply, but do not imply NISE LASErMPNN already uses the resident ProteinMPNN adapter. Qualification0430 shows prepared-input LASEr residency improvement. Geometry is a repeated pre-affinity selection gate in ordinary NISE, but the planned equal-budget rescue comparison0429 retains geometrically failing intermediates and scores all at common assessment. Thus critical-path optimization should focus on resident sequence design, bounded independent-lineage preparation/prefetch and reporting gaps; geometry-pool/overlap microbenchmarks are bounded supporting checks, not evidence of full-cycle throughput improvement. No scientific selection or running plan changed.

User curtailed second seeded repeat2026-10-15T20:09EDT. job-8b436ddca9bc cancelled through broker; all48 first-seed pairs complete and audited. Paired mean21.631s vs5.654s/design (3.82565x); P(bind) MAE.0105849,max.033429,Spearman.997612. Combined top10 unchanged; pooled P(bind)-only top10 retains9/10. One early0.80 gate crossing (.808854 to.787324). Four same-seed smoke/main controls match exactly under both settings. See analysis/FIRST_SEED_REPORT.md and first_seed_summary.json. Shortened CPU follow-up atValidation/output/biotin_affinity_efficiency_v1/cpu_followup_20261016T000959Z: no second affinity-seed cohort, one same-seed serial/overlap pair plus warmup (18light calls). Geometry sweep separate from cycling.

Shortened follow-up submitted via plan-d6f708cd5f7eb890 / job-d6f708cd5f7e, digestd6f708cd5f7eb8909618b88faafe5af63a4a930f0d3c28414c257c3c99d766a3. No prior raw data modified.

## CPU follow-up completed (2026-10-15 EDT)

See0433 for corrected config-relative helper-path launch failure and resumed
nanobody handoff. Corrected managed job-f4db470073e8 completed at
`Validation/output/biotin_affinity_efficiency_v1/cpu_followup_20261016T001422Z`.
Geometry48cases×2orders: exact at1/2/4/8workers;1worker2.716–2.727s versus
8workers0.940–0.951s. One same-seed serial/overlap pair53.7434/48.1476s,
identical eight affinity outputs/features and identical LASEr FASTA/scores and
geometry. CPU tasks slowed during overlap, but total time improved. Prepared
inputs only; no full cycling throughput or global default promotion claimed.
The user-authorized follow-on biotin comparison uses50/1 affinity and qualified
resident CPU sampling after the original nanobody campaign finishes.
