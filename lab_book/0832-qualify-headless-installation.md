---
entry: 0832
title: Add and qualify headless Studio installation
date: 2026-11-09
author: Codex
type: implementation
status: complete
machine: Apple M4 Max, 40 GPU cores, 64 GB; isolated CPU installation qualification
tags: [install, cli, mcp, headless, reproducibility]
---

## Context

User asks to resolve the app-first staging prerequisite identified in Lab0831,
so people and LLMs can install from GitHub and operate through CLI/SSH without
opening the app. Preserve the existing pinned installer and scientific broker.
Do not disturb the installed runtime or running benchmarks.

## What was done

Added root `install.sh`, bundled `pipeline/install_cli.sh`, transactional
`scripts/stage_assets.py`, and installed `bin/studioctl` / `bin/studio-mcp`
launchers. Source checkout/archive and extracted app-bundle entry points use
one implementation. `--stage-only` selects control/CLI without model weights;
normal selections delegate to the existing portable installer. No source-build,
sudo, Homebrew, compiler, desktop or system-Python prerequisite is introduced.

The stager uses the same execution lease and installer mutex as existing work.
It prepares the complete resource payload before activation, hashes its assets,
rolls back failures and journals interrupted updates for recovery. Projects,
models, retained components/jobs and existing MSA caches are preserved. It seeds
the same scaffold/example MSAs as AppPaths. Ordinary component install failure
keeps the existing resumable/partial-success behavior and propagates nonzero exit.

Added `studioctl project-create` for GUI-free project initialization, with safe
slugs and project-path containment. Launchers bind their own root rather than
silently inheriting another installation from the environment. MCP profile
permissions and scientific schemas remain unchanged. Registered headless tests
in the offline entry point; extended the existing Swift snapshot harness to
compare actual app staging with headless staging. Documented source/archive,
bundle, SSH/assistant, retry/update and diagnostic routes in
[HEADLESS_INSTALL](../docs/HEADLESS_INSTALL.md), README, CLI and AI guides.

## Results

No benchmark measurements or model inference. Ten headless tests pass, covering
actual resource staging/update, cached-data preservation, live execution and
installer locks, failed-update rollback, hard process interruption/recovery,
symlink containment, help/detection without host Python, selection forwarding,
source-archive/bundle entry points, failure propagation, and CLI project creation.
Actual app/headless staging parity passes, including overlays/examples/MSAs and
launchers. The complete offline entry point passes70/70 commands, including Swift tests
and controller harnesses. Final swift build passes. Real install/update retry
passes with all selected MPNN assets preserved and no forbidden tool calls.

Actual network installation in `.build/headless-qualification-0832`: pinned
control runtime and MPNN family installed; doctor, engine detection, project
creation and read/run MCP initialization/tool discovery pass. Admin remains
disabled. Model weights were obtained through the existing checksum-verified
upstream downloads and are not tracked. No source environment was copied.
PATH sentinels for Python, Git, brew, sudo and compiler tools recorded no calls.
The real bootstrap exposed duplicate-slash/physical-alias normalization in
`ensure_python`; fixed its managed-prefix check and reran successfully.

The first full private suite also exposed an existing installer harness missing
the beta isolation fields used by PipelineInstaller. Added explicit inert AppPaths
stub values. The initial documentation-link failure preceded creation of this
entry; both checks must pass in final verification.

## Decision and rationale

Reuse the released component installer and broker; add only their missing
headless bootstrap/staging entry. Bootstrap a pinned Python in a temporary root
when no managed control Python exists, leaving the target untouched until its
execution lease is held. Updates reuse existing control Python. Asset identity
excludes already-generated cache content so retrying yields a stable digest.
Do not use a moving pip environment, require GUI automation, or assemble a
separate scientific launcher.

## Reproduce

```bash
python3 Tests/test_headless_install.py
bash Tests/test_pipeline_snapshot.sh
python3 Tests/run.py
swift build --disable-sandbox -j 4
# Network acceptance in a NEW isolated root; no inference:
PATH=/usr/bin:/bin bash install.sh --root "$PWD/.build/headless-qualification" --stage-only
bash install.sh --root "$PWD/.build/headless-qualification" --without-abmpnn
```

The network commands download real packages/assets. For the sentinel test put
failing executables named python/python3/git/brew/sudo/clang/swift/xcrun/
xcode-select/make before `/usr/bin:/bin` on PATH. The installed launchers and
managed Python still work. Receipts are under `lab_book/artifacts/0832-headless/`.

## Limits and what was not tested

No Enverge connection or M5 hardware qualification; no app GUI opened or installed
app/shared runtime updated. No GPU work or changes to running campaigns. No fresh
network installation of every optional engine, base/all-engine acceptance,
scientific accuracy, actual 14.x macOS host, Gatekeeper or updater test. Source
and bundle route fixtures replace network component installation only; local
Beta bundle staging is explicitly rejected to preserve runtime isolation. The
isolated control/MPNN acceptance uses real downloads. No weights redistributed.

## Public delivery

The user explicitly authorized publication of 0.2.41/build94 on 2026-11-09.
Public main and release/paper-next received the reviewed installation change;
private model/kernel optimizations remain excluded. Source commit
`13b70b00699b30ca3732a4a3d271c0f00fa72048` passed all 70 hosted contracts:
[GitHub run](https://github.com/t-j-fryer/iProteinStudio/actions/runs/42711297661).

Published [0.2.41/build94](https://github.com/t-j-fryer/iProteinStudio/releases/tag/v0.2.41-beta),
including ZIP, DMG, checksums and clean-source build provenance. Independently
downloaded assets match the prepared bytes; CryptoKit verifies the update ZIP's
Ed25519 signature. Version/build, update key/feed continuity, all eight changed
pipeline resources and absence of model weights pass. Archive verification was
performed before activating this commit's generated signed appcast; see the
published-archives receipt. CLI/MCP schema version remains 58.

The actual public GitHub source archive also completed a fresh control-only
installation with PATH=/usr/bin:/bin, followed by doctor and project creation.
Its asset digest matches the actual app-bundle installation; no app launch,
model weights, system developer tools or inference were needed. Receipt:
`artifacts/0832-headless/github-archive-qualification.json`.

Neither installed app was restarted or replaced, and existing shared runtimes
and running benchmarks were untouched. Enverge/M5 qualification remains pending
actual remote access; installation acceptance is not scientific qualification.
