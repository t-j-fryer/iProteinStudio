---
entry: 0041
title: Exclude the unoptimized seed from iterative re-checks
date: 2026-08-27
author: GPT-5.6
type: bugfix
status: complete
machine: Apple M4 Max, 40-core GPU, 64 GB unified memory, macOS 26.x
tags: [iterative-design, post-prediction, ui, command-contract]
---

## Context

Iterative campaigns write an initial `cycle_00` prediction before any sequence
optimization. Studio's “All cycles” independent-check option nevertheless emitted
`--post-include-cycle00`, so it spent checker compute on that unoptimized seed and
described the scope as cycles 00 through N.

## What was done

- Removed Studio's `--post-include-cycle00` emission from both hit-gated and
  ungated all-cycle post-prediction commands.
- Renamed the GUI option to “All design cycles (01–N)” and stated explicitly that
  the unoptimized seed is excluded.
- Corrected the prediction-time estimate to count N optimized checkpoints rather
  than N+1 checkpoints.
- Added command-contract assertions for both all-cycle modes.

The lower-level CLI flag remains available as an explicit diagnostic opt-in; it is
not part of a Studio-generated campaign.

## Results

No performance measurements — implementation only.

| Condition | n | Metric | Value |
|---|---:|---|---:|
| Studio all-cycle command contract | 2 modes | cycle 00 inclusion | 0 |

## Decision and rationale

“All cycles” in a design interface should mean all sequence-optimized design
cycles. Cycle 00 is the starting seed rather than a product of the iterative
design process, so re-folding it adds cost without evaluating an optimization
checkpoint. Retaining the CLI opt-in preserves a useful debugging capability
without exposing it as routine GUI behaviour.

## Reproduce

```bash
cd /Users/thomasfryer/iProteinStudio
caffeinate -dimsu swiftc -parse-as-library \
  Sources/iProteinStudio/Models/ProteinSequenceInput.swift \
  Sources/iProteinStudio/Models/Predictor.swift \
  Sources/iProteinStudio/Models/DesignRequest.swift \
  Sources/iProteinStudio/Models/DesignPoint.swift \
  Sources/iProteinStudio/Core/ResumeContract.swift \
  Sources/iProteinStudio/Core/TemplateWriter.swift \
  Sources/iProteinStudio/Core/CommandBuilder.swift \
  Sources/iProteinStudio/Core/MetricsWatcher.swift \
  Tests/IterativeCommandContractHarness.swift \
  -o /private/tmp/iproteinstudio-iterative-contract
caffeinate -dimsu /private/tmp/iproteinstudio-iterative-contract
caffeinate -dimsu bash Tests/test_iterative_cli_contract.sh
caffeinate -dimsu swift build
```

## Limits and what was not tested

No GPU prediction was needed because this changes checkpoint selection before an
engine launches. The manual CLI-only `--post-include-cycle00` path remains covered
by the CLI selector contract and was not removed.

## Next

If seed-quality diagnostics become a user workflow, expose them as a separately
named advanced action rather than broadening “All design cycles”.
