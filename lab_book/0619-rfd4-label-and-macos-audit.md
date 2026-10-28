---
entry: 0619
title: Correct RFD4 labels and audit macOS requirements
date: 2026-10-28
author: Codex
type: audit
status: in-progress
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

Complete the release checks and record public delivery. Older-OS qualification
is separate work and is not implied by this label correction.
