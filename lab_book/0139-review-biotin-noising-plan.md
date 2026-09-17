---
entry: 0139
title: Review biotin attachment atoms and partial-noising campaign scale
date: 2026-09-17
author: Codex
type: audit
status: complete
machine: Apple Silicon development host; CPU chemistry audit only
tags: [nise, biotin, atom-mapping, planning]
---

## Context

Following [0137](0137-nise-fixed-budgets-and-partial-noising.md), the user requested
a repeat biotin campaign with partial noising, first checking the prior atom
criteria for protein-linked biotin and confirming settings and scale.

## What was done

Read the required MCP workflow guide, installed-engine detection, project/run
listing and completed-run overview. Compared current source guidance with the
older installed bridge. Audited the completed test2 Protein Hunter/Boltz request,
regenerated its ligand atom map and verified exact signature agreement. Checked
the selected chemical subgraphs and isolated exposure feasibility with RDKit.
Prepared labelled SVG diagrams and a normalized policy-v3 draft; requested the
missing attachment chemistry. Saved artifacts and a detailed
[report](artifacts/0139-biotin-noising-plan/REPORT.md).

## Results

No model inference or performance measurements. The nine Bind atoms cover the
fused-ring head plus its carbonyl oxygen; four Expose atoms cover the terminal
acid and adjacent methylene. A direct lysine amide replaces the old acid hydroxyl;
its original label cannot be reused for that product. An illustrative methylamide
cap is explicitly unapproved and does not represent the attached protein.

Arithmetic budget for 1,000 starts / 8 trajectories / beam 3 / 64 first-cycle
proposals / 32 later proposals per parent / 30 cycles, with 32 masked and 32 repair
proposals from cycle 2: initial maximum 25,000 structure predictions, optimisation
maximum 37,632, total 62,632. Patience four, geometry gates and selection reduce
actual work. No ETA is inferred. The saved source-queue snapshot had no active
jobs among the 100 returned entries; this is not a guarantee about other processes.

## Decision and rationale

The previous atom regions support the intended head-binding/tail-exit hypothesis.
Final atom selection must follow the actual conjugate chemistry. A water-accessible
tail cannot establish steric clearance for an attached protein. Keep the historical
6 Å contact / 50% per-atom retained accessibility criteria in the review draft,
pending attachment confirmation; do not silently substitute a capped ligand.

The requested noising branch remains experimental. Plan a bounded end-to-end
pilot reaching cycle 2 before the full campaign, through the governed bridge.
The draft JSON is labelled as using the original free ligand and is not an
approved execution plan. No jobs or immutable plans were created.

## Reproduce

```bash
cd /Users/thomasfryer/iProteinStudio
/Users/thomasfryer/.iproteinstudio/venvs/NanoHunter_boltz/bin/python \
  lab_book/artifacts/0139-biotin-noising-plan/audit.py \
  --old-run /Users/thomasfryer/.iproteinstudio/projects/test2/nise_runs/nise-C9CCE180-9E41-4BA3-95AE-CB03FBB867FA \
  --output lab_book/artifacts/0139-biotin-noising-plan
```

## Limits and what was not tested

No protein-conjugate structure, linker ensemble, experimental binding, Boltz/NESSO
inference, noising efficacy, timing, or memory benchmark. Isolated SASA feasibility
uses one generated conformer. No app/DMG update, commit, push, queue change or
campaign launch. No shipped implementation changed; Swift build was not repeated
for this documentation/audit-only work. Actual attachment remains unconfirmed.

## Next

Resolve the attachment chemistry and final ligand representation with the user;
review its remapped atoms and budgets, then perform the required pilot before
launching a large campaign.
