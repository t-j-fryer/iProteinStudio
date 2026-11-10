---
entry: 0836
title: Deliver optimized engine adapters across app and headless workflows
date: 2026-11-10
author: Codex
type: implementation
status: complete
machine: Apple M4 Max, 40 GPU cores, 64 GB unified memory
tags: [esmfold2, rfd4, release, cli, mcp, provenance]
---

## Context

The user asks to deploy Claude's committed ESMFold2/RFD4 optimizations across app,
CLI, MCP and GitHub. Commit c0e6a78 contains the three changed science adapters;
its timing/correctness evidence is recorded in development entries0819,0825,0826,
with the later ESMFold2 Figure3a remeasurement in0828. Those are existing
measurements by Claude, not measurements made for this integration.

Read-only file comparisons confirm installed public0.2.40/build93, Beta0.2.39-dev/
build92 and the shared staged scripts all differ from those three source files.
Opening the old public app re-stages its old bundle. Job snapshots correctly
preserved the code they actually accepted; source commits never updated binaries.
No confidential molecule or workspace contents were inspected.

## What was done

Prepare0.2.42/build95 with the original three optimized files unchanged. Add a
workflow release manifest with checked hashes, defaults and monotonic generation.
App/headless staging refuse downgrades and equal-generation conflicting releases;
packaging and new snapshot creation verify adapter contents. Swift snapshots and
CLI/MCP code snapshots retain the release identity. CLI doctor reports executable
and installed identities; system_detect reports installed identity. Bridge59 keeps
the existing request schemas and execution broker. Historical snapshots remain
readable/resumable. Backend environments, upstream model revision and weights
are unchanged; the changed adapter code remains retained per job.

## Results

No new performance measurements. Private and independent public offline suites
both pass71/71 commands; both app builds and packaged-resource checks pass.
Focused release tests pass5/5; headless staging/recovery tests pass11/11, including
sealed resource immutability. Actual Swift/headless staging parity passes with
390 resources/seeds and downgrade rejection. Snapshot/manifest tests preserve
historical jobs and reject changed adapters before new submission.

The actual public bundle upgrades the previous0.2.41 isolated control installation
through its headless entry point. Installed CLI doctor and a fresh MCP stdio
session confirm bridge59/server1.20.0 and generation2026111001. Both executable
and installed release identities agree. Its strict app signature still verifies
after installation; no model weights or inference were needed. See the sanitized
local-qualification receipt. The first acceptance probe incorrectly equated the
bridge contract number with the MCP semantic version; corrected that assertion
and assigned the additive server version1.20.0.

The new validator import initially exposed two integration issues: importlib-based
stager loading needed its own script search path, and bytecode writes had to be
disabled before importing the validator. Fixed both and reran the failed recovery
case, the full suites and final headless/sealed-bundle acceptance.

## Decision and rationale

Deploy the validated source through rebuilt bundles and the standard locked
stager. Do not hand-copy adapters into the shared runtime: an old bundle would
replace them again. Preserve old runs and make the new code auditable before
launch. The guard applies to updated binaries; it cannot retrofit old installed
applications, so both installed copies need replacement to resolve that route.

ESMFold2 BF16 changes numerical outputs slightly and can shift borderline gates;
RFD4's exact-output evidence is separate from its less clearly resolved total
throughput. Do not quote the later cross-date Figure3a reduction as the isolated
BF16 gain. Do not expose a new invented performance setting or change scheduler,
MSA, steps, seeds or model weights to make deployment appear faster.

## Reproduce

```bash
python3 Tests/test_workflow_release.py
python3 Tests/test_headless_install.py
bash Tests/test_pipeline_snapshot.sh
python3 Tests/run.py
bash release/build_local_beta.sh
bash Tests/test_packaged_resource_bundle.sh 'build/iProteinStudio Beta.app'
```

## Limits and what was not tested

No new GPU inference or benchmark for this delivery, no Enverge/M5 connection, no claim of
universal speedup or cross-hardware numerical equivalence. Running scientific
work and immutable prior outputs have not been changed. Public publication and
app replacement are not complete until recorded below.

## Public delivery

The user explicitly approved publication and both app replacements on2026-11-10.
[Release0.2.42/build95](https://github.com/t-j-fryer/iProteinStudio/releases/tag/v0.2.42-beta)
is tagged at clean packaging commit b829135d050c29d860e46e4c4f417d25d2281bf9.
Source qualification passed71/71 hosted commands with no failures:
[GitHub run](https://github.com/t-j-fryer/iProteinStudio/actions/runs/42881502747).

Independently downloaded ZIP/DMG, checksums and provenance match the prepared
assets. CryptoKit verifies the ZIP's Ed25519 update signature; all changed bundled
resources and the optimized manifest match source, with no model weights. The
published-archives receipt records verification before activating this commit's
signed update feed. Source, tag and feed are kept distinct for reproducibility.

Installed public0.2.42 and Beta0.2.42-dev both report build95, pass strict signatures
and were reopened using quit/open commands only. Previous bundles are retained.
All three adapter hashes match both bundles and the shared staged pipeline after
launch. A fresh production code snapshot verifies the same release and its full
inventory. Fresh CLI/MCP sessions report bridge59/server1.20.0 and checked release
generation2026111001. The existing MCP connection attached to this chat remains
loaded with the previous server and requires reconnecting; new sessions use the
updated code. No workspace UI or confidential molecules were viewed, no existing
job snapshot/raw output was changed, and no new model inference was run.

## Next

Use a new accepted plan/campaign for the optimized implementation; reconnect
already-open MCP clients. Existing campaigns intentionally keep their recorded
code. Enverge/M5 qualification remains a separate task after remote access.
