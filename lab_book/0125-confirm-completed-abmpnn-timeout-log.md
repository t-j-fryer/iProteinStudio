---
entry: 0125
title: Confirm the completed AbMPNN timeout log
date: 2026-09-09
author: Codex
type: audit
status: complete
machine: local Apple Silicon Mac; inspection of another user's supplied setup log
tags: [install, downloads, support]
---

## Context

After build 34 was prepared in entry 0124, the user supplied
`setup-1788986582-1BA80A39 (1).log` to clarify the reported installation failure.

## What was done

Read the complete log, compared its bytes with the previously supplied file,
and checked build 34's source manifest and local build provenance. No model,
runtime, or application files were changed. The raw third-party log is not
copied into the repository.

## Results

The new file is 8,626 bytes and begins with every byte of the earlier 3,433-byte
log. Its SHA-256 is
`1c4bea3181b9f8e6da6a8dd503c9d17e2a125bff0f60c13462d8a7e00ad4d098`.
Apple's C++ compile/link/run check passed. Boltz reported ready and the three
general MPNN checkpoints were already present. AbMPNN remained at zero downloaded
bytes through 20 attempts, ending with `TimeoutError: The read operation timed out`
while awaiting the HTTPS response status, followed by a fatal `NHFAIL`.

This is a completed copy of the earlier attempt using the old installer path.
Build 34 uses a separate AbMPNN component, two original-source attempts followed
by the pinned alternative, and component-level failure continuation. This log
does not exercise that implementation. No new throughput measurement was made.

## Decision and rationale

Recommend replacing the older app with the prepared build 34 and retrying setup,
retaining verified downloads. No further code change is justified by this log;
changing the Apple tools or deleting the managed installation would not address
the observed download timeout.

## Reproduce

Read both named files from the user's supplied Downloads location and compare
`new.read_bytes().startswith(old.read_bytes())`. Search the completed log for
`NHSTATE`, `NHFAIL`, `20 attempts`, and `compile/link/run`.
Compare the retry settings in `scripts/abmpnn_sources.json` with the log and
check `build/unsigned-beta-0.2.0-34/BUILD_PROVENANCE.txt`.

## Limits and what was not tested

No remote access to the affected Mac, fresh installation, or new network test.
The log does not identify the exact app build number or establish whether the
person has subsequently opened build 34. It cannot establish a global outage.

## Next

Use the build 34 DMG from entry 0124; inspect a newly created setup log if the
updated installation still encounters a failure.
