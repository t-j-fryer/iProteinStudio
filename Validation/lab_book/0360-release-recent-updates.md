---
entry: 0360
title: Qualify Studio build81 and current shared workflows
date: 2026-11-04
author: Codex
type: audit
status: in-progress
machine: Apple M4 Max, 40-core GPU, 64 GB unified memory
---

Manifest: experiments/studio_release_032_v2/manifest.json. Eight RFD4 routes and
two T4 prediction checks; existing immutable planner/broker path, pinned model
and runtime hashes, cached SUMO/scaffold MSAs for protein routes; ligand and T4
prediction MSA empty, no external MSA fallback. Output audits cover complete
receipts, cardinality, finite coordinates/objectives, chemistry/atom identity,
framework/conformer allocation, no unwanted affinity calls, and exact T4 kernel
parity without automatic reference generation. All raw outputs retained.

NESSO job-e0d6fb15dfc2 paused via supported cancel. Old failed build78 outputs and
draft remain held. Source/provenance and managed job IDs will be in preparation.json
and jobs.json. No efficacy or performance claim. Results pending.
