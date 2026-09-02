---
entry: 0053
title: Make measured resident scheduling automatic
date: 2026-09-01
author: codex-gpt-5
type: implementation
status: complete
machine: Apple M4 Max, 40-core GPU, 64 GB unified memory, macOS 26.x
tags: [iterative-design, persistence, ui, boltz, intellifold, protenix]
---

## Context

Entry [[0046-implement-campaign-resident-predictors]] measured three iterative-
design schedulers in complete 12-trajectory, five-cycle, 80-aa SUMO campaigns.
Studio subsequently selected the winning engine-specific policy by default, but
still presented the slower historical route as an Advanced GUI setting. That
allowed an older saved form or an accidental click to restore process-per-
trajectory execution and repeat up to 72 model loads in the measured campaign.

## What was done

- Made scheduling a product policy in `CommandBuilder`: Boltz 2, IntelliFold
  v2-flash/full v2, Protenix Mini and Protenix Constraint use one campaign-
  resident worker; full Protenix v2 uses one directory process per cycle.
- Removed scheduling and obsolete parallel-process choices from Advanced. The
  main run summary now states the automatic policy before launch; Advanced
  retains only explanatory text and recovery controls.
- Migrated decoded `standard` values from old project JSON to the optimized
  value. Command construction also ignores a legacy in-memory value, so the
  invariant does not depend on migration alone.
- Made time/speed presentation use the automatic policy rather than a dormant
  stored preference.
- Retained `SpeedMode.standard` only for backward-compatible decoding and kept
  the runner's explicit `--design-scheduler run` route for controlled CLI
  diagnostics.
- Documented that Resume executes the command recorded for an existing
  campaign; it does not rewrite historical provenance when the app policy
  changes.

## Results

No new performance measurements were made. The policy is based on the completed
M4 Max benchmark in entry 0046: resident was fastest for five supported design
engines, while cycle-wave was fastest for full Protenix v2.

| Condition | n | Metric | Value |
|---|---:|---|---:|
| Swift iterative command contract | 1 executable suite | status | passed |
| Iterative shell/CLI contract | 1 suite | status | passed |
| Iterative GUI source contract | 1 suite | status | passed |
| Swift package build | 1 build | status | passed |
| Release app assembly and ad-hoc signature validation | 1 bundle | status | passed |

The command contract explicitly encoded and decoded an old `standard` request,
confirmed migration to `batched`, and confirmed a resident launch. It also
confirmed that even an unmigrated in-memory legacy value cannot bypass full
Protenix v2's cycle-wave policy.

## Decision and rationale

Predictor lifetime is not a scientific parameter. Studio therefore chooses the
fastest measured reliable implementation automatically instead of asking a
bench scientist to understand process lifetime, directory waves or MPS model-
load overhead. Full Protenix v2 remains the deliberate exception: its resident
campaign was slower than its cycle-wave campaign, so describing every engine as
resident would be both slower and inaccurate.

The historical per-trajectory runner was not deleted. It remains useful for
controlled implementation comparisons and fault diagnosis, but is now an
explicit CLI choice rather than a routine GUI campaign option. Existing run
manifests remain immutable so Resume does not silently change a campaign midway.

## Reproduce

```bash
cd /Users/thomasfryer/iProteinStudio

/usr/bin/caffeinate -dimsu swiftc -parse-as-library \
  Sources/iProteinStudio/Models/ProteinSequenceInput.swift \
  Sources/iProteinStudio/Models/Predictor.swift \
  Sources/iProteinStudio/Models/DesignRequest.swift \
  Sources/iProteinStudio/Models/DesignPoint.swift \
  Sources/iProteinStudio/Core/ResumeContract.swift \
  Sources/iProteinStudio/Core/TemplateWriter.swift \
  Sources/iProteinStudio/Core/CommandBuilder.swift \
  Sources/iProteinStudio/Core/MetricsWatcher.swift \
  Tests/IterativeCommandContractHarness.swift \
  -o /private/tmp/iproteinstudio-iterative-contract-default-resident
/usr/bin/caffeinate -dimsu \
  /private/tmp/iproteinstudio-iterative-contract-default-resident
/usr/bin/caffeinate -dimsu bash Tests/test_iterative_cli_contract.sh
/usr/bin/caffeinate -dimsu bash Tests/test_iterative_results_ui_contract.sh
/usr/bin/caffeinate -dimsu swift build
/usr/bin/caffeinate -dimsu ./build_app.sh
```

## Limits and what was not tested

No new GPU campaign was launched because this change promotes the already
completed paired benchmark rather than altering the resident worker or engine
inference code. The evidence remains limited to the M4 Max, SUMO, fixed 80-aa
binder, 12-trajectory/five-cycle setting recorded in entry 0046. The UI wording
compiled and has a source contract, but this pass did not perform a manual click
through on every supported macOS window size.

## Next

Keep scheduling automatic. Re-benchmark the policy only when an engine version,
checkpoint, MPS runtime or materially different hardware changes; record that
measurement before changing the mapping.
