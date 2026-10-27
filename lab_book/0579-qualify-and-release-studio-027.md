---
entry: 0579
title: Qualify motif beta and publish Studio 0.2.27
date: 2026-10-26
author: Codex
type: implementation
status: in-progress
machine: Apple M4 Max, 40-core GPU, 64 GB unified memory
tags: [release, motifs, rfd4, packaging]
---

## Context

The user requested completion of the remaining qualification and publication of downloadable GitHub releases following source publication 0577.

## What was done

Work proceeds in `.worktrees/release-0.2.27`, from 3691828. Validation 0259 declares a one-root KSI technical pilot, two sequence designers, one fixed cycle and one proposal per designer: two guided and two separate untemplated Boltz calls. Existing memory-override and pause authorizations apply only to these bounded tests. Production queue identities and order are recorded before interruption.

## Results

Qualification host: Apple M4 Max, 40-core GPU, 64 GB unified memory, macOS 26.6.1 (25G76). No speed or enzyme-activity claim.

Runtime package `881120a852911b115009d9d846f3751b481b032ab4d58b0390f55581198a82bd` excludes three unrelated learned TorchMetrics LPIPS `.pth` payloads found during the release audit. Every retained file matches the already model-tested RFD4 runtime from 0559. A new packaging guard distinguishes Python `.pth` path loaders and exact static chemical tables from learned checkpoints. No weights were published. Final archive SHA-256 `538bec0fd641eaeea8f95778a404bf547059f24d149e3fa79869b2f47961c1d6`, 442106152 bytes, matches GitHub's uploaded asset digest. Public runtime: [runtimes-2026.10.26-1](https://github.com/t-j-fryer/iProteinStudio/releases/tag/runtimes-2026.10.26-1).

The exact final archive passed full-inventory verification, extraction, transactional activation, isolated native imports and both real-native RFD4 fixture tests in a new root containing spaces and Unicode. First extraction exposed a symlink-only parent directory bug; extraction now creates that parent, with a real archive regression. Five runtime package tests and four portable installer tests passed.

Motif failed attempts remain intact. Attempt 01 failed native parsing because AtomWorks split a mixed protein/ligand chain. Attempt 02 reached generation but its exported ligand was numbered 1 instead of the original residue 801. Conditioning now assigns one unique chain and residue 1 per ligand, with a reversible source map; atom names, elements and coordinates remain unchanged, and original source bytes remain exact. All 41 preparation fixtures and native parser checks for KSI, PGK multiligand and OMP cross-chain cases pass. Attempt 03 completed a guided/untemplated pair, then actual broker interruption/resumption exposed tuple/list JSON inequality in the frozen reference. Canonical comparison fixes replay without rewriting an unchanged reference; a mutation still fails closed. Eighteen motif contract tests pass after the additional native-label test described below.

The full fast suite passed 67/67 command groups, including all 14 Swift XCTest cases and standalone Swift contracts. Public motif bridge tests passed 2/2; `swift build` passed. Initial motif-unit invocations used unsuitable existing environments (Boltz lacked Biotite; RFD3 lacked Gemmi); the existing Protenix interpreter passed all 17 without altering any environment.

Native UI inspection partially recovered: the recommended easy/hard buttons, saved workflow, six intention-based custom options and motif chooser’s template-guided Boltz beta button were exposed in the accessibility tree. After clicking the beta button the external computer-use pipe closed repeatedly; its destination screen, full visual inspection and VoiceOver acceptance are not claimed. No scientific job was started from the UI. See `ui-observation.json` in the validation output.

Attempt 04 completed all four native Boltz predictions and broker resume, but the strict output audit rejected generic native `LIG` residue labels. The submitted CCD entity map now produces a separately saved mapped PDB and identity receipt; native PDB bytes remain intact. Completed-unit receipts also bind native confidence JSON. A read-only replay of the two retained untemplated outputs into a separate audit directory passed atom/element, sequence and metric validation. Neither passed the configured geometry gates; no thresholds were changed.

Final attempt 05 passed the derived output audit. Managed job `job-03883c318c6e`, plan SHA-256 `03883c318c6e2493ea23370ce7969bdd62b127abb1b83060f055336382f42061`: one accepted KSI root, two valid proposed sequences, two guided and two untemplated predictions. Exact sequence, residue/ligand identity, heavy atoms/elements, finite complete backbone coordinates and native confidence passed. The two separate process sessions each recorded one Boltz model load, native MPS and fallback=0. After the intentional interruption, all 18 completed files retained both hashes and modification timestamps. Recomputed geometry metrics agree within 1e-6 numerical tolerance; gate decisions are identical. Neither candidate passes the configured geometry gates. No independent-family or experimental hit is claimed.

The two managed memory logs contain 63 and 29 complete samples, zero sampling errors, with explicit override policy. Maximum sampled process-tree footprint was 5942632944 bytes and RSS 7927988224 bytes on the host described above. These account shared pages imperfectly and are not exact physical RAM or calibrated admission estimates. No memory profile was promoted.

The public result overview exposes both designer groups and preserves guided/untemplated roles with no independent-hit verdict. The already-running connected MCP process still had an old catalog; a fresh installed read-profile process correctly discovered/reviewed the runs. Long-lived clients must reconnect after bridge updates.

Installer review also found that RFD4 was absent from the retry parser, and that a pre-release local package could mask the newly published runtime. Both are corrected: the shipped catalog takes precedence when an engine has a public profile; explicit developer local-package selection remains separate. Six portable installer tests pass (the new filesystem fixture initially needed macOS canonical path resolution). The actual installed RFD4 update exercised this path successfully. Its first redundant public transfer was deliberately stopped after slow progress; partial bytes remain. The retry consumed the exact local archive whose digest matches GitHub's asset, reused all verified installed model assets and activated the public runtime identity. This cached upgrade is separate from the untouched empty-root test, which downloads all assets normally.

Bridge 46, GUI qualification copy, README and the evidence skill now distinguish this bounded software acceptance from broader scientific qualification. Both skills validate. Final Swift build passed. The installed doctor reports bridge 46, and installed detection reports RFD4 ready under manifest `881120a852911b115009d9d846f3751b481b032ab4d58b0390f55581198a82bd`.

Paused production work was restored in recorded order: `job-4df41f91d918` running, `job-1e0a8a779e14` queued, and the subsequently started/paused `job-ae5e53a4beb8` queued third. All original plan digests match. The earlier `job-b3e3f8606412` had already completed and was not restarted. Retained queue and install receipts are under this validation output. The distribution verifier passed against the existing public 0.2.26/build 72 app: both full downloads match checksums/GitHub digests, the live feed matches, Sparkle verification succeeds with the unchanged key, the extracted app passes strict deep signature verification and the DMG verifies. No updater installation was performed. Bounded direct/API runtime download probes timed out at 90/60 seconds with partial files retained; these are network-transfer limits, not complete-file checksum failures. The full empty-root installer continues without preseeded model assets. Empty-root installation and app publication remain in progress.

## Reproduce

See `Validation/experiments/studio_release_027_v1/manifest.json` and the managed plan receipts in `Validation/output/studio_release_027_v1/`.

## Limits and what was not tested

One benchmark motif is a software smoke test, not broad motif performance qualification. No wet-lab testing, threshold promotion, memory calibration or second physical Mac. Other template engines and arbitrary custom-motif workflows remain outside this Boltz beta acceptance.

The first empty-root base attempt caught two RFD4 catalog entries for locally generated Hugging Face tree-cache JSON files. Their claimed upstream URLs return 404. The exact failed downloader was stopped to allow other components to finish, and both cache-only entries were removed. All actual upstream model/configuration hashes remain unchanged. The catalog regression now forbids cache directories in asset paths and URLs. Initial logs/receipts remain intact; retry uses the same isolated root and its already verified public downloads, without preseeded model assets.
