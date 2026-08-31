---
entry: 0048
title: Harden managed installation without perturbing the resident benchmark
date: 2026-08-31
author: codex-gpt-5
type: implementation
status: complete
machine: Apple M4 Max, 40-core GPU, 64 GB unified memory, macOS 26.x
tags: [installer, downloads, cancellation, reproducibility, ui, runtime]
---

## Context

The read-only installer audit in `0047` found that nine isolated scientific
environments were justified by real compatibility boundaries, but the mechanism
managing them was not yet equivalently robust. The resident-predictor benchmark
was still timing GPU campaigns from a separate frozen worktree, so this first
implementation slice had to avoid the active worktree, the installed runtime and
any build, package-resolution or model workload that could contaminate timing.

## What was done

- Created the isolated `agent/installer-runtime-hardening` worktree from current
  `main`; no scientific runner or installed engine was changed.
- Wrapped GUI setup in `caffeinate` and made CLI setup self-protecting. Added an
  atomic, stale-owner-aware `.install.lock` shared by install, repair, reuse and
  materialisation; the GUI refuses uninstall while that lock exists.
- Changed Cancel to terminate the installer and every discovered descendant
  (`pip`, Git, Python, compilers and downloaders), wait for process exit, and keep
  setup controls disabled until cancellation is complete.
- Added a durable per-attempt log under `~/.iproteinstudio/logs/installer`, a
  Finder reveal action in first-run setup and Engines, bounded phase history,
  aggregate approximate footprint consent and a conservative free-space
  preflight with a 3 GB reserve. The preflight credits allocated bytes already
  retained by an interrupted component so a legitimate resume is not budgeted
  as a second full install.
- Added explicit `incomplete`, `broken`, `update` and `busy` parser states while
  retaining `ok`, `missing` and `skipped` compatibility. Detection now reports
  partial directories and broken links rather than collapsing them into missing.
- Strengthened the verified downloader to recover legacy partials exposed under
  final filenames, promote an already-complete `.part` without networking,
  validate the requested digest, validate HTTP range origins, flush data before
  promotion and handle a completed Range request returning HTTP 416.
- Routed Boltz structure/affinity/CCD, all four MPNN-family weights, AntiFold and
  RFdiffusion3 checkpoints through the same resumable verified downloader.
  Protenix already used it. RFdiffusion3 progress is now streamed to the GUI and
  retained in its component log instead of disappearing behind redirection.
- Made app-owned pipeline resource replacement copy-and-swap with rollback per
  item. Generated `__pycache__`, `.pyc`, `numba_cache` and `.DS_Store` payloads
  are pruned from staged resources and from assembled app bundles.
- Added behavioural installer-lock/incomplete-state contracts and downloader
  resume/pre-promotion tests, and documented the new runtime behavior in
  `docs/CLI.md`.

## Results

No performance measurement was made; this was a source-only implementation while
the GPU benchmark remained active.

| Condition | n | Metric | Value |
|---|---:|---|---:|
| Downloader local contract | 3 tests | pass/fail | 3 passed |
| Installer hardening synthetic contract | 1 script | pass/fail | passed |
| Existing component reuse/materialisation contract | 1 script | pass/fail | passed |
| Descendant cancellation contract | SIGTERM-resistant grandchild | pass/fail | passed |
| Full Swift package build | 1 clean scratch build | pass/fail | passed |
| Internet/model/GPU transfer | 0 | executed | none |

The downloader server test used loopback only and transferred a 2.4 MB synthetic
payload. No external network request or model import was made.

## Decision and rationale

Correctness mechanisms that do not require changing the runtime were implemented
first. The work deliberately does **not** collapse environments: the audit found
that doing so would couple incompatible NumPy/Torch/Python/ESM contracts. It also
does not claim installer-v2 completion. Exact managed CPython/uv builds,
hash-locked full dependency graphs, versioned environment staging, general
component receipts, shared Protenix common data and checkpoint-level install/
remove controls require migrations and cold-install acceptance after benchmarking.

The app estimates installed footprint conservatively rather than presenting it
as a measured download size. This avoids false precision and leaves enough free
space for temporary files and macOS while an environment is built.

## Reproduce

```bash
cd /Users/thomasfryer/iProteinStudio/.worktrees/installer-runtime-hardening
python3 Tests/test_verified_downloader.py
bash Tests/test_installer_hardening_contract.sh
bash Tests/test_installer_component_contract.sh
bash Tests/test_process_runner_cancellation.sh
bash -n build_app.sh
bash -n Sources/iProteinStudio/Resources/pipeline/setup_pipeline.sh
bash -n Sources/iProteinStudio/Resources/rfd3_overlay/install_rfd3.sh
```

The downloader test needs permission to bind a localhost-only ephemeral port.
`bash Tests/test_process_runner_cancellation.sh` exercises the compiled
`ProcessRunner` against a SIGTERM-resistant child/grandchild tree.

## Limits and what was not tested

- `swift build` passed after the performance benchmark finished. `build_app.sh`
  is reserved for the final integrated tree so the shipped bundle contains both
  this installer work and the resident-worker policy.
- No real setup, cancellation, repair, update, removal, disk-full interruption,
  cold install or checkpoint download was executed.
- Process-tree cancellation passed a compiled synthetic long-lived
  child/grandchild contract. Clicking Cancel in the packaged GUI remains an
  unautomated interaction test.
- IntelliFold and OpenFold downloads remain checksum-verified and transactional
  but restart interrupted transfers. Their upstream transfer mechanisms need a
  validated URL/range migration before the UI can promise resume for them.
- Most engines still lack comprehensive immutable receipts, environments are
  still mutated in place, and ambient/uv Python toolchains are not yet exact,
  managed, checksum-pinned builds.
- Checkpoint-level choices (IntelliFold full v2, Protenix v2/Mini and Boltz
  affinity) and Protenix common-data deduplication are not in this slice.
- Copy-and-swap staging is per resource item, not yet an immutable pipeline
  snapshot bound to each run manifest.

## Next

Next implement exact toolchains/receipts and versioned component staging before
touching the current managed runtime. Validate one cold minimal install, one
interrupted-and-resumed install, update/rollback, repair and component removal
before claiming a fully transactional installer.
