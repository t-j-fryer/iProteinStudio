---
entry: 0035
title: Make MSA and accelerator policy fail-loud
date: 2026-08-22
author: codex-gpt-5
type: implementation
status: complete
machine: Apple M4 Max, 40-core GPU, 64 GB unified memory, macOS 26.x
tags: [protenix, intellifold, msa, mps, reproducibility, testing]
---

## Context

An audit for the separate iProteinHunter-beta experiment found two policy
hazards in Studio's shared runtime. Accelerate 1.1.1 assigns
`PYTORCH_ENABLE_MPS_FALLBACK=1` while choosing MPS, so selecting an MPS device did
not prove that unsupported operations would fail instead of silently moving to
CPU. Separately, Studio converted Protenix `msa: empty` by omitting the MSA path
but did not pass `--use_msa False`. Protenix defaults that switch to true and its
`need_msa_search` function treats a missing path as an online-search request.

This was not merely theoretical. The existing 2026-08-21 Protenix logs contain
`starting to update msa result` for explicit-empty prediction input. Existing
IntelliFold logs did not contain an observed CPU-fallback warning; the
IntelliFold issue was permission for fallback, not evidence that fallback had
already occurred.

## What was done

- Added one drop-in IntelliFold launcher shared by plain Predict, iterative
  design and RFdiffusion3 verification. It pins the already-installed PyTorch
  2.6.0 / Accelerate 1.1.1 contract, sets fallback to zero before importing
  PyTorch, replaces Accelerate 1.1.1's MPS device property that would set it back
  to one, asserts the selected device is MPS, and emits a machine-readable device
  record.
- The launcher verifies the exact Cartesian product of requested input YAMLs,
  seeds and diffusion samples. IntelliFold's upstream runner can record a failed
  target and still return success; a missing structure or summary-confidence
  file now makes the Studio invocation fail.
- Made IntelliFold GPU-only in the iterative CLI, matching the product policy
  already enforced for Protenix. Ordinary CPU preprocessing remains normal;
  this rule concerns model execution and unsupported MPS operators.
- Made Protenix pass `--use_msa True` or `False` explicitly on every invocation.
  Fully single-sequence jobs run with false. Jobs containing a real MSA run with
  true.
- Preserved mixed-chain intent. For an aligned target plus an explicit-empty
  binder, the target A3M is passed unchanged and a durable query-only A3M is
  materialised for the binder. This makes upstream `need_msa_search` false for
  every chain without disabling the target's real alignment.
- Directory batches containing both fully single-sequence jobs and MSA-backed
  jobs are partitioned into separate Protenix invocations because Protenix's
  `use_msa` setting is process-wide.
- Protenix now verifies the exact number of raw structure/summary pairs implied
  by seeds × samples before normalising the best-ranked result.
- Extended the workflow and iterative CLI contracts to cover explicit-empty,
  mixed-chain, strict-launcher routing, version pins and missing-output failure.

## Results

| Condition | n | Metric | Value |
|---|---:|---|---:|
| Deterministic Python/shell/Swift contracts | 8 suites | passing suites | 8/8 |
| Full debug Swift build | 1 build | result | pass in 4.73 s |
| Incremental release app-bundle build and signature check | 1 build | result | pass |
| Managed component detection | 8 components | detected ready | 8/8 |
| IntelliFold v2-flash, 75-residue explicit-empty X input | 1 seed × 1 sample | complete structure/summary pairs | 1/1 |
| IntelliFold acceptance | 1 fold | upstream prediction loop | 32.73 s |
| IntelliFold acceptance | 1 fold | selected device / fallback | MPS / disabled |
| Protenix Mini, same input | 1 seed × 1 sample | complete structure/summary pairs | 1/1 |
| Protenix Mini acceptance | 1 fold | upstream model forward / job | 1.92 s / 4.93 s |
| Protenix Mini acceptance | 1 fold | MSA-server searches | 0 |

The Protenix log explicitly reported `use_msa=False` and Apple MPS. The
IntelliFold log emitted `IPROTEINSTUDIO_DEVICE|intellifold|mps|fallback=0` before
model inference. Both acceptance invocations completed under `caffeinate`, and
their exact-output checks returned success.

## Decision and rationale

`msa: empty` means a deliberate scientific input, not a cache miss. Online MSA
generation remains available through Studio's explicit `auto` policy, which
first resolves the shared cache and records any generated A3M on disk. A model
adapter must not independently reinterpret absence as permission to use the
network.

Globally forcing Protenix `--use_msa False` would have corrupted the common
aligned-target/single-sequence-binder case. Query-only A3M is the per-chain
representation needed when Protenix's process-wide switch must stay enabled for
another chain. Separating fully empty jobs avoids changing their no-MSA model
path merely because an unrelated MSA-backed job shares a scheduler batch.

Selecting `mps` is also insufficient evidence of GPU-only execution when the
framework explicitly enables fallback. The retained Accelerate version is
pinned, so the smallest auditable intervention is a version-gated launcher
around the validated upstream runner. A future Accelerate or PyTorch upgrade
must fail until its device semantics are re-audited rather than silently
bypassing this contract.

## Reproduce

```bash
cd /Users/thomasfryer/iProteinStudio

NANOHUNTER_ROOT=/Users/thomasfryer/.iproteinstudio \
  bash Sources/iProteinStudio/Resources/pipeline/setup_pipeline.sh --detect

/usr/bin/caffeinate -dimsu bash Tests/test_iterative_cli_contract.sh
/usr/bin/caffeinate -dimsu \
  /Users/thomasfryer/.iproteinstudio/rfd3/.venv/bin/python \
  Tests/test_workflow_pipelines.py
/usr/bin/caffeinate -dimsu \
  /Users/thomasfryer/.iproteinstudio/rfd3/.venv/bin/python \
  Tests/test_ligand_conditioning.py
/usr/bin/caffeinate -dimsu \
  /Users/thomasfryer/.iproteinstudio/rfd3/.venv/bin/python \
  Tests/test_verified_downloader.py

SDKROOT=/Library/Developer/CommandLineTools/SDKs/MacOSX15.4.sdk \
  CLANG_MODULE_CACHE_PATH=/private/tmp/iproteinstudio-policy-build-clang \
  SWIFTPM_MODULECACHE_OVERRIDE=/private/tmp/iproteinstudio-policy-build-swiftpm \
  /usr/bin/caffeinate -dimsu swift build --disable-sandbox

SDKROOT=/Library/Developer/CommandLineTools/SDKs/MacOSX15.4.sdk \
  /usr/bin/caffeinate -dimsu ./build_app.sh release
codesign --verify --deep --strict --verbose=2 build/iProteinStudio.app
```

The three production-file Swift harness compile commands are unchanged from
[[0029-retire-untrusted-jax-metal-predictors]]. The exact GPU acceptance commands
and their outputs were retained in this work session's tool log; inputs came
from the saved explicit-empty `Hallucinate.yaml`, and outputs were written under
`/private/tmp/iproteinstudio-strict-{intellifold,protenix}-20260822`.

## Limits and what was not tested

- The real Protenix acceptance used Mini, not v2. Both models use the same
  adapter, MSA preprocessing and patched MPS runtime, but a second v2 model load
  was not spent to repeat identical routing coverage.
- The real IntelliFold acceptance used v2-flash, not full v2. Both use the same
  launcher and upstream runner.
- The mixed real-MSA/explicit-empty Protenix case was passed through Studio's
  converter and upstream `need_msa_search`, which returned false. It was not
  followed by another GPU fold.
- No GUI automation was performed. The release app bundle was built, its ad-hoc
  signature verified, and the packaged `intellifold_predict.py` located inside
  its resource bundle; the app itself was not launched for a click-through.
- The existing Boltz unsupported-SVD CPU fallback is a separate, previously
  documented issue and was not changed here.

## Next

Use an aligned-target plus single-sequence-binder Protenix job in an ordinary
design campaign and confirm the saved input JSON contains both durable A3M paths.
When changing PyTorch or Accelerate, add a fresh native-MPS acceptance before
updating the strict launcher pins.
