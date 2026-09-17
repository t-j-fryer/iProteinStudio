---
entry: 0140
title: Replace an ordinary sampling parent with the noising branch
date: 2026-09-17
author: Codex
type: bugfix
status: complete
machine: Apple Silicon development host; software checks only
tags: [nise, biotin, sampling, ui]
---

## Context

The user corrected [0139](0139-review-biotin-noising-plan.md): partial noising must
replace an ordinary beam member, rather than sampling all three ordinary parents
and adding the branch. They clarified that exposing free biotin's terminal region
is the objective; exact conjugation chemistry is not required for this campaign.

## What was done

Changed cycle-2-onward ordinary sampling to the best `beam - noise_advance` current
parents, ranked by score then name. The full beam remains available to choose the
best masking parent. Candidate origin does not prevent a high-scoring repaired
winner from becoming a subsequent ordinary sampling parent. Saved proposal
receipts now identify the actual ordinary parents and their limit.

Updated Python and Swift budgets, native UI explanation and total-advancement
label, MCP guide/schema wording, upstream adaptation note and NISE documentation.
Added executable assertions across both initial generators, with/without NESSO,
for exact ordinary sampling counts, parent identities, successful repaired-parent
promotion, lower-score reserved winners and zero-new-work interruption replay.

Regenerated the draft free-biotin request and atom audit in
`artifacts/0140-biotin-beam-correction/`. Original 0139 artifacts remain historical;
the [new report](artifacts/0140-biotin-beam-correction/REPORT.md) supersedes its
chemistry prerequisite and budget. No job or immutable execution plan was created.

## Results

No inference or performance measurements. New later-cycle ceiling per trajectory:
64 ordinary + 32 masked + 32 repair = 128 structure predictions. First cycle stays
64. Eight trajectories and 30 cycles give 30,208 optimisation predictions and
55,208 including initial stages; these are arithmetic maxima. Free-biotin atom
map matches the previous saved run exactly.

Software validation: 41 NISE tests, Swift request-contract harness and Swift build
pass; logs are in the artifact directory. An initial new assertion used `tid`
instead of the checkpoint's `trajectory` key; corrected before the passing run.

## Decision and rationale

Keep `beam=3` as the combined number advanced, with two ordinary places and one
reserved repair. Setting the existing serialized total to two would instead
leave only one ordinary place. Explain the split in the UI and documentation.
Keep the unchanged ordinary beam-three behavior when noising is disabled.

Use the original free biotin and terminal exposure criteria as requested. This
tests head-binding/tail-accessibility; do not claim that water accessibility proves
steric compatibility with every linker or attached protein.

## Reproduce

```bash
cd /Users/thomasfryer/iProteinStudio
NANOHUNTER_ROOT=/Users/thomasfryer/.iproteinstudio \
  /Users/thomasfryer/.iproteinstudio/venvs/NanoHunter_boltz/bin/python \
  -m unittest discover -s Tests -p 'test_nise*.py'
CLANG_MODULE_CACHE_PATH=/private/tmp/iproteinstudio-modules \
  SWIFTPM_MODULECACHE_OVERRIDE=/private/tmp/iproteinstudio-modules \
  swift build --disable-sandbox --skip-update
CLANG_MODULE_CACHE_PATH=/private/tmp/iproteinstudio-modules swiftc \
  -module-cache-path /private/tmp/iproteinstudio-modules -parse-as-library \
  Sources/iProteinStudio/Models/NISERequest.swift \
  Sources/iProteinStudio/Models/WorkspaceOrganization.swift \
  Sources/iProteinStudio/Models/Project.swift Tests/NISERequestContractHarness.swift \
  -o /tmp/iproteinstudio-nise-beam-contract
/tmp/iproteinstudio-nise-beam-contract
/Users/thomasfryer/.iproteinstudio/venvs/NanoHunter_boltz/bin/python \
  lab_book/artifacts/0140-biotin-beam-correction/audit.py \
  --old-run /Users/thomasfryer/.iproteinstudio/projects/test2/nise_runs/nise-C9CCE180-9E41-4BA3-95AE-CB03FBB867FA \
  --output lab_book/artifacts/0140-biotin-beam-correction
```

## Limits and what was not tested

No real-model noising pilot, chemistry ensemble, experimental affinity, model
timing or memory measurements. No interactive GUI testing, installed-app/DMG
replacement, campaign launch, commit or push. Previously frozen runs retain
their own script snapshots. No scientific benefit is inferred from fixture tests.

## Next

Review the revised settings and perform the governed pilot reaching cycle 2 before
launching the large campaign. Exact linker identity is not a blocking requirement.
