---
entry: 0153
title: Audit student VHH budgets and disappearing dashboard results
date: 2026-09-18
author: GPT-6 Codex
type: audit
status: complete
machine: Local archive audit on Apple M4 Max; student hardware not established
tags: [nanobody, budgets, results, ui]
---

## Context

The student reported requesting 100 trajectories per framework, receiving 60
outputs, empty artifacts, and results disappearing as each framework started.
Read-only source archive: `/Users/thomasfryer/Downloads/VHHs`. Compared saved
manifests, CLI arguments, output cardinality receipts, batch completion hashes,
and the current repository's native controls/history/dashboard. No inference,
scientific parameter changes, or modification of the student archive.

## What was done

Inspected both engine batches and all sixteen child manifests. Independently
verified every file hash in the completed batch's checkpoint receipt: 756 files
match; no missing or changed files. Compared current allocation logic in
`Models/DesignRequest.swift`, numeric control in `Views/RunUXComponents.swift`,
launch and active-child routing in `Core/RunController.swift`, metrics reset in
`Core/MetricsWatcher.swift`, and durable history / Activity View.

[Machine-readable audit](artifacts/0153-vhh-student-audit/audit.json).

## Results

Completed batch `09fec81c-4dde-4203-9287-2cd297a6623b` records
`trajectoriesPerEngine=12`, five optimized cycles and eight scaffold allocations:
`[2,2,2,2,1,1,1,1]`. Vobarilizumab, Caplacizumab, Gefurulimab and ALB8 received two;
Gontivimab, Isecarosmab, Sonelokimab and 3EAK received one. The child requests,
saved form states, requestedTrajectories and cardinality receipts agree.
All eight children are complete with no missing expected checkpoints:
12 independent trajectories, 60 optimized cycle outputs, and 12 cycle00 starts
(72 design-stage structures including initialization). These are not 60
independent trajectories and do not establish 60 validated binders.

Earlier batch `b4eca8fe-54e9-49ba-840b-25e89afc3acf` saved the same allocation.
Its first child is marked stopped, with setup/MSA directories but no completed
design cycle; seven subsequent children contain prepared inputs/manifests, no
completed outputs. All child inputs are intentionally prepared before submission.
Their raw manifests say running because that is the prepared manifest's default;
this is not evidence those later children executed. No parent completion receipt
or useful diagnostic log for the earlier stop is included. Do not invent a crash
or network-error explanation.

Four zero-byte files exist: three empty Protenix task lists and the earlier
attempt's empty target setup log. Empty task lists are consistent with saved
final-cycle-only, hits-only validation: an earlier-cycle hit does not queue the
final cycle. Empty hit folders / native MSA, packed and template directories can
be normal optional outputs. The completed batch's authoritative artifact hashes
all verify; no missing design output was detected.

## Decision and rationale

**Already handled:** pipeline cardinality enforcement predates this archive
(commit acbd3a2, 2026-08-31), and its receipts are present and passing. Durable
run history and per-child View actions already exist; completed output is not
being deleted. Multi-scaffold allocation was added in 14097e3 (2026-09-09).

**Still present:** the live dashboard follows only the current child. Controller
`receive` changes campaignRoot when active_output changes; AppState restarts
MetricsWatcher, which clears displayed points for the new root. Browse Results
also uses this single root. There is no combined framework-batch results view.
Use Activity / workspace Run history -> View to revisit an earlier child on its
original machine. A unified batch browser needs framework-aware identifiers;
run_001 in different frameworks must not collide.

**Budget discrepancy not fully reconstructable:** current default total is 12,
which matches the submitted batch exactly. Equal splitting divides a total per
engine across frameworks; it does not interpret the number as per-framework.
There is no saved 100-per-framework request in this archive. Current numeric
fields retain a separate draft, committed only on Return/focus loss; the Start
button snapshots the current request without explicitly committing the editor.
An uncommitted draft is a plausible UI failure mode, not a reproduced explanation
of this student's interaction. An old workspace / unsaved edit also cannot be
excluded. Archive pipeline provenance does not establish the installed app build.
Do not promise that merely installing the latest build fixes this discrepancy.

## Reproduce

Read both `engine-batch-*/studio_engine_batch.json` descriptors and each child
`studio_run.json` / `design_cardinality_receipt.json`. Sum actual trajectory,
optimized-design and total-checkpoint counts. For every entry in the completed
batch's `engine_batch_progress.json` -> completed, map the original campaign path
by basename into the archive, hash each relative file with SHA256 and compare.
The saved audit lists each receipt and verification totals.

## Limits and what was not tested

No live GUI reproduction of typing 100 and clicking Start, no exact student app
binary/build, no original broker failure log for the first attempt, and no model
inference or biological quality analysis. No app code changed, rebuilt, installed,
committed or published. Current running biotin campaign was not touched.

## Next

1. Ensure valid numeric edits reach the request before Start/Queue, with a GUI
   regression for typing without Return. Invalid drafts should prevent submission.
2. Present explicit total-versus-per-framework entry and a clear launch summary of
   framework count, per-framework trajectories, total trajectories and cycle outputs.
   Under existing semantics, eight frameworks at 100 each is total 800, or custom
   budgets of 100 each; five cycles means 4000 optimized cycle outputs plus 800 starts.
3. Add a batch-level dashboard/results browser with framework filters, durable
   history and separate independent-trajectory versus cycle-output counts.
4. Label children not yet started and explain skipped optional post-check outputs.
