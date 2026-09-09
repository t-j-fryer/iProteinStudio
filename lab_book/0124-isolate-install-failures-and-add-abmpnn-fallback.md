---
entry: 0124
title: Isolate installation failures and add the verified AbMPNN fallback
date: 2026-09-09
author: Codex
type: bugfix
status: complete
machine: Apple Silicon development Mac; no model inference
tags: [install, downloads, provenance, ui]
---

## Context

Following entries 0122 and 0123, the user approved the verified Mosaic alternative
to Zenodo and asked that a download failure not block the whole installation.
AbMPNN was previously a mandatory part of the shared MPNN transaction, so its
failure prevented both core promotion and every later installation stage.

## What was done

- Added a pinned multi-source manifest for AbMPNN. The original and alternative
  serializations have separate SHA-256 pins and separate resumable files. Either
  already-verified variant is reused without network access. Invalid downloads
  never become runtime files. The helper atomically records source provenance.
- Bounded AbMPNN attempts to two per original source and three per alternative,
  with a 15-second connect/read timeout. These are retry policy settings, not
  download-time guarantees. Logged the actual exception on each retry.
- Moved AbMPNN to its own component and receipt. It remains selected by default;
  users can deselect, retry, or remove it independently. Its sequence-design
  choice requires both its verified checkpoint and the core MPNN runtime.
- Ran each installation action in an isolated subshell while retaining the
  parent's installation lock. Component failures report their identity, leave
  successful components intact, and permit independent components to proceed.
  A failed dependency defers its dependent. The final partial result exits 2;
  it is never reported as complete success.
- Separated Boltz affinity, IntelliFold full v2, and Protenix v2/Mini checkpoints
  from base runtime promotion. Moved optional Python preparation inside each
  affected component's boundary. Common Apple-tools/Python-bootstrap failure
  still stops setup because all engines need those prerequisites.
- Added a native partial-result card with actionable errors, log access, and a
  retry that retains the reviewed selection and only runs unfinished components.
  Unselected installed engines keep their availability. Workspace routing now
  accepts a completed predictor even if core sequence design failed; normal
  workflow-specific engine checks still apply.
- Prevented AbMPNN removal from following a linked source directory into an
  original installation. The linked checkpoint is excluded from removal.
- Updated installation documentation and build number to 34. No changes to
  design/scoring models, inference settings, resident workers, or active runs.

## Results

Live production-helper acceptance reproduced the Zenodo read timeout, automatically
retried the original source, then downloaded and verified the Mosaic alternative.
The resulting file was 20,060,943 bytes with the pinned alternative SHA-256.
The temporary model file was deleted; [only provenance metadata is retained](artifacts/0124-abmpnn-live-fallback.json).
Exact tensor/metadata equivalence was established in entry 0123, not re-measured
as an inference benchmark here.

Recovery fixtures exercise real localhost HTTP downloads, invalid checksums,
source-specific partials, cached variants, all-source failure, production component
boundaries, dependent deferral, parent lock retention, and narrow retry. Native
controller tests execute the actual installer with only its process boundary
mocked. Workspace routing tests execute the actual receipt/core-presence helper.
Validation passed: 11 recovery tests (including three base/extra combinations),
3 existing downloader tests, 6 Apple-tools tests, all 9 installer dependency-lock
graphs, runtime transactions, vendor preservation, installer hardening, pipeline
snapshots, the native installer/readiness harnesses, and all six Swift contract
executables. Debug build passed. Release build, ad-hoc signature verification, and packaged-resource checks also
passed. Build 34 app, ZIP, DMG, checksums and signed local appcast were generated
under `build/unsigned-beta-0.2.0-34/`. The recovery scripts and manifest in the app
were compared with their source files. The first package was a dirty-tree local
validation; publication requires a rebuild from the committed clean tree, with
its source identity recorded in `BUILD_PROVENANCE.txt`. No GitHub binary release
was published.

Initial fixture runs exposed an empty-file fixture that did not satisfy the real
IntelliFold size check, and a standalone snapshot compile missing the new helper
source. Both test setups were corrected and rerun successfully. Sandboxed localhost
binding, process visibility, and a non-writable default Swift module cache required
appropriate test permissions or a temporary module cache; these were test-environment
issues, not clean-Mac installation results.

No performance measurements — installer correctness and availability work only.

## Decision and rationale

Use the equivalence-audited, revision-pinned mirror, not an arbitrary URL or an
unchecked replacement checkpoint. Each serialization has its own checksum and
provenance. Keep AbMPNN selected by default while making its failure independent,
rather than allowing it to prevent minibinder workflows from installing.
Keep missing engines unavailable instead of silently substituting weaker models.
Continue independent work rather than treating partial installation as either
complete success or a reason to discard all completed work.

## Reproduce

```bash
python3 Tests/test_install_download_recovery.py
python3 Tests/test_verified_downloader.py
python3 Tests/test_apple_build_tools.py
python3 Tests/test_installer_lock_contract.py
python3 Tests/test_runtime_transaction.py
python3 Tests/test_vendor_pipeline.py
bash Tests/test_installer_hardening_contract.sh
bash Tests/test_pipeline_snapshot.sh
bash Tests/test_apple_build_tools_ui.sh
python3 Tests/run_swift_contracts.py
CLANG_MODULE_CACHE_PATH=/private/tmp/iproteinstudio-modules SWIFTPM_MODULECACHE_OVERRIDE=/private/tmp/iproteinstudio-modules swift build --disable-sandbox --skip-update
bash release/release_app.sh --unsigned-beta  # clean committed source; use --allow-dirty only for local testing
```

The network fixtures require permission to bind localhost. For live acceptance,
run `scripts/download_verified.py` with `--sources scripts/abmpnn_sources.json`,
`--output` and `--provenance` in a fresh temporary directory, then delete the
checkpoint. No live model is installed into the managed runtime during tests.

## Limits and what was not tested

No clean-Mac full scientific-engine installation, model inference, interactive
GUI acceptance, Gatekeeper acceptance on another Mac, or changes to the affected
user's machine. InstalledRuntime checks are workspace routing, not a replacement
for per-engine integrity/availability checks. No global Zenodo outage is inferred
from one network. All approved hosts can still fail; missing files then remain
unavailable until a successful retry. Full XCTest is unavailable on this CLT-only
host; standalone native contract executables are used. Active campaigns and their
managed runtime remain untouched. No model weights are committed or redistributed.

## Next

Test the new DMG on the affected Mac and use the component-level errors if another
host fails. Publishing a GitHub binary release is separate from the local build.
