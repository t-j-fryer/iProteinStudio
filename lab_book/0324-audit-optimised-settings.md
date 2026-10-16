---
entry: 0324
title: Audit optimised settings across app and workflow entry points
date: 2026-10-06
author: Codex
type: audit
status: complete
machine: Apple M4 Max, 40-core GPU, 64 GB unified memory, macOS 26.x
tags: [predictors, defaults, mcp, cli, tests, ui]
---

## Context and scope

The user requested a general audit of the app and related interfaces for current
optimised settings, stale defaults and bugs. Reviewed GUI requests/controllers,
shared prediction profiles, native/MCP preflight, direct CLI adapters, resident
workers, NISE, RFdiffusion3 generation/verification and optional ligand screening.
The installed app and runtime were read, not modified. Existing campaigns and
accepted immutable plans were not changed.

## Confirmed profiles

Source, installed app and installed runtime have identical parsed profile tables.
Exact paths, hashes and values: `artifacts/0324-optimised-settings-audit/profile-inventory.json`.

| Engine | Supplied MSA cap | Recycles/loops | Diffusion steps |
|---|---:|---:|---:|
| Boltz | 128 | 3 | 25 |
| IntelliFold Flash/full | 128 | 10 | 25 |
| Protenix v2/Constraint | 128 | 10 | 25 |
| Protenix Mini | 128 | 4 | 5 |
| OpenFold3 | 128 | 3 | 25 |
| ESMFold2 Full | 128 | 3 | 50 requested |
| ESMFold2 Fast | no MSA | 3 | 50 requested |

These are the previously promoted scientific profiles, not new performance
measurements. Sample counts, affinity, conditioning and RFdiffusion3's 200-step /
2-recycle generation profile remain separate. Explicit overrides remain valid.
Historical benchmark scripts using 200 steps were not rewritten to new science.

## Findings and fixes

1. **Optional ligand-screening verification lost profile overrides.** The
   separately launched NESSO/PSICHIC shortlist verification had no frozen
   prediction-settings field. Depending on its parent process it could inherit
   different settings or fall back to defaults. Native Protein Hunter/RFD3 and
   MCP preparation now pass and normalize the parent profile, include it in the
   immutable config/preparation identity and pass it explicitly to the folding
   subprocess. Historical configs without the field retain their old inherited
   behavior; existing campaign files were not migrated. Resume rejects changed
   new configs. Tests cover frozen overrides, environment isolation, changed
   resume settings, native handoff and prepared config defaults.
2. **MCP Protein Hunter omitted explicit defaults when overrides were absent.**
   New plans now resolve and record `--prediction-settings-json`, preventing a
   later worker from inheriting an unrelated launch-process profile. Existing
   accepted plans are unchanged. GUI already supplied the flag.
3. **Predict ignored explicit zero recycles.** The legacy top-level override used
   a truthiness check; zero was treated as absent. It now distinguishes `None`
   from zero. A command-generation test covers absent, zero and positive values.
4. **Stale app summaries.** Protenix v2/Constraint descriptions still advertised
   200 steps; OpenFold claimed two processes; Boltz claimed extra workers never
   help. Updated the summaries to current profiles and workflow-specific model
   reuse, without claiming universal concurrency performance. MSA summaries now
   acknowledge capping; forced pocket guidance is no longer described as always
   off on the ordinary Boltz entry.
5. **Test coverage/environment friction.** Added the existing OpenFold resident
   receipt/resume suite to the main science suite. Added optional
   `--biotite-python` for the six declared Biotite-dependent fixtures, allowing
   existing Protenix and Boltz environments to be used without altering either.
   Updated `docs/TESTING.md` and `docs/PREDICTION_PROFILES.md`.

## Scheduling audit and remaining opportunity

- Protein Hunter uses one resident model for supported normal cycles, full
  Protenix v2 cycle waves, and the existing per-trajectory scheduler for native
  partial/motif modes. Separate initialization releases the starting model before
  refinement. These exceptions are intentional, not evidence of bypassed profiles.
- NISE defaults to one resident worker, supports the validated two-worker Boltz
  pool explicitly, and activates saved profiles before constructing workers.
  Selective affinity and automatic CPU geometry scheduling remain in place.
- RFD3 generation settings remain independent from verification profiles. Shared
  verification adapters retain their existing resident/cycle-wave dispatch.
- **Predict throughput follow-up:** Boltz/Protenix use finite directory chunks;
  IntelliFold retains its separately measured multiprocess/batch schedule.
  OpenFold/ESMFold use one directory worker. These paths apply current scientific
  profiles but do not all have campaign-long residency. A paired benchmark of
  larger chunks or persistent cross-chunk sessions would establish whether a
  change helps current workloads and smaller-memory Macs. No unmeasured schedule
  was promoted in this audit.

## Validation

- Initial all-suite run: 78/83 commands passed; five failures were missing Biotite
  in the selected Boltz test environment. All five passed using existing Protenix
  Python. No package installation was required.
- Final expanded all-suite run with two declared interpreters: 83/84 commands
  passed. The sole failure was the native screening test's old mocked call
  signature; it did not yet expect `prediction_settings`. Updated that test to
  supply and assert a custom profile, then reran the complete desktop suite:
  **25 tests passed**. Thus each of the 84 commands has a passing final result,
  with that one command verified in a separate rerun rather than concealing the
  initial failure.
- One optional actual Accelerate CPU loader test was skipped by its existing
  dependency gate. Other synthetic loader/ownership/resume contracts ran.
- Focused profiles: 10 passed. Screening: 15 passed. MCP bridge: 24 passed.
- `swift build` and `git diff --check` passed. Swift test and standalone Swift
  contracts ran within the full suite.

Logs: `lab_book/artifacts/0324-optimised-settings-audit/`.

## Reproduce

```bash
python3 Tests/run.py --suite all \
  --science-python "$HOME/.iproteinstudio/venvs/NanoHunter_boltz/bin/python" \
  --biotite-python "$HOME/.iproteinstudio/venvs/NanoHunter_protenix/bin/python"
python3 Tests/test_desktop_jobs.py
swift build
```

## Limits and deployment

No real-model GPU campaign, speed benchmark, live-network acceptance, interactive
GUI/VoiceOver or packaged-app/Gatekeeper/Sparkle acceptance was run. No claim that
all possible errors have been ruled out. Existing unrelated checkout edits were
preserved. These fixes are in source and the local build; the installed app,
managed runtime, GitHub and releases were not replaced by this audit.
