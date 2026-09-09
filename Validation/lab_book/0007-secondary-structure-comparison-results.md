---
entry: 0007
title: Analyze the completed five-arm secondary-structure comparison
date: 2026-09-04
author: gpt-6
type: analysis
status: complete; exploratory, no default promotion
machine: Apple M4 Max, 40-core GPU, 64 GB unified memory (campaign manifest)
tags: [secondary-structure, anti-helix, beta-sheet, paired-comparison]
---

## Question and provenance

Does changing the starting sequence suffice, or must the secondary-structure
prior remain active during SolubleMPNN redesign? This analyzes the five already
submitted full jobs from entry 0006; it does not submit new inference.

Each arm has 10 paired 90-residue binder trajectories against alpha-cobratoxin,
with resident Boltz and five optimized cycles. Prior strengths are 0.50. Seeds,
target and MSA policy were held fixed by the declared manifest. Both seed-only /
sustained pairs have exactly matching cycle-00 sequences in all 10 trajectories.

The launch provenance is `Validation/output/secondary_structure_priors_v1/manifest_full.json`:
commit `37cc95497283025191e7d2067cb35d1af9168d72` plus its recorded dirty-tree hash
`2e0a89bc1d637a51da35a5b2202dd4c3d0c7a8e83cbd00684e5d966255e7910f`.
The target MSA SHA-256 is
`377a3af41f6816683c9b06241fafd2e0c2bc6b0129c2f4a78387ad36f75f34cf`.
Immutable per-arm plans and campaign-owned pipeline snapshots retain script and
engine/checkpoint provenance; this analysis does not replace those records with
the subsequently edited app sources.

All five durable states report completed. Finish times span 20:19–22:31 UTC on
2026-09-04. The old `jobs_full.json` submission statuses are stale; they were not
used as completion evidence. No elapsed-time or throughput comparison is made.

## Audit and method

- Exactly 300 unique coordinate outputs: 50 initial structures and 250 optimized
  structures. Every run has cycles 00–05 and all expected confidence records.
- All chain-A structures contain 90 C-alpha atoms, exactly match the recorded
  requested binder sequence, and have finite coordinates. No optimized sequence
  contains an X mask. CSV iPTM/pLDDT match the corresponding confidence JSON.
- No adjacent C-alpha distance outliers under the explicitly defined 2.5–4.5 Å
  screen. This is a coarse continuity check, not a complete geometry/clash audit.
- Logs contain MPS evidence in each arm. Only the permitted Boltz
  `aten::linalg_svd` CPU-fallback warning was found: 68 warning occurrences per
  arm across duplicated/nested logs, not 68 measured operator invocations. No
  other fallback messages were observed; this is a log audit, not device profiling.
- Secondary structure is Biotite 1.6.0 P-SEA on predicted chain-A coordinates,
  using the declared `analyze.py`; NumPy 2.4.1 supports the summary/audit.
  Biotite reports a label_atom_id substitution because auth_atom_id is absent in
  these CIFs. Chain identity and sequence were explicitly verified afterward.
- Primary summaries average optimized cycles 01–05 within each trajectory, then
  across the 10 trajectories. Because every trajectory is complete, these means
  also equal the balanced 50-structure mean. The independent statistical unit is
  the paired trajectory, not a cycle. Cycle 00 is excluded from design endpoints.
- Exploratory 95% percentile bootstrap intervals use 20,000 paired trajectory
  resamples, fixed RNG seed 20260904. They are unadjusted descriptive intervals
  across multiple endpoints, not confirmatory significance tests.

## Optimized-cycle results

| Arm | Helix % | Sheet % | Coil % | iPTM | Binder pLDDT /100 |
|---|---:|---:|---:|---:|---:|
| Natural | 43.3 | 12.1 | 44.6 | 0.716 | 69.9 |
| Anti-helix, seed only | 37.1 | 17.0 | 45.8 | 0.741 | 63.8 |
| Anti-helix, sustained | 25.6 | 17.4 | 57.0 | 0.687 | 60.5 |
| Beta, seed only | 44.7 | 14.2 | 41.1 | 0.755 | 68.2 |
| Beta, sustained | 44.2 | 15.0 | 40.7 | 0.713 | 70.0 |

Fractions are mean percentages of the 90 binder residues. Binder pLDDT is the
mean of the binder C-alpha confidence values, reported on the 0–100 scale; iPTM
comes from the design-engine complex confidence record.

The strongest controlled result is sustained anti-helix versus anti-helix
seed-only: **11.56 percentage points less helix**, with a paired interval of
**4.27–20.42 points less**. Nine of ten paired trajectories have less helix on
average. Sheet changes by only **+0.36 points** (interval -4.20 to +4.49), while
coil increases by **11.20 points** (+4.67 to +18.58). The intervention reduces
helix predominantly by increasing coil rather than creating beta-sheet.

Relative to natural controls, sustained anti-helix has 17.76 points less helix
on average, but that contrast is noisier (interval -35.49 to +1.27 points).
The better-isolated seed-only/sustained comparison is the clearer evidence for
continued pressure during redesign.

Beta seed-only and sustained arms have sheet fractions of 14.20% and 15.04%,
versus 12.07% natural. Sustaining beta pressure adds only **0.84 points** relative
to beta seed-only (interval -3.60 to +6.31), and changes helix by -0.47 points
(-8.73 to +9.11). Neither beta comparison establishes reliable sheet enrichment.
Both beta arms remain about 44–45% helical in these predictions.

There is a confidence tradeoff to monitor for anti-helix: mean binder pLDDT is
60.5 sustained, 63.8 seed-only and 69.9 natural. Mean iPTM is 0.687, 0.741 and
0.716 respectively. Sustained minus seed-only iPTM is -0.054, with an interval
spanning zero (-0.152 to +0.045); a binding-quality penalty is not established.
These are design-engine confidence metrics, not binding measurements.

## Final cycle, reported separately

| Arm | Helix % | Sheet % | Coil % | iPTM | Binder pLDDT /100 |
|---|---:|---:|---:|---:|---:|
| Natural | 44.9 | 11.8 | 43.3 | 0.696 | 73.3 |
| Anti-helix, seed only | 37.2 | 16.4 | 46.3 | 0.805 | 74.7 |
| Anti-helix, sustained | 24.0 | 17.4 | 58.6 | 0.616 | 67.6 |
| Beta, seed only | 45.8 | 14.6 | 39.7 | 0.722 | 76.5 |
| Beta, sustained | 45.0 | 15.9 | 39.1 | 0.796 | 78.9 |

This endpoint has 10 structures per arm. Final-cycle iPTM >=0.70 occurs in 5/10
natural, 9/10 anti-helix seed-only, 4/10 sustained anti-helix, 5/10 beta seed-only
and 7/10 sustained beta outputs. These are descriptive threshold counts, not
independently verified hits, and were not used to select a winning prior.

## Interpretation and limits

Sustained anti-helix has evidence of the intended helix-suppression effect in the
paired contrast. Its product is more coil, with lower mean binder confidence.
The beta control has not demonstrated the intended reliable sheet enrichment.
Keep both interventions experimental; no default is promoted by this analysis.

This is one target, one binder length, one strength setting, one design predictor
and 10 paired trajectories per arm. There are no independent confirmation folds
or wet-lab measurements. Sequence diversity, detailed clashes/geometry,
strand-register accuracy, solubility and cross-target replication have not been
analyzed here. P-SEA assignment does not prove a stable beta fold or binding.

## Reproduce and artifacts

```bash
python3 Validation/experiments/secondary_structure_priors_v1/analyze.py \
  --campaign-root Validation/output/secondary_structure_priors_v1/campaigns \
  --output Validation/output/secondary_structure_priors_v1/analysis/psea_per_structure.csv
/path/to/biotite-python Validation/experiments/secondary_structure_priors_v1/summarize.py \
  --root Validation/output/secondary_structure_priors_v1
```

The actual prepared interpreter used was
`~/.iproteinstudio/venvs/NanoHunter_protenix/bin/python`. It was already installed;
no dependencies, weights or runtime scripts were changed.

Derived artifacts under the campaign's ignored `analysis/` directory:
`psea_per_structure.csv`, `audited_per_structure.csv`, and
`comparison_summary.json`. The JSON retains arm means, paired intervals, audit
results and SHA-256 fingerprints of all inspected raw coordinates, confidence
files and metrics CSVs, plus the launch manifest and P-SEA input table. The new
`summarize.py` was executed successfully; raw job outputs were not modified.
