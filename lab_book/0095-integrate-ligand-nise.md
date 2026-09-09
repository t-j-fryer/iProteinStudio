---
entry: 0095
title: Integrate ligand NISE and rebrand Protein Hunter
date: 2026-09-05
author: gpt-6
type: port
status: complete
machine: Apple M4 Max, 64 GB unified memory, macOS 26.6.1
tags: [nise, fluorescein, ui, resident-worker, affinity, recovery, mcp]
---

## Context

The user requested an audit of beta's fluorescein small-molecule work, a dedicated
Studio tab alongside the existing workflows, and rebranding iterative design as
Protein Hunter. They explicitly confirmed implementation during the audit. This
authorizes the ligand-NISE addition despite the earlier scope exclusion; protein
and cross-reactive NISE remain upstream.

The Studio checkout already contained substantial uncommitted reliability and
secondary-structure work. It was preserved. No legacy Studio checkout was read
or edited. The source audit traced ligand search to NanoHunter and the optional
apo/preorganisation analysis to iProteinHunter-beta.

## What was done

* Added [docs/NISE.md](../docs/NISE.md), covering original evidence, historical
  provenance limits, current science, repository ownership, lifecycle, output
  identity and the remaining throughput experiment.
* Ported the inspected ligand search plus beta's geometry/weighted preorganisation
  calculation into `Resources/pipeline/scripts/nise/`, with original source
  revisions/hashes and the NanoHunter MIT notice. Removed unused beta CLI/protein
  helpers from the exposed ligand module. No runtime sibling imports or weights
  were copied into Studio.
* Added a distinct NISE request, tab/controller, backward-compatible workspace
  field, Activity/Resume/reattachment, native/MCP planning and grouped candidate
  holo/apo results. Display labels now say Protein Hunter while saved `iterative`
  identities remain unchanged. MCP v9 adds `nise_plan` and its versioned schema.
* Wrapped the upstream search with per-sampling and per-prediction checksum
  receipts. Replay includes Phase 0 and reconstructs trajectory patience without
  resampling completed sequences or trusting partial CSV rows. Code snapshots,
  model/input/source fingerprints and the existing shared broker execution lock
  are retained.
* Made missing affinity fail instead of silently weakening the score. Added
  requested-sequence, finite-coordinate, ligand-cardinality and atom-correspondence
  guards. Optional final apo analysis reports an incomplete job on missing
  requested measurements while preserving the completed search outputs.
* Corrected resident Boltz checkpoint identity: structure and affinity now have
  separate cached model objects, with explicit opt-in for affinity and rejection
  of other checkpoints. The within-cycle default and experimental cross-cycle
  option use the shared file-queue protocol. Apo has a separate structure-only
  session. Protein predictor policy remains unchanged.
* Added request/journal/model-identity/MCP contracts, full-search interruption
  fixtures, apo/reward tests, saved-workspace migration coverage and candidate
  grouping checks. An existing MCP test raced terminal status against worker
  exit; its wait now observes both, matching the production resume contract.

## Results

No throughput measurements — implementation and bounded correctness acceptance.

| Check | n | Result |
|---|---:|---|
| NISE lightweight contracts | 7 tests | pass |
| NISE scientific fixtures, no inference | 5 tests | pass |
| MCP bridge regressions | 17 tests | pass with loopback access |
| Native durable job regressions | 9 tests | pass |
| RFdiffusion predictor scheduling regressions | 3 tests | pass |
| Prediction engine safety | 4 tests | pass |
| Reviewed vendoring | 1 test | pass |
| Swift contracts | NISE migration, StudioCore, result discovery/grouping, iterative commands | pass |
| Workspace, immutable snapshot, iterative CLI and RFdiffusion results contracts | 4 scripts | pass |
| `swift build` | 1 final build | pass |

The real acceptance job `job-7a0b79a61ae6` completed with exit code 0. Two holo
predictions shared one structure/affinity worker across actual LASErMPNN sampling;
one apo prediction used a separate session, and replay started no workers. Exact
raw manifest, plan, snapshot, model fingerprints, receipts and audit are retained
under `Validation/output/nise_integration_v1/smoke-01/`. See
[Validation 0013](../Validation/lab_book/0013-nise-integration-acceptance.md).

The first isolated Swift build failed on the sandbox's default module-cache
location and then unavailable network dependency cloning. It passed using a
writable module cache and the existing canonical `.build` Sparkle checkout.
The initial sandboxed MCP suite could not bind its loopback fixture; rerunning
with that access exposed the existing worker-exit race, then passed after the
test wait was corrected. These were not scientific inference failures.

## Decision and rationale

Use a dedicated ligand workflow and a versioned upstream port rather than extend
the protein iterative objective or import beta's development tree at runtime.
Keep optional preorganisation as a final shortlist ranking: the original beta
evidence does not establish that changing the search objective improves a full
campaign. Keep cross-cycle ligand residency experimental: the earlier protein
benchmarks and this lifecycle smoke do not establish ligand throughput.

LASErMPNN's upstream sampling API has no seed control. Preserve exact sampled
sequences for replay and say so; do not claim seed-only reconstruction. Future
upstream refreshes must review `UPSTREAM.json` and the deliberate adapter changes.

## Reproduce

```bash
python3 Tests/test_nise_contract.py
"$NANOHUNTER_ROOT/venvs/NanoHunter_boltz/bin/python" Tests/test_nise_science.py
python3 Tests/test_mcp_bridge.py
python3 Tests/test_desktop_jobs.py
python3 Tests/test_rfd3_predictor_scheduling.py
python3 Tests/test_prediction_engine_safety.py
python3 Tests/test_vendor_pipeline.py
CLANG_MODULE_CACHE_PATH=/private/tmp/iproteinstudio-nise-modules python3 Tests/run_swift_contracts.py
CLANG_MODULE_CACHE_PATH=/private/tmp/iproteinstudio-nise-modules bash Tests/test_workspace_organization.sh
CLANG_MODULE_CACHE_PATH=/private/tmp/iproteinstudio-nise-modules bash Tests/test_pipeline_snapshot.sh
CLANG_MODULE_CACHE_PATH=/private/tmp/iproteinstudio-nise-modules bash Tests/test_iterative_cli_contract.sh
CLANG_MODULE_CACHE_PATH=/private/tmp/iproteinstudio-nise-modules bash Tests/test_rfd3_results_ui_contract.sh
CLANG_MODULE_CACHE_PATH=/private/tmp/iproteinstudio-nise-modules \
SWIFTPM_MODULECACHE_OVERRIDE=/private/tmp/iproteinstudio-nise-modules \
swift build --disable-sandbox --skip-update
```

The real smoke uses its declared Validation driver and the immutable broker plan,
not a direct untracked model command. Source/weight paths resolve from the managed
runtime. No repository commit or installation update was performed.

## Limits and what was not tested

No full real ligand search to convergence, prospective search-objective
comparison, paired scheduler throughput campaign, memory soak, live GPU
worker-death injection, other Apple hardware, packaged DMG or interactive native
GUI/VoiceOver acceptance was performed. The installed app was not replaced.
The added package-resource assertions were not exercised on a newly packaged app.

The original completed fluorescein evidence is not a checkpoint-identical
baseline for today's evolved upstream driver. Beta's small shortlist analysis
does not establish general binding, linker exposure, or performance. Protein
NISE, cross-reactivity, persistent LASErMPNN, and additional ligand predictor
families are not implemented by this change.

## Next

Complete the declared ligand throughput/fault/soak campaign before changing the
default scheduler. Exercise the native form, Stop/Resume, result windows and
workspace switching in a freshly packaged app on the supported Mac hardware.
