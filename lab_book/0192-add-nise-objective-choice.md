---
entry: 0192
title: Make sequence-scorer objectives explicit in NISE
date: 2026-09-25
author: Codex
type: implementation
status: complete
machine: Local Apple-silicon development Mac; no inference benchmark
tags: [nise, nesso, psichic, scoring, ui, mcp]
---

## Context and decision

The user requested NESSO/PSICHIC as an optional actual optimisation objective,
with Boltz only generating structures and enforcing geometry, rather than always
using these models as prefilters for the Boltz composite objective.

Keep `scoring_mode=boltz` for existing/default requests. Add explicit experimental
`scoring_mode=screening`, using the selected model for every scored refinement,
seed/beam selection, best-so-far and patience. NESSO retains its validated software
formula `P(bind) + 1 - entropy_crop_pl` and rejection of missing/invalid/near-zero
entropy. PSICHIC retains `1 - predicted_nonbinder`, not its separate affinity
prediction or an invented placement confidence. Model accuracy remains unvalidated.

Do not translate Boltz's 0.80 early gate. Separate `nesso_early_score_gate` (0–2)
and `psichic_early_score_gate` (0–1) default to zero/off, remain adjustable, and
persist independently in the UI. Geometry eligibility, score validity and
shortlist counts still restrict work. This is an explicit conservative default
for a new experimental option, not a promoted calibrated threshold.

Evidence reviewed: existing Lab Books 0175/0176 and their saved reports. The
historical fluorescein distribution had PSICHIC proxy median 0.013 (5th/95th
percentiles 0.000/0.996), NESSO five-recycle P(bind) median 0.651, and Boltz
P(bind) median 0.645. These are copied from the audited 0175 report (5,440 saved
screened candidates, 5,387 Boltz probabilities; original Apple M4 Max analysis).
NESSO's composite additionally includes entropy. These distributions are not
biotin or biological calibration; neither a shared 0.8 nor a new 0.5 cutoff is
justified. No distributions or models were recomputed for this implementation.

## Implementation

- Shared Python contract, MCP schema/guide, Swift request encode/decode and form
  expose the mode and separate engine cutoffs. Objective mode requires both stage
  screens and geometry-first structure requests. Legacy omitted fields retain
  Boltz behaviour. Prediction budgets identify objective and affinity enablement.
- The existing shortlists stay as controllable folding budgets. Geometry-passing
  shortlisted candidates advance by the sequence score. Cycle00 and the
  unrestrained gate remain geometry-only. No hidden backfill, altered geometry
  threshold or Boltz-score fallback was added.
- Objective mode bypasses selective affinity ranking/pruning. Resident singleton,
  stage-batch and pool workers forbid affinity checkpoint loading; affinity entry
  points reject calls in this mode. Native structure inputs retain the established
  ligand chemical state and reusable pre-affinity cache format. Installed Boltz
  assets are still required by the existing engine installation/preflight.
- Candidate records, CSV columns, advancement/summary metadata and result views
  identify the objective; Boltz p(bind) remains null rather than being relabelled.
- Request/operation identities and objective-aware frozen settings prevent
  objective/gate mutation during resume. Cached sequence scores are replayed.
- UI explicitly enables both screens and disables partial noising for this mode:
  masked sequences have no complete-sequence score. The existing geometry-only
  initial generators remain supported. Improvement stays in selected-score units,
  default 0.01 and editable; no unvalidated automatic rescaling.

## Validation

Deterministic model-boundary tests run the real search/selection/journal over
NESSO and PSICHIC crossed with Protein Hunter, RFD3 and cohort starts. They check
conflicting Boltz-confidence/sequence-score winners, geometry rejection of the
highest-scoring proposal, engine-specific early gates, exact best score, patience
termination, deliberate interruption, zero-work replay and rejection of an
objective change. Native backend guards and stage-worker affinity disablement
are exercised without model inference. The existing Boltz routes are regression
tested; fixture interfaces were extended to carry objective metadata.

Swift request/results harnesses check legacy decoding, separate cutoff retention,
mode dependencies, encode/decode, explicit objective labels and absent Boltz
binding probability. See artifacts for final test/build logs.

## Reproduce

```bash
NANOHUNTER_ROOT="$HOME/.iproteinstudio" "$HOME/.iproteinstudio/venvs/NanoHunter_boltz/bin/python" -m unittest discover -s Tests -p 'test_nise_*.py'
```

Build with the native SwiftPM workaround documented in 0191; local version
0.2.6-cohort2 (51). No commit, GitHub publication or installed app replacement
was requested/performed; shared active campaign resources were not modified.

## Limits and what was not tested

No prospective neural-model optimisation, real GPU worker startup, real affinity
head execution, memory/throughput measurement, receiving-Mac inference, or GUI
interaction smoke. This verifies algorithm/control/metadata behaviour, not
scientific accuracy or compute savings. Existing optional preorganisation remains
a separately labelled downstream analysis, not the optimisation objective.

## Final result

64 Python NISE tests passed. Both targeted Swift request and results harnesses
compiled and passed. The release app build, resource-bundle contract, deep strict
signature verification and packaged-source equality checks passed. The DMG
checksum is valid. Cohort ZIP CRC and all 20,099 scientific file hashes passed;
its 1,491 candidates /712 lineages are unchanged and only instructions were added.

Artifacts: `build/transfers/iProteinStudio-NISE-objective.dmg` and
`build/transfers/Biotin-Phase0-1491-objective-ready.zip`. Existing cohort archives
also remain import-compatible. Hashes and source audit are saved with this entry.
These are local test artifacts, not a published/notarized release.
