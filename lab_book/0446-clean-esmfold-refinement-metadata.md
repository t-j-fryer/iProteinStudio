---
entry: 0446
title: Remove generation metadata from ESMFold2 refinement inputs
date: 2026-10-16
author: Codex
type: bugfix
status: complete
tags: [rfd3, esmfold2, epitope, handoff]
---

## Context

After the automatic MSA fix, a second-Mac report identified an empty nanohunter mapping rejected by ESMFold2. The reported cause was independently reproduced against the actual handoff writer and ESMFold2 parser. Version0.2.25 includes this defect.

## What was done

The handoff now removes empty generation metadata after disabling epitope guidance. For ESMFold2 Fast/Full it removes the whole Studio nanohunter metadata block from the refinement copy, including nonempty residual Protenix options that would otherwise still fail. Original generation inputs remain byte-identical. Boltz/Protenix Constraint retain enabled epitope metadata. ESMFold2's strict parser remains unchanged; it does not pretend to support epitope guidance.

Updated the old test that expected the empty mapping to survive. New cross-boundary tests exercise actual ESMFold2 parsing for both models, three metadata aliases, empty/hotspot-only/hotspot-plus-distance mappings (18 combinations). Added enabled/disabled guidance coverage through the existing stage matrix and a test removing emptied metadata for both supported refiners.

## Results

Before correction: 18 ESMFold2 parser errors and one empty-metadata assertion failure. After correction:23 Hunter tests and8 ESMFold2 adapter tests passed. No performance measurements.

## Reproduce

```bash
/Users/thomasfryer/.iproteinstudio/venvs/NanoHunter_protenix/bin/python -m unittest discover -s Tests -p 'test_hunter*.py'
/Users/thomasfryer/.iproteinstudio/venvs/NanoHunter_protenix/bin/python -m unittest discover -s Tests -p test_esmfold2_adapter.py
```

## Decision and rationale

Keep backend input normalization at the stage handoff; do not teach ESMFold2 to ignore arbitrary unsupported fields, remove hotspots from the original generation input, or edit accepted job snapshots. Removing only an empty block is insufficient when Protenix-specific metadata remains.

## Limits and what was not tested

No other-Mac logs inspected. No learned-model inference, server MSA request or full RFD3 campaign performed. Tests use complete amino-acid sequences and explicit empty alignments; existing full-MSA path-preservation tests also pass. Scientific prediction behavior and runtime settings are unchanged.

## Release

Follow-up app/MCP/CLI release validation and deployment recorded below.

Curated release tree: Swift release build passed;23 Hunter tests and8 ESMFold2 adapter tests passed. Version0.2.26/build72, MCP44/bridge1.17.2. No changes to model weights or active job snapshots.

## Publication and deployment

Published v0.2.26-beta/build72 from256d92e; GitHub main and the signed update feed are updated. All four published assets match local SHA256 and byte counts. Packaged-resource and deep code-signature checks passed. This retains the existing ad-hoc beta/Sparkle EdDSA channel and is not Apple notarized.

Installed and opened /Applications/iProteinStudio.app. The staged initialization helper, runner, MCP version/module, CLI and pipeline version are byte-identical to the release bundle. Doctor passes with MCP44/bridge1.17.2. Existing model installations were reused.

Briefly stopped managed benchmark job159313e82b33 through Studio to release the resource-staging lock, then submitted resume of its same original plan. Completed checkpoints and frozen scientific code/settings were preserved. No inference tests were added to the GPU queue. Other Macs need the release installed and MCP reconnected; failed old snapshots need a newly prepared plan.
