---
entry: 0047
title: Audit and simplify the managed runtime installer
date: 2026-08-31
author: codex-gpt-5
type: audit
status: complete
machine: Apple M4 Max, 40-core GPU, 64 GB unified memory, macOS 26.x
tags: [installer, dependencies, environments, reproducibility, usability, storage]
---

## Context

The app now exposes nine supported scientific components through one graphical
installer, but the implementation accumulated one virtual environment per
compatibility island and several generations of download, detection and update
logic. The owner asked whether the environment count could be reduced and how
installation could become more robust and approachable while the resident-model
benchmark continued independently.

This was a read-only audit of the installer, current managed runtime and existing
acceptance record. No environment, checkpoint, cache or active process was
changed.

## What was done

- Mapped `PipelineInstaller`, `AppPaths`, `setup_pipeline.sh`, the RFdiffusion3
  installer, component UI, uninstall behavior, download helper, package locks
  and installer contract tests.
- Inspected the nine installed environments, their Python/Torch/NumPy/MLX
  compatibility boundaries, source trees, model directories and actual disk
  footprints.
- Compared detection with installation pins and receipts, and traced first
  install, retry, cancellation, reuse, materialisation, app update and uninstall
  behavior.
- Checked the SwiftPM resource tree for ignored build artifacts that can still
  enter `.copy` resources.

## Results

### Measured local footprint

| Condition | n | Metric | Value |
|---|---:|---|---:|
| Managed runtime | 1 | total logical disk use | 33 GB |
| Engine virtual environments | 9 | logical disk use | 8.4 GB |
| Managed model directories | 5 top-level families | logical disk use | 19 GB |
| Managed source checkouts | 7 | logical disk use | 1.6 GB |
| RFdiffusion3 checkout, environment and weights | 1 | logical disk use | 4.6 GB |
| Retained extracted Boltz CCD archive | 1 | redundant file size | 1,855,662,080 bytes |
| Duplicated Protenix common chemical data | 4 files x 2 | duplicate logical size | about 655 MB |
| User-global uv cache | 1 | logical disk use, not Studio-exclusive | 14 GB |
| User-global pip cache | 1 | logical disk use, not Studio-exclusive | 2.6 GB |

The active filesystem had 400 GiB available. No file was removed. The cache
figures cannot be attributed wholly to Studio and are not a safe automatic
cleanup target.

### The logical environments should not be merged blindly

The apparent overlaps hide validated incompatibilities:

- Boltz and RFdiffusion3 both use Torch 2.13.0, but currently require NumPy
  1.26.4 versus 2.5.1 and different chemistry/MLX stacks.
- IntelliFold and OpenFold both use Torch 2.6.0, but currently require NumPy
  1.26.4 versus 2.4.6 and different Python/MLX stacks.
- LigandMPNN and LASErMPNN both use Torch 2.2.1, but use NumPy 1.23.5 versus
  1.26.4; LASErMPNN also carries locally compiled PyG extensions.
- AntiFold remains on Python 3.10 and Torch 2.2.0 with older Biotite.
- Protenix v2/Mini and Constraint share most packages, but Constraint must not
  contain `fair-esm`; that absence is a scientific loading contract, so a shared
  environment would make its behavior ambiguous.

Nine logical environments are therefore defensible. The correct simplification
is one transactional installer and shared immutable artifacts, not one large
Python environment whose resolution couples unrelated engines.

### High-priority robustness findings

1. `uv` is installed by an unpinned `curl | sh`, Python is selected from ambient
   `PATH` when available, and minor versions rather than exact builds are
   requested. Installed venv interpreters currently point outside the managed
   root to both `~/.local/share/uv/python` and `/Library/Frameworks/Python.framework`.
   Consequently copying `~/.iproteinstudio` alone is not actually self-contained.
2. Only Protenix Constraint has a comprehensive install receipt. Most detection
   checks only executable/file presence, so an old source revision, changed
   package graph or corrupted-but-present checkpoint can still appear installed.
   A changed pin also has no clean upgrade path: existing pinned repos cause the
   installer to fail rather than stage and swap a new version.
3. Most environments are not complete hash-locked resolutions. Several install
   only top-level pins, upgrade `pip` without a pin, or install editable projects
   whose transitive dependency ranges can resolve differently later.
4. Selecting any new engine reruns the unconditional MPNN installation. Existing
   environments are modified in place rather than built transactionally, and no
   installation lock prevents two app copies or an active run from overlapping
   an install/update.
5. `ProcessRunner.cancel()` terminates only the immediate shell and immediately
   re-enables setup controls. A descendant `pip`, compiler or downloader may
   continue, and a second install can then start. The whole installer is not
   protected by `caffeinate`.
6. The UI has no free-space preflight, aggregate download size, persistent
   installer log, phase timing or actionable diagnosis. Unprefixed pip output is
   discarded from the interface. The generic claim that partial downloads are
   retained is true for the verified Protenix helper and RFdiffusion3 checkpoint,
   but false for several Boltz, IntelliFold, AntiFold and OpenFold transfers.
7. App updates replace staged pipeline files one item at a time rather than
   switching an immutable version atomically. A crash or a surviving detached
   campaign can therefore observe mixed script generations. Linked RFdiffusion3
   installations are also overlaid in place.
8. Ignored `__pycache__` directories and a local `numba_cache` directory exist
   below SwiftPM `.copy` resources. They have entered build resource bundles even
   though Git ignores them, so bundle contents can depend on developer-machine
   debris. A debug bundle can also stage a top-level `numba_cache` over the
   managed cache.
9. Reuse of an existing installation validates presence far more strongly than
   compatibility. Except for Constraint, linked engines can bypass the source,
   patch, package and model fingerprints claimed by the standalone installer.
10. Checkpoint granularity is too coarse for informed storage choices. Installing
    IntelliFold always downloads flash (435 MB) and full v2 (3.40 GB); installing
    Protenix always downloads Mini (537 MB) and v2 (1.86 GB); Boltz always installs
    its 2.06-GB affinity checkpoint. These should be individually manageable
    capabilities over shared runtimes/data.

### Existing strengths worth preserving

- Source revisions and model hashes are explicitly pinned in the installer.
- Protenix transfers use a timeout-aware, resumable, atomic verified downloader.
- Constraint detection fingerprints its patches and patched source and enforces
  native MPS with no CPU fallback.
- Results, projects and MSA caches are outside component removal plans.
- Large downloads have an explicit review/consent screen, and app updates are
  already separated from engine/checkpoint updates.
- Component isolation currently prevents one engine upgrade from resolving a
  different dependency graph for every other engine.

## Decision and rationale

Keep the nine scientific environments for now. Do not merge them merely to make
the directory tree look simpler. Instead implement a versioned runtime manager:

1. **Deterministic toolchain.** Bundle or checksum-pin one uv release, install
   exact CPython patch builds under `~/.iproteinstudio/toolchains`, ignore
   ambient Python, and use frozen hash-locked per-engine resolutions.
2. **Transactional components.** Build each component in a staging directory,
   verify imports, accelerator policy, source/patch/package/checkpoint hashes and
   a lightweight engine health check, then atomically switch a `current` link.
   Retain the prior version until the switch succeeds.
3. **Receipts and state.** Give every component one immutable receipt and expose
   `ready`, `update available`, `incomplete`, `broken` and `busy`, rather than
   collapsing everything into `ok` or `missing`.
4. **One download layer.** Route every checkpoint through the verified resumable
   downloader; record progress, throughput and errors in a durable install log.
   Protect the full operation from sleep and cancel the complete process group.
5. **Shared storage without shared imports.** Use a managed uv cache/APFS cloning
   for duplicate wheels, one immutable Protenix common-data directory referenced
   by both products, and a shared Git object store/worktrees where worthwhile.
   Measure physical savings before making a claim.
6. **Capability-level checkpoints.** Separate runtime/common data from optional
   IntelliFold full v2, Protenix v2, Protenix Mini and Boltz affinity weights.
   Keep Constraint as its own isolated runtime.
7. **Noob-proof manager.** Offer Essentials, Independent validation and Complete
   presets; show total transfer, installed footprint and available space; expose
   Install, Update, Repair, Remove, Reveal files and Clear safe caches. Never
   delete shared/user-global caches automatically.
8. **Versioned pipeline snapshots.** Stage app-owned runner/overlay versions
   immutably and bind each new run to one version so an app update cannot change
   helpers midway through a detached campaign.

The first implementation slice should address correctness before deduplication:
pin the toolchain, add receipts/locks, make install/cancel transactional, unify
downloads/logging, and exclude generated resource artifacts. Storage cleanup and
checkpoint splitting follow once migrations are covered by tests.

## Reproduce

```bash
cd /Users/thomasfryer/iProteinStudio/.worktrees/resident-benchmark

du -sh /Users/thomasfryer/.iproteinstudio
du -sh /Users/thomasfryer/.iproteinstudio/venvs/* \
  /Users/thomasfryer/.iproteinstudio/rfd3/.venv
du -sh /Users/thomasfryer/.iproteinstudio/models/*
du -sh /Users/thomasfryer/.iproteinstudio/src/*

sed -n '1,1234p' Sources/iProteinStudio/Resources/pipeline/setup_pipeline.sh
sed -n '1,360p' Sources/iProteinStudio/Core/PipelineInstaller.swift
sed -n '1,360p' Sources/iProteinStudio/Resources/rfd3_overlay/install_rfd3.sh

ls -l /Users/thomasfryer/.iproteinstudio/venvs/NanoHunter_boltz/bin/python*
sed -n '1,30p' \
  /Users/thomasfryer/.iproteinstudio/venvs/NanoHunter_boltz/pyvenv.cfg
```

## Limits and what was not tested

- No cold install, package download, upgrade, repair, cancellation or uninstall
  was executed because the GPU benchmark was active and this was an audit.
- Logical sizes came from `du`; APFS clone/shared-block physical savings were not
  measured.
- The installed environment reflects this development Mac. A genuinely new Mac
  can expose network, certificate, proxy and Xcode-toolchain failures absent here.
- The proposed consolidation has not been implemented or benchmarked. Dependency
  boundaries are observations of validated current environments, not proof that
  future upstream ports can never share a runtime.
- The 14-GB uv and 2.6-GB pip caches are user-global and may contain unrelated
  projects; they must not be attributed to or removed by Studio without an
  ownership-aware migration.

## Next

Implement an installer-v2 foundation in the order above, with synthetic
transaction/interruption tests first and one cold minimal install plus one
upgrade/rollback acceptance on a separate Apple-Silicon user account before it
replaces the current installer.
