---
entry: 0143
title: Start the biotin acceptance pilot and update Studio distribution
date: 2026-09-17
author: Codex
type: implementation
status: in-progress
machine: Apple M4 Max, 64 GB unified memory
tags: [nise, biotin, release, mcp]
---

## Context

The user approved starting the campaign from [0142](0142-limit-biotin-exposure-to-terminal-oxygens.md)
and requested that the app, MCP and GitHub be brought up to date. Pending source
changes include the previously requested RFdiffusion3 audit fixes, OpenFold
scheduling correction and NISE search/noising work, all with prior Lab Book records.

## What was done

Called MCP workflow guidance and engine detection. Verified the empty managed
queue outside the filesystem sandbox (process visibility is required for correct
broker state). All required engines report runnable. Created a five-start pilot
with unchanged ligand/filter/scoring protocol and explicitly reduced sampling
counts, plus the unchanged full campaign request. Recorded the validation manifest
and Validation Lab Book entry 0027 before inference.

Created the immutable plan with source `studioctl.py plan-nise`, reviewed its
normalized request, budget and command, then used the run-profile `job_start`
with its exact digest. Saved the broker receipt for native app discovery.
Pilot plan `plan-8e5b6fae95094aa8`, job `job-8e5b6fae9509`, output
`test2/nise_runs/nise-3c9725ad1fee467f`; entered initial backbone generation.

Bumped app build to 38 and MCP version to 19, updated release notes, and started
the full software suite before preparing the release. Operational logs are under
`artifacts/0143-biotin-launch-and-update/`; ignored scientific receipts are under
`Validation/output/biotin_noising_acceptance_v1/`.

## Results

The software suite initially passed 45/51 commands in the Boltz environment.
Five science commands lacked Biotite (and the first alternate template check
lacked Gemmi); all five pass in the installed RFD3/Protenix environments. The
skipped surface-origin suite also passes in RFD3. Standalone Swift contracts and
`swift build` pass. `swift test` cannot run because Command Line Tools lack XCTest;
no full Xcode installation is present. This is recorded rather than counted as a pass.
The continuation guard's negative/positive fixture passes.

The first packaging attempt correctly stopped at its hard-coded MCP-18 assertion
after building the MCP-19 bundle. Updated the packaging contract to version 19,
added exact-source checks for the NISE policy/noising files, and reran it
successfully before retrying publication. No artifact from the failed attempt
was published.

The pilot passed two of five initial backbones and entered refinement. A planned
stop/resume for runtime deployment will preserve completed unit receipts. The
acceptance guard permits this one restart while still requiring a single resident
session across optimisation cycles 1 and 2. Full immutable plan
`plan-bfd005780c66a3ef` is prepared and reviewed, not started. A guarded continuation
will require completed pilot output audits and updated staged runtime before
submitting that exact plan; failures stop continuation without weakening settings.

Pilot ceiling 139 structure predictions; full campaign ceiling
55,208. These are budgets, not measured throughput or final-design counts.

## Decision and rationale

The user authorized the full campaign. A bounded pilot must exercise the new
noising branch before large execution, per repository instructions. A successful
exit without reaching complete cycle-2 repair is insufficient acceptance.
App/runtime updates must respect the execution lease; immutable job snapshots
preserve running science. Publish source and packaged app only after software
checks, without including model weights or raw validation jobs.

## Reproduce

```bash
NANOHUNTER_ROOT="$HOME/.iproteinstudio" /usr/bin/python3 \
  Sources/iProteinStudio/Resources/pipeline/mcp/studioctl.py plan-nise \
  Validation/experiments/biotin_noising_acceptance_v1/pilot_request.json
```

Use the returned exact ID/digest for `studioctl.py start`, then `job-status`.
The full software suite command is `Tests/run.py --suite all --science-python`
with the installed Boltz Python, as recorded in the test log.

## Limits and what was not tested

No partial-noising efficacy or speed claim. Full campaign has not yet started;
pilot acceptance, packaging/install and GitHub publication are pending at this
entry's creation. No model weights are committed or distributed.

## Next

Audit the pilot through the durable guarded continuation and submit the full
campaign only after acceptance. Any failure remains visible in its continuation
record and must be diagnosed before further execution.

## Deployment and continuation update

Packaged build 38 from clean source `0128830` (implementation commit `a8b9064`).
Ad-hoc signature/resource checks pass; the DMG verifies. Published the beta
app/DMG, provenance and checksum files at GitHub release `v0.2.0-beta`; Sparkle
archive signature and feed were published in `0c8a42d`. The app is open from
`build/iProteinStudio.app` (observed PID 69225). Installed MCP doctor reports
version 19, and the staged MCP guide/schema and NISE script bytes match source.
Existing live MCP connections can retain imported old guidance until reconnected;
fresh connections load v19. No client configuration was overwritten.

The pilot was stopped through the broker for staging and resumed after byte
verification. All five initial predictions were reused; refinement continued
with `L002_c1_1`, after the already completed `L002_c1_0`. Two of five starts passed
initial atom checks. Pilot remains running; the 1,000-start job is not yet submitted.

Detached guarded continuation PID 69460 monitors job `job-8e5b6fae9509` and holds
full plan `plan-bfd005780c66a3ef` for automatic submission through `job_start` only
after its strict output audit passes. It runs under caffeinate, saves its status
to `Validation/output/biotin_noising_acceptance_v1/continuation.json`, accepts a
STOP_CONTINUATION marker, and expires after 48 h. One planned maintenance restart
is allowed; optimisation must use a single resident session across both cycles.
No new permission is required for the already authorized full campaign.

Deployment logs and [receipt](artifacts/0143-biotin-launch-and-update/deployment.json)
record the release and pending scientific acceptance separately. This is not a
claim that the new scientific branch has already passed real-model acceptance.
