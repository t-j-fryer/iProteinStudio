---
entry: 0127
title: Checkpoint resident IntelliFold predictions within interrupted batches
date: 2026-09-09
author: GPT-6
type: bugfix
status: complete
machine: Apple M4 Max, 40-core GPU, 64 GB unified memory, macOS 26.x
tags: [predictors, resume, intellifold, reliability]
---

## Context

[Entry 0126](0126-inspect-live-intellifold-cycle01-progress.md) found the live
IntelliFold Full worker was progressing, but its resumed cycle-wave batch had
repeated 34 completed predictions. The shell only recognized trajectory outputs
after the entire batch returned; the resident worker also forced override.
The user requested a resume fix. The active campaign's immutable snapshot must
remain unchanged.

## What was done

- Added `pipeline/scripts/prediction_resume.py`: atomic, fsynced per-prediction
  receipts; exact seed/sample coverage; usable geometry; canonical confidence
  content hashes that survive lossless gzip; archive uncommitted partial files.
- Integrated the receipts into resident IntelliFold Full/Flash. Hash model, CCD,
  Python runtime/upstream code, package versions, relevant execution environment,
  resolved settings, input YAML and local MSA/template dependencies. Verify the
  prepared manifest/features before reuse. Completed records are filtered from
  the inference loader; no forced override. One model remains resident per worker.
- Commit after annotation, confidence compaction and output validation. Check
  input dependencies before committing. Changed completed outputs or settings
  fail explicitly, preserving the original receipt.
- Record deterministic feature RNG boundaries: reset the first requested seed
  inside each dataset access (including Accelerate lookahead), rather than before
  `next(loader)`; retain each requested diffusion seed. Enforce the
  existing zero-data-loader-workers default. This deliberately changes the old
  feature RNG boundary and is documented; no claim of bitwise equivalence to an
  older build's predictions.
- Remove only disposable YAML symlinks before rebuilding each wave request, so
  already-materialized trajectories do not remain in resumed input membership.
- Emit per-item progress/reuse counts to the worker queue and live shell log.
  Exclude archived partial coordinates from prediction-geometry discovery.
- Add interruption/process-restart fixtures to the fast test entry point and
  explicit packaged resource comparisons. Document scope in `docs/CLI.md`.
- Increment local app/DMG build to 35; exercise the local packaging workflow.

## Results

No GPU performance measurements — implementation and software fixtures only.

- Managed IntelliFold Python: all 14 resume tests pass (real PyYAML/ipSAE and
  storage/geometry helpers; tensor/model/accelerator operations are fixtures).
- A real child process exits during job 2 of 3, after its first seed; outputs
  include a deliberately truncated structure. Restart preserves job 1 bytes and
  mtimes, archives the partial item, retries job 2 and completes job 3. All
  seed/sample content hashes match an uninterrupted fixture. Repeating resume
  performs no further inference calls; reducing membership also reuses correctly.
- Fixtures cover corruption, missing output, conflicting gzip, NaN JSON,
  changed input/dependencies/settings, partial multi-seed/sample sets, processed
  cache changes, untracked legacy refusal, stale links, and live shell progress.
- Existing suites pass: prediction-engine safety (4), iterative engine batch (9),
  NISE contracts (9), RFdiffusion3 predictor scheduling (3).
- An actual Accelerate 1.1.1 DataLoaderShard / PyTorch 2.6.0 CPU test confirms
  that prefetched feature RNG is independent of skipped preceding records.
  Fully reused requests bypass the empty loader (which otherwise yields `None`).
  Receipts normalize upstream tuple-valued buckets to their persisted JSON form.
- Storage-policy regression passes. `swift build --disable-sandbox --skip-update`
  passes with local module caches.
- Local build-35 packaging rehearsal passes release assembly, packaged resource
  checks, ad-hoc signature verification and DMG/ZIP/appcast generation. Final
  distribution artifacts are rebuilt from committed source using the command
  below; generated binaries and weights are not committed or published here.

## Decision and rationale

Use verified per-item receipts rather than upstream's existence-only skip. An
interrupted write can leave files present but unusable, and existence cannot
prove which settings produced them. Preserve uncommitted evidence before replay.
Do not guess provenance for legacy partial batches or modify an active snapshot.
Keep the concrete engine fix scoped to the observed resident IntelliFold path;
other engines need their own output/finalization contracts before equivalent
checkpointing is claimed.

## Reproduce

From the canonical Studio checkout:

```bash
python3 Tests/test_resident_prediction_resume.py
/Users/thomasfryer/.iproteinstudio/venvs/NanoHunter_intellifold/bin/python Tests/test_resident_prediction_resume.py
python3 Tests/test_prediction_engine_safety.py
python3 Tests/test_iterative_engine_batch.py
python3 Tests/test_nise_contract.py
python3 Tests/test_rfd3_predictor_scheduling.py
CLANG_MODULE_CACHE_PATH=/private/tmp/iproteinstudio-modules SWIFTPM_MODULECACHE_OVERRIDE=/private/tmp/iproteinstudio-modules swift build --disable-sandbox --skip-update
# After committing the source, regenerate artifacts with clean provenance:
CLANG_MODULE_CACHE_PATH=/private/tmp/iproteinstudio-modules SWIFTPM_MODULECACHE_OVERRIDE=/private/tmp/iproteinstudio-modules bash release/release_app.sh --unsigned-beta
```

The generic Python fixture uses a JSON-only YAML substitute if PyYAML is absent
and skips the explicit YAML-text and actual Accelerate tests; the managed Python
runs those tests too.

## Limits and what was not tested

No actual MPS inference, uninterrupted-versus-resumed GPU numerical comparison,
new campaign, live-worker pause, or current-run mutation. Fixtures prove control
flow and persistence, not real-model quality or speed. Full XCTest requires
Xcode; this machine has Command Line Tools. Current and older campaigns keep
their recorded runtime, so they do not acquire this fix just by updating the app.
New per-prediction receipts currently cover resident IntelliFold only. Existing
Boltz, Protenix and non-resident IntelliFold partial-batch behavior is not changed.
No automatic migration/adoption of legacy outputs, cross-machine resume guarantee,
or new throughput recommendation. Model hashing startup cost is not benchmarked.

## Next

Validate a planned small real-model pause/resume run once the active campaign
finishes. Extend per-item receipts to other engines using their output contracts.
