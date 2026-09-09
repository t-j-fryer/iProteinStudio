---
entry: 0123
title: Check Zenodo status and verify an AbMPNN alternative
date: 2026-09-09
author: Codex
type: audit
status: complete
machine: local Apple Silicon Mac; tensor comparison on CPU
tags: [install, downloads, provenance]
---

## Context

Following entry 0122, the user requested internet research into whether Zenodo's
failure was widespread and whether another route could unblock AbMPNN setup.

## What was done

Read Zenodo's official blog, roadmap, service principles and linked UptimeRobot
status page. Searched public AbMPNN integrations for alternate file sources.
Inspected Mosaic's repository and attribution notice at immutable revision
`70fec525423f5f87156a1a957b4a4048f9f8e676`. Downloaded its AbMPNN file temporarily,
verified the installed original against Studio's pinned SHA-256, and compared both
checkpoints using `torch.load(..., map_location='cpu', weights_only=True)`.
Recursively checked dictionary keys, scalar metadata, tensor shapes, dtypes and
exact values. The temporary weights were deleted; only verification metadata is
retained in [the JSON record](artifacts/0123-abmpnn-mirror-verification.json).

## Results

No performance benchmark or inference run.

- Zenodo's January 28, 2026 announcement acknowledges platform-wide slowdowns,
  interrupted service and impaired file transfers due to heavy automated traffic.
  Its August 20 roadmap still lists infrastructure enhancements for this load.
  These are background evidence, not a confirmed September 9 incident bulletin.
- The official linked status page could not provide live status data through the
  browser tool. Third-party checker pages gave conflicting or stale results and
  were not used to establish a global outage.
- Direct bounded HEAD requests to the Zenodo homepage and an unrelated public
  record (22306521) both timed out after 12 seconds with no response bytes. This
  extends the earlier AbMPNN/API symptoms beyond that checkpoint, from this network.
- Germinal contains a converted `.pkl` checkpoint, which is not a drop-in `.pt`
  source for Studio. Mosaic contains a `.pt` copy and explicitly documents that
  it was re-serialized from Zenodo record 8164693.
- Mosaic's file downloaded successfully: **20,060,943 bytes**. It has SHA-256
  `5dca8d551747cffee33ee319724a47cd2e9d9b45132de13d84b511e3381aa125`.
  The verified original has SHA-256
  `fd41b40ee0f51974d73e1acb754cd8acaa36b3327543d5d28bcf4aa4e07b4a1b`.
- **472 stored tensors compared exactly, with zero differences**, including
  matching dtype/shape. All recursively compared checkpoint metadata matched.
  Top-level keys: epoch, step, num_edges, noise_level, model_state_dict and
  optimizer_state_dict. The files are not byte-identical, despite equivalent
  tensor and metadata contents.

## Decision and rationale

There is a practical verified alternate source. Recommend an explicit, immutable
Mosaic fallback with its own accepted SHA-256 and recorded source provenance.
Do not merely change the URL while retaining the original digest: the current
installer would reject the re-serialized file. Receipts and cached-artifact
validation must recognize the actual accepted variant if a fallback is implemented.
Zenodo remains the primary publisher. This audit does not change the installer,
disable verification, install the alternate weights or publish model binaries.

## Sources and reproduction

- https://blog.zenodo.org/2026/01/28/2026-01-28-improvements-and-support-expectations/
- https://about.zenodo.org/roadmap/
- https://about.zenodo.org/principles/
- https://stats.uptimerobot.com/vlYOVuWgM
- https://github.com/escalante-bio/mosaic/blob/70fec525423f5f87156a1a957b4a4048f9f8e676/src/mosaic/proteinmpnn/NOTICE
- Immutable download URL and both SHA-256 values are in the JSON verification record.

For equivalence, verify the original file's SHA-256 first; load both files with
CPU-only `weights_only=True`, recursively check metadata, and use `torch.equal`
with explicit dtype/shape equality for every tensor. Do not unpickle either
checkpoint with unrestricted loading.

## Limits and what was not tested

No confirmation of a global current outage, official incident declaration,
alternate network test or test on the affected user's Mac. No whole-installation,
inference, downloader failover or receipt migration test: those would accompany
an implementation. No application code changed and no build was rerun for this
research-only follow-up. No weights are committed or redistributed.

## Next

Implement and test explicit variant-aware download fallback if requested, including
safe partial-file handling, receipts and cached-checkpoint reuse. Separately,
making AbMPNN independently installable would prevent an optional designer's host
outage from blocking unrelated engines; that would be a product/defaults change.
