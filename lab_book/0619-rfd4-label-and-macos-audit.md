---
entry: 0619
title: Correct RFD4 labels and audit macOS requirements
date: 2026-10-28
author: Codex
type: audit
status: complete
machine: Apple M4 Max, 40-core GPU, 64 GB unified memory
tags: [rfd4, install, release, compatibility]
---

## Context

The RFD4 installation label and unpublished-runtime note survived earlier
integration/release work. The user requested correction and asked which tools
really need recent macOS versions.

## What was done

Removed RFD4's blanket experimental classification from the installer, README
and MCP memory error. Preserve the uncalibrated-memory override requirement.
Corrected the published-runtime description. Added `docs/MACOS_SUPPORT.md` and
linked current documentation to distinguish dependency deployment targets,
conservative support gates and actual older-OS qualification.

Read each listed native file in five installed runtime manifests with `otool -l`.
[Audit script](artifacts/0619-macos-audit/audit.py) and
[results](artifacts/0619-macos-audit/native-minimums.json) retain relative package
paths, counts and maxima. No inference or performance measurements were made.

## Results

| Runtime | Native binaries checked | Maximum deployment target | Cause |
| --- | ---: | --- | --- |
| Protenix | 539 | 26.0 | bundled Kalign executable |
| OpenFold3 | 458 | 26.2 | MLX core/libraries |
| RFdiffusion3 | 527 | 26.2 | MLX core/libraries |
| ESMFold2 shared by Full/Fast/600M | 527 | 26.2 | MLX core/libraries |
| RFD4 | 657 | 14.0 | highest native dependency target |

Swift build and the existing memory-admission regression suite passed.
The memory override remains enforced; only its descriptive text changed.

## Decision and rationale

Do not call RFD4 experimental due to incomplete memory calibration. Do not
claim a blanket latest-OS requirement. Keep current installation gates until
older-OS execution is qualified: binary load commands alone cannot establish
operator availability or scientifically valid output. The RFD4 gate is explicitly
identified as conservative, while the Protenix gate originates in an auxiliary
binary that could be rebuilt. Existing immutable archives are unchanged.

## Reproduce

Run the audit script with Python on an installation containing the five named
components. It reads each `runtime.json` native-file inventory and invokes
`otool -l`; no models are loaded. `swift build` is required before release.

## Limits and what was not tested

No older-macOS machine, lower-target rebuild, inference comparison or performance
benchmark. Remaining engines' requirements are read from the shipped catalog,
not newly exhaustively binary-audited. These findings do not certify older-OS
inference. Version 0.2.30/build76/bridge50 packages only wording and documentation.

## Next

Published [v0.2.30-beta](https://github.com/t-j-fryer/iProteinStudio/releases/tag/v0.2.30-beta),
build 76, from source `6e6596d00dd9d470b2f0049979517748896b2f1c`; initial
appcast commit `dedb4b1`. Release build and package-resource contract passed;
27 memory-admission tests passed; bundled CLI doctor reports bridge 50.
Public DMG/ZIP downloads passed GitHub digests, checksums, Sparkle signature,
previous-key continuity, codesign and DMG checks. [Public receipt](artifacts/0619-macos-audit/download-verification.json).

Installed the verified public ZIP, retaining the previous app for rollback.
The Engines UI visibly shows **RFD4** without the experimental label. The
active campaign retained its independent worker and saved plan; identifying
operational details remain local. Managed bridge 49 remains in use until the
active job releases its execution lease, when Studio stages bundled bridge 50.
The campaign was not cancelled and its runtime was not replaced.

Older-OS qualification remains separate work. No lower-version compatibility
claim or scientific result was added by publishing this release.
