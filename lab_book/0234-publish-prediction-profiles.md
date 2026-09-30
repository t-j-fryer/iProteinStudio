---
entry: 0234
title: Publish shared prediction profiles and qualified runtime improvements
date: 2026-09-30
author: Codex
type: implementation
status: complete
machine: Apple M4 Max, 40-core GPU, 64 GB unified memory, macOS 26.6.1
tags: [predictors, ui, mcp, release, performance]
---

## Context
Apply the benchmark prediction defaults consistently to new app, MCP and CLI
jobs, retain native compute for Protenix Mini and both ESMFold2 variants, expose
scientific overrides, and remove the Protein Hunter 96-trajectory form limit.
Publish a tested app and update feed. Existing immutable jobs must not change.

## What was done
Target MSA cap 128 including query, reduced diffusion 25 for Boltz2, IntelliFold
Flash/Full, Protenix v2/Constraint and OpenFold3. Native recycles retained.
Mini: 5 diffusion steps / 4 recycles. ESMFold2 Full: 100 requested steps / 20
loops. Fast: no MSA, 50 requested steps / 3 loops. Sample-count, guidance,
affinity and RFdiffusion3 generation settings remain separate controls.

## Evidence and limitations
Source evidence: 0228 (exact tokens), 0229 (resident overhead), 0230 (shared-target
campaign), 0233 (paired workstation filtering). Those experiments are not a
claim of universal accuracy equivalence. The original paper matrix remains immutable. The user subsequently requested a
separate continuation with the final app profiles; see the continuation below.
No new performance numbers are claimed in this implementation entry.

## Results
In progress. Results, failures and release identifiers will be appended before
publication. Fresh-Mac installation and cross-chip performance are not tested
by this change.

## CPU and contract validation
Swift build passed, followed by 13 Swift tests. MCP integration passed 22 tests
when given the local-socket and process-inspection permissions its inert workers
require (sandboxed run reproduced the documented seven failures/one error).
NISE: 66 tests passed in the installed Boltz test environment. RFdiffusion3:
35 tests passed. Prediction templates/engine safety/MSA tests: 14 passed.
New profile tests: 7 passed. ESMFold2 adapter tests: 8 passed. Iterative CLI
contract passed. Resume suite: 14 tests, 13 passed/1 pre-existing optional skip.
Initial generic Python lacked YAML/gemmi/boltz dependencies; rerunning in the
appropriate existing engine environments resolved those environment errors.

Resume tests exposed two integration defects in capped-input staging: stale
members when replaying a subset and failure to inspect original inputs after a
staged copy was prepared. Fixed by staging each input set separately and keeping
original-input identities in the IntelliFold ledger. Unchanged inputs are not
rewritten. No raw benchmark output or installed package was modified.

Release acceptance plan `plan-84e8a86212123809`, SHA256
`84e8a86212123809d210837b27eecb43c6ce4fb0421dd37087361e02f0f10cba`, job
`job-84e8a8621212`. Frozen code, original SUMO alignment, input rows and runtime
bindings are under `Validation/output/prediction_profile_release_v1/attempt01`.
Paper job `job-8b090b4b2f4e` cancelled normally for this GPU acceptance window;
its unchanged immutable plan and atomic completed outputs are preserved.

## Production model acceptance

Attempt01 completed all nine engines, two different binder/SUMO96 complexes each
(18 predictions, seed42, one sample). The production resident adapters loaded
once per engine; OpenFold used its existing per-input production launcher.
Verified requested chain sequences, finite coordinates, confidence files and
geometry-parser success. A second audit verified every saved receipt hash and
all numeric confidence JSON values. Geometry flags remain advisory; this does
not claim all predicted structures are physically perfect or that every new
scientific budget is universally equivalent.

The clean release checkout passed all58 fast regression groups. Follow-up
profile tests (7) and live-result tests (5) passed after fixes for native Boltz
MSA override precedence, staged-input publication, and relative YAML dependencies.
The acceptance freeze precedes those input-path fixes; they were validated by
focused integration contracts without changing model arithmetic.

## Decision and rationale

Keep native Mini5/4 and ESMFull100/20 at the user's request. Reduced diffusion
is a scientific profile, not a numerically exact runtime optimization. Published
controls retain explicit overrides. Sample counts, guidance, affinity budgets
and RFdiffusion3 generation are separate settings and are unchanged.

## Benchmark continuation

User explicitly requested the restarted paper screen use the final app settings.
New plan `plan-a36f3b69a4a992de`, SHA256
`a36f3b69a4a992de464a44fa445698812780bb1c2233f645e4929cae9e2da032`,
output `Validation/output/paper_binder_matrix_v1/campaign_app_profiles_v1`.
All674 old Mini1-step predictions are excluded from the new profile cohort.
ESMFull had not started and now requests100 steps.2124 compatible completed
units are hash-verified and referenced read-only (674 each Boltz/Flash/OpenFold,
102 Constraint). The original cancelled job is not resumed or rewritten.

The continuation resolves budgets from the versioned app JSON but retains the
original instrumented runtime and qualified hooks for timing continuity. It is
a benchmark harness, not a claim that all native app scheduling paths are the
same. Runtime manifests are asserted identical to the original plan; inputs,
seed42, sample1 and target MSAs remain fixed. Repeated geometry analysis can now
compare Mini1 against Mini5 without mixing them in one primary cohort.

## Reproduce

`python3 Tests/run.py --suite fast` (local process/socket permissions required).
Run science fixture tests with the existing Boltz/Protenix environments documented
above. Release smoke preparation: `prediction_profile_release_v1/prepare.py`;
start its immutable plan through Studio's broker. Continuation preparation:
`paper_binder_matrix_v1/continue_app_profiles.py OLD_CAMPAIGN NEW_OUTPUT`.
The frozen config and imported-unit receipt index preserve exact provenance.

## Limits and what was not tested

No fresh-Mac install, cross-chip accuracy/performance test, interactive VoiceOver
review, or new broad ligand/template geometry qualification. Production smoke
uses protein complexes. Full long-running continuation and geometry/filtering
comparisons remain ongoing. No additional speedup is inferred from smoke timing.

## Next

Publish and verify the packaged app/MCP/update feed, then start the app-profile
continuation under the shared execution lease. Biotin remains paused.

Final standalone acceptance also passed Boltz, Mini, v2 and Constraint (one
complex each), exercising the actual native CLI argument path at final defaults.
Plan `plan-73103e896403b4a3`, job `job-73103e896403`; four receipt hashes verified.
Combined production acceptance:22 predictions. The continuation's independent
export audit verified2124/5392 predictions with zero integrity errors. Final
Swift build, packaged resource checks, ad-hoc app signature verification and
Sparkle appcast generation passed.

## Publication and restart verification

Published `v0.2.17-beta` (build63), source commit `ec22920`, update-feed commit
`21d605c`. All four GitHub asset SHA256 digests match local artifacts. The live
Sparkle feed advertises build63; its archive signature was verified with the
project signing identity. Local app build63 is installed and opened, with
build62 retained under `build/app-backups/`. Installed MCP36 doctor passed;
all19 detected component entries report OK; prediction adapters match source.

Continuation `job-a36f3b69a4a9` is running under its immutable plan. First
audited Mini outputs confirm5steps/4recycles; full compute has not been reduced
on restart. Stage timing, geometry advisories and hash checkpoints continue.
The original benchmark job remains cancelled and raw results unchanged; biotin
was not resumed. The longer campaign and its comparative analysis remain in
progress. Distribution remains the existing ad-hoc trusted beta, not Apple
notarization or a fresh-Mac installation claim.
