---
entry: 0131
title: Audit three test2 ligand NISE campaigns
date: 2026-09-16
author: GPT-6 Codex
type: audit
status: complete
machine: Local M4 Max / 64 GB Studio installation; hardware utilisation not measured
tags: [nise, nesso, rfd3, ligand, audit]
---

## Context

The user requested an explanation of each campaign in
`~/.iproteinstudio/projects/test2/nise_runs`, including failures. This follows
the ligand-selection and named-run work in [[0130-atom-controls-and-run-names]].

## What was done

Used the read-only MCP workflow guide and results overviews, then inspected saved
requests, candidate/atom/screening records, broker terminal state, nested worker
logs and frozen runtime control flow. Inspected RFdiffusion3 fixture arrays without
loading a model. Added a [report](artifacts/0131-test2-nise-audit/REPORT.md),
[reproducible analysis script](artifacts/0131-test2-nise-audit/audit.py) and
[derived JSON](artifacts/0131-test2-nise-audit/audit.json). No campaign files changed.

## Results

Existing local-run observations, one campaign per condition. Durations below are
recorded job wall spans, **not new benchmarks or device compute measurements**.

| Condition | Initial structures | Sequence-bearing Boltz folds | Outcome | Recorded wall span |
|---|---:|---:|---|---:|
| Boltz / Protein Hunter | 100 | 2,369 | Completed; five historical exports, two pass later ligand check | 220,085 s |
| NESSO / Protein Hunter | 100 | 127 | Zero of nine initial-gate candidates pass Cα <2 Å | 23,352 s |
| NESSO / RFD3 | 0 completed | 0 | Empty buried-atom subset crashes metrics reduction | 139 s |

Boltz optimisation stopped normally at cycle11 under saved termination rules.
NESSO screened 354 sequences, rejected two near-zero-entropy outputs, and selected
118 for folding. All nine subsequent unscreened gate candidates failed Cα RMSD;
three did pass atom checks. RFD3 fixtures had 0 buried, 4 exposed and 9 hotspot
atoms; two raw PDBs existed before the worker metrics exception. Provenance hash
matched the inspected installed generator. Full stage counts and winner metrics
are in the report and JSON.

## Decision and rationale

Classified no gate survivors as a filtering outcome, the RFD3 exception as a code
defect, and historical winner exports as a qualification/labeling issue. Did not
weaken filters or alter frozen runs. A smaller NESSO shortlist plausibly reduces
lineage retention, but these different starting structures/sequences cannot support
a causal model comparison. Prefer paired recorded inputs for that follow-up.

## Reproduce

From the canonical Studio repository, with Python 3 and NumPy:

```bash
python3 lab_book/artifacts/0131-test2-nise-audit/audit.py \
  --runs "$HOME/.iproteinstudio/projects/test2/nise_runs" \
  --jobs "$HOME/.iproteinstudio/agent/jobs" \
  --output /tmp/test2-nise-audit.json
cmp /tmp/test2-nise-audit.json lab_book/artifacts/0131-test2-nise-audit/audit.json
```

## Limits and what was not tested

Ran the audit script against all three real campaigns; verified selected NESSO
score formulas and uniquely matched exported winning sequences/scores to candidate
records. No inference, geometry recomputation, experimental validation or new
throughput benchmark. No code fix, GPU smoke test, app build, installation or commit
was part of this read-only task. NumPy fixture inspection confirms the empty mask;
it is not an end-to-end verification of a repair.

## Next

Handle empty optional RFD3 metric subsets, label historical winners with the
checks active when selected, and compare shortlist sizes using fixed recorded
inputs. Run a small managed smoke test before any repaired large RFD3 campaign.
