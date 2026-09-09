---
entry: 0087
title: Evaluate repository structure, usability, accessibility and reliability
date: 2026-09-04
author: gpt-6
type: audit
status: complete
machine: Apple M4 Max, 40-core GPU, 64 GB unified memory, macOS 26.x (existing project provenance)
tags: [architecture, accessibility, usability, reliability, testing]
---

## Context

The user asked whether the repository supports a user-friendly, accessible and
reliable product. This review follows entry 0086 and includes the existing
uncommitted secondary-structure implementation. The active scientific campaign
was not modified or used as a test fixture.

## What was done

Reviewed app routing, workspace persistence/deletion, campaign launch/recovery,
installation controls, results loading, native and embedded-web accessibility,
vendoring, documentation and test entry points. Ran selected existing executable
contracts using temporary fixtures. Only this record and the Lab Book index/status
were edited; recommendations below are not implemented fixes.

## Results

The top-level separation between `Sources`, `Tests`, `Validation`, `docs`,
`tools`, and `release` is sensible. Preserve it. Strong foundations include
typed requests, command builders, campaign-owned pipeline snapshots, immutable
MCP plans, transactional engine installs, explicit scientific caveats, grouped
result provenance and an unusually useful evidence history.

The main weaknesses are inconsistent ownership across GUI/runtime boundaries,
silent persistence failures, incomplete accessibility semantics, and a test
suite that requires knowledge of individual scripts and installed environments.
There were no performance measurements or real-model quality measurements in
this review. Source findings below are not claimed as live GUI reproductions.

### 1. High priority: protect saved work and fail visibly on persistence errors

`State/AppState.swift:98–106` writes `config.json` without `.atomic`, suppresses
write errors, and silently returns an empty project list when decoding fails.
Because every form edit calls `save()`, an interrupted write can make saved
workspaces disappear from the interface; a subsequent save can replace the
unreadable index. This does not itself establish deletion of output directories.

`Core/RunController.swift:76–88,200–202` starts the process even if the supposedly
durable `studio_run.json` failed to encode/write. Atomic writing is present for
that manifest, but its error is discarded. Log failures are also ignored.

`State/AppState.swift:76–82` removes the project from memory first, permanently
removes its output directory, suppresses filesystem errors and saves afterward.
`Views/Projects/ProjectSidebar.swift:121–140` asks for deletion confirmation but
does not block deletion of an active workspace. A running process can therefore
lose its inputs/checkpoints; a failed deletion can leave results orphaned from
the workspace list.

Recommended boundary: a throwing workspace store with atomic writes, a recoverable
previous index and explicit corruption handling. Persist and verify the launch
manifest before spawning work. Block deletion while any job owns that workspace;
offer archive/Trash where appropriate and remove the index entry only after the
filesystem operation succeeds. Do not silently initialize over damaged state.

Acceptance: inject write failures and malformed JSON; the previous index remains
recoverable and no job starts without its record. Attempt deletion while a fake
GUI or MCP job is active; the directory and index must remain intact.

### 2. High priority: one durable lifecycle for GUI and MCP jobs

`Core/RunController.swift:188–197` launches directly through `ProcessRunner`.
The broker separately owns `agent/execution.lock` in
`Resources/pipeline/mcp/iprotein_mcp/broker.py`. `docs/CLI.md:97–101` explicitly
documents that GUI launches do not acquire that lock. Native Start guards and
`ActivityCenterView.hasLiveActivity` only consult in-memory GUI controllers.
Consequently an agent campaign and a GUI campaign can overlap even when both
interfaces separately claim to prevent concurrent GPU work.

History has another symptom of split ownership: `RunHistoryStore.swift:138–148`
classifies an incomplete iterative run as interrupted without checking its live
owner. The Activity view adds a separate live row but leaves the history row's
state unchanged. On restart the native iterative controller has no durable
reattachment equivalent to the RFdiffusion3 controller.

Route GUI launch/resume/cancel through a shared job service using the existing
broker's provenance and lock policy. Preserve recorded resident scheduling and
scientific defaults. Include queued, preparing, running, stopping and terminal
states; cancellation must retain resource ownership until process exit. Extend
runtime maintenance guards through the same ownership mechanism. Existing
installer busy-process checks are useful but are not a shared job lease.

Acceptance: an MCP job blocks/queues a GUI start and vice versa; app restart
rediscovers the job; Stop waits for descendants; Resume is unavailable for work
that is still alive. Verify with fake workers before inference acceptance.

### 3. High priority: keep displayed results attached to their workspace

`AppState` owns a single `run` and `metrics` instance. In
`Views/RootView.swift:239–240`, any selected workspace receives the global live
dashboard whenever that controller has a campaign root, without checking the
campaign's project ID. `LiveDashboardView.swift:28,104` takes its threshold and
heading from the currently selected project.

Code path: start iterative work in workspace A, select workspace B and open its
iterative tab. The view can combine A's run/metrics with B's name and threshold.
This affects overview hit counts; it does not establish that durable saved
verdicts or the grouped Hits browser are rewritten.

Give every run an immutable context containing workspace ID, launch request,
thresholds and output root. Route dashboards by that context. A different
workspace should show its own form/history and a link to the active run.

Acceptance: switch between two workspaces with different thresholds while a fake
run is active; run identity, header, counts and output destination remain correct.

### 4. High priority for accessibility acceptance: name interactive controls

Useful explicit labels and shortcuts already exist on primary navigation and
Start actions. Concrete remaining gaps:

- `Views/Onboarding/ComponentsView.swift:223–227` uses an empty-label checkbox;
  the engine name is separate sibling text.
- `Views/NewRun/DesignFormView.swift:494–500` places text beside a slider without
  supplying the slider's accessible label/value. Other temperature and threshold
  sliders use the same pattern.
- `Resources/web/py2dmol/viewer.html:228–240` contains unlabelled canvases, a
  symbol-only playback button and an unnamed frame slider. The adapter updates
  the visual frame counter without an explicit accessible cycle description.
- Main and results windows have large fixed minimum sizes, and the grouped
  browser enforces a 720-point detail pane. Layout at enlarged display settings
  and text sizes needs actual acceptance; clipping was not measured here.

Use shared labelled controls, explicit values/units, meaningful web playback and
frame names, keyboard-operable viewer actions, and a textual result/structure
summary. Respect reduced-motion preferences and provide adaptable layouts. The
viewer already has a colourblind option; its existence alone is not a complete
accessibility audit.

Acceptance: complete setup selection, input, Start, Stop, Resume, result selection
and trajectory navigation using keyboard and VoiceOver. Check focus order,
announcements, zoomed displays, contrast and motion in the running application.
Source-string checks cannot establish these outcomes.

### 5. Medium priority: make validation and recovery messages consistent

Quick/Advanced setup, worked examples, constrained numeric controls, download
review and checkpoint Retry are useful product choices. Preserve them.

Iterative validation is split between `DesignRequest.isRunnable` and
`DesignFormView.missingReason` (lines 324–351). The latter can return an empty
string for invalid nonempty sequences or some invalid numeric values; it also
contains a literal `(r.designPredictor.label)` interpolation typo. Inline errors
cover some cases, but the Start area's explanation is not a complete contract.
`RunController.finish` generally exposes an exit code rather than a categorized
cause. RFdiffusion3/prediction already have structured validation patterns to reuse.

Return one typed list of validation issues with field destinations and recovery
actions, and derive both Start availability and its explanation from that list.
Give failed jobs a cause, preserved-checkpoint status and a specific next action.
Provide a previewable, sanitized diagnostics export so bench scientists do not
have to find and redact raw logs manually. Keep technical logs available.

Acceptance: every disabled Start has a useful explanation; malformed inputs link
to the relevant field; missing files, unavailable engines and failed stages have
distinct recovery actions without changing scientific settings automatically.

### 6. Medium priority: isolate filesystem loading from view updates

`Core/RunHistoryStore.swift:107–118` scans all project histories synchronously on
the main actor. `LiveGroupedRunResultsPane` loads in its initializer and calls
the synchronous loader every two seconds. `RunResultsView.refresh` similarly
reloads from disk. `Models/RunResult.swift` contains filesystem discovery and
parsing alongside value types. Larger campaigns therefore have a plausible UI
responsiveness risk; this review did not measure latency or observe a freeze.

Move result discovery to a dedicated service off the main actor. Cache by stable
file identity/modification information, coalesce refreshes, cancel obsolete
loads, retain the last valid snapshot during partial writes and publish small
updates to the UI. Measure representative large fixtures before selecting an
indexing scheme or claiming a speed improvement.

### 7. Medium priority: create one discoverable test entry point

`Package.swift` declares one executable and no test target. There is no checked-in
`.github/workflows` directory. Valuable tests exist, but their forms differ:
unittest classes, top-level Python assertions, `main()` scripts, compiled Swift
harnesses and shell source-string checks. Some UI contracts only search for
strings and cannot detect workspace identity or accessibility behaviour.

This review encountered both consequences: default Python lacked PyYAML for the
workflow suite, and `python3 -m unittest ... Tests/test_storage_policy.py` imported
the module without running its `main()` assertions. Running that script directly
executed the real test. The workflow suite passed with its documented managed
RFD3 Python. A green discovery command is therefore not necessarily full coverage.

Add a documented test runner that explicitly invokes every suite with declared
dependencies, reports skipped checks and separates fast contracts, GUI acceptance,
real-model inference and release acceptance. Move pure Swift logic into a library
with a standard test target incrementally. Add CI for deterministic checks; keep
hardware inference in the declared Validation system. Preserve existing useful
harnesses during migration.

### 8. Medium priority: clarify ownership of vendored and Studio-authored code

The current runner is 8,123 lines, `RunResult.swift` 1,259 and `DesignFormView.swift`
1,042 (working-tree counts). Size is a navigation signal, not proof of defects.
The substantive problem is mixed responsibility and uncertain update boundaries.

`tools/sync_pipeline.sh:35,65` copies the upstream runner over the local runner,
which also contains Studio-authored policy changes. The tracked PIPELINE_VERSION
hash does not match the current dirty working-tree runner. Run snapshots compute
their own provenance, so this observation does not invalidate existing jobs.
It does show why a provenance file and an overwrite script are insufficient for
maintaining the upstream/local boundary.

Record an explicit vendor manifest, upstream revision, local patch series or
overlay ownership, and applied hashes. Stage synchronization for review and run
contract checks before replacement. Avoid a wholesale runner rewrite during
scientific validation. Update ARCHITECTURE.md's narrow nanobody/3Dmol description
to cover the actual workflows, py2Dmol integration and job boundary.

## Decision and rationale

Recommend incremental consolidation, with data safety and job ownership first.
A mass folder rename would create review and provenance churn without fixing
these user-visible failure modes. Keep packaged resource locations stable until
their launch/distribution contracts are deliberately migrated.

Suggested logical boundaries, introduced as each area is changed:

| Boundary | Owns |
|---|---|
| Domain | Validated requests, immutable run context, result identity, verdicts |
| Workspaces | Atomic persistence, migration, recovery, archive/deletion |
| Jobs | Shared GUI/MCP lifecycle, queue/lock, cancellation, resume |
| Results | Discovery, parsers, indexing, grouping and incremental snapshots |
| Runtime | Assets, installer, engine health, update/provenance policy |
| UI components | Labelled inputs, validation presentation, error/recovery cards |
| Feature views | Setup, workspaces, design, prediction, RFdiffusion3, results |

The low-level scientific adapters remain upstream-derived. The app and MCP
should consume the same execution and result contracts instead of independently
reconstructing them. Folder placement alone cannot enforce this boundary.

## Reproduce

From the canonical checkout, these existing checks were executed:

```bash
python3 -m unittest Tests/test_secondary_structure_control.py Tests/test_design_cardinality.py Tests/test_storage_policy.py Tests/test_runtime_transaction.py
python3 Tests/test_storage_policy.py
bash Tests/test_iterative_results_ui_contract.sh
bash Tests/test_rfd3_results_ui_contract.sh
bash Tests/test_ai_integrations_ui_contract.sh
bash Tests/test_process_runner_cancellation.sh
/Users/thomasfryer/.iproteinstudio/rfd3/.venv/bin/python Tests/test_workflow_pipelines.py
swiftc -sdk /Library/Developer/CommandLineTools/SDKs/MacOSX15.4.sdk \
  -module-cache-path /tmp/iproteinstudio-review-module-cache \
  Tests/PredictionResultsContractHarness.swift \
  Sources/iProteinStudio/Models/RunResult.swift \
  -o /tmp/iproteinstudio-review-results-contract
/tmp/iproteinstudio-review-results-contract
```

Results: five secondary-prior unittest cases passed; the import-time cardinality
and runtime-transaction assertions passed; the separately executed storage
policy, workflow pipeline and Swift result-discovery contracts passed. All three
source-based UI contracts passed. These are fixtures, not measured model outputs.

The cancellation harness failed inside the workspace sandbox and passed when
rerun with approved escalation. Its two surviving temporary shell processes from
the sandbox attempt were identified by path/start time and stopped; unrelated
processes were left alone. Default `python3` could not run the workflow contract
because PyYAML was missing; the documented existing RFD3 environment succeeded.
No dependencies or model assets were installed or changed.

## Limits and what was not tested

This is a source/architecture review plus selected executable contracts, not a
complete GUI, accessibility, security, scientific or distribution audit. No
VoiceOver session, screenshot review, real-model inference, disk-full injection,
app crash/relaunch, GUI/MCP concurrency experiment, destructive project deletion,
large-campaign timing, M1 test, Gatekeeper/Sparkle acceptance or full Swift build
was performed. No commit was made. The source findings require dedicated
regression tests when fixed; passing existing contracts does not dismiss them.

## Next

1. Fix persistence/deletion and run-context ownership with failure-injection tests.
2. Unify job state/resource ownership across GUI and MCP, preserving provenance
   and resident scheduling; validate restart/cancellation with fake workers first.
3. Complete native/web accessibility and novice recovery flows with actual GUI
   acceptance, while adding a dependable fast test entry point.
4. Extract result loading and formalize vendor ownership incrementally; measure
   responsiveness before promoting performance changes.

Continue the already-submitted secondary-prior campaign independently, retaining
its scientific controls and immutable outputs.
