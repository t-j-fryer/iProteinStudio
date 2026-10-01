---
entry: 0253
title: Promote ESMFold2 Full 3/50 and update Figure 2
date: 2026-10-01
author: Codex
type: implementation
status: complete
machine: Apple M4 Max, 40-core GPU, 64 GB unified memory
tags: [esmfold2, defaults, manuscript, queue]
---

## Context

User explicitly chose Full 3 loops/50 requested diffusion steps as the new app
and Figure 2 default after reviewing the four-target, five-seed results in0251.
Also requested Protenix stopped while other benchmarks run.

## What was done

Stopped Protenix through Studio's cancellation contract; confirmed cancelled with
completed checkpoints retained. Terminated its dedicated continuation watcher
after checking process identity and recorded a manual hold in shared handoffs.
No benchmark resumes automatically.

Changed the shared prediction-profile JSON (Full MSA128/50steps/3loops), direct
adapter profile metadata, Swift labels, NISE explanation and MCP schema help.
Predict, Target Prep, Protein Hunter, RFdiffusion3 verification and NISE read the
same registry. Fast remains sequence-only3/50; Mini remains native5steps/4cycles.
Explicit overrides and immutable accepted jobs retain their requested settings.

Figure 2 imports20 audited follow-up outputs and substitutes them only for the
four Full app-default conditions. Original20/100 rows remain in source data;
baseline and matched-compute series are unchanged. Audits cover receipt hashes,
MSA shapes, actual steps/loops and warmup/resident identities. Updated manuscript
Results, Online Methods, figure plan, caption and builder instructions. Previous
publication assets are preserved under `artifacts/0253-esm-full-defaults`.

## Results

No new predictions. Performance/quality measurements are from0251, not new runs.
All20 Full3/50 outputs passed the recorded geometry checks, but MBP domain
placement varied. The manuscript explicitly retains that limitation and the
CPU compilation overlapping final dimer seeds. User preference promotes a
throughput default, not a claim of universal accuracy equivalence.

Eight profile tests and eight ESM adapter tests pass, including preservation of
explicit Full20/100 overrides and Fast isolation. Figure rebuilt from original
export plus follow-up and again from its self-contained source table:301 source
rows,265 plotted predictions,1,324 receipt files verified. PDF rendered at180
and600dpi; layout visually reviewed. The registered manuscript image synchronized.

## Decision and rationale

Apply the user's selected scientific defaults across shared app contexts rather
than changing only the plot. Retain historical raw labels and outputs for
reproducibility. The baseline and matched arms must not acquire reduced compute.
Package from an isolated checkout of released commit f6987ca plus these changes,
excluding unrelated ongoing edits in the main workspace.

## Reproduce

Run `Tests/test_prediction_profiles.py`, `Tests/test_esmfold2_adapter.py`, and
`manuscript/figures/figure2_v1/build_figure.py` (README lists environment flags).
Local build log and preserved assets are in `lab_book/artifacts/0253-esm-full-defaults`.

## Limits and what was not tested

No new ligand, binder, fresh-Mac or long memory-soak experiment. Numerical output
equivalence is not claimed across different compute budgets. No public GitHub
release is created by this task. Build/staging verification recorded below.

## Next

Keep Protenix held until the user requests resumption. Preserve the original
interrupted-session distinction when completing that benchmark later.

## Build and deployment verification

Isolated production `swift build` and app assembly passed; code signature verified.
The local app was replaced and reopened, with its previous bundle retained under
`build/app-backups`. Shared installed adapter, profile JSON, four MCP schemas and
pipeline version match source hashes. Installed Full defaults resolve to MSA128,
3loops/50steps; MCP normalization preserves an explicit20/100 override. Protenix
remains cancelled and the continuation watcher is stopped. Evidence:
`artifacts/0253-esm-full-defaults/{build.log,deployment.json,staging_verified.json}`.
This is a local build64 update; the published GitHub release was not replaced.
