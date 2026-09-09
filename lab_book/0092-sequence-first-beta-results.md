---
entry: 0092
title: Analyze the completed sequence-first beta sampling comparison
date: 2026-09-05
author: gpt-6
type: analysis
status: complete
machine: Apple M4 Max, 40-core GPU, 64 GB unified memory, macOS 26.6.1
tags: [secondary-structure, beta-sheet, seed-only, boltz, validation]
---

## Context

Follow-up to project entry0091 and Validation entry0009. The user requested an
analysis of the two completed seed-only arms: beta-pattern sampling alone versus
beta plus helix-kill weights, sampling the complete sequence before45/90 X masks.
Boltz2 and normal SolubleMPNN subsequently ran ten trajectories per arm with five
optimized cycles. There was no supplied binder structure or independent postcheck.

## What was done

Reviewed both runs through results_overview: ten trajectory groups each. The
background monitor had completed the full audit and paired summary. Rechecked
all394 audit-recorded SHA-256 values (including managed broker state aliases) and
all four summary input hashes using the executed inspect_results.py. Immutable
scientific outputs were not changed. Derived review.json and trajectories.svg/png
show paired trajectory means and cycle trends. The initial hash-check attempt
assumed job_state aliases were local files; corrected their resolution to the
recorded managed runtime before successfully verifying every hash.

Scientific provenance remains in Validation/output/secondary_structure_seed_mask_v1/
manifest_full.json and stage_receipt.json. Launch commit37cc95497283025191e7d2067cb35d1af9168d72
plus the manifest's dirty-file fingerprints identify the uncommitted implementation.
The launch manifest records MSA checksum377a3af41f6816683c9b06241fafd2e0c2bc6b0129c2f4a78387ad36f75f34cf.
The stage receipt fingerprints Boltz2 and SolubleMPNN checkpoints and measured hardware.

## Results

Both jobs completed with exit0: beta job-a29994816133; mixed job-5c17a5cfae6d.
All120 structures audited (100 optimized,20 initialization). Exact sequence and
mask replay, finite90-CA coordinates, confidence files, output cardinality,
script provenance and absence of MPNN secondary bias passed. No adjacent-CA
outliers at2.5–4.5 angstrom bounds. Each arm had68 allowed Boltz SVD warning
occurrences across duplicated logs; these are not independent fallback-call
counts. No other inference fallback messages were found.

Primary statistical unit: mean cycles01–05 within each trajectory, then ten
trajectory means per arm. Cycle00 is excluded. Paired differences are mixed minus
beta. Percentile95% intervals use20,000 resamples of whole trajectory pairs,
seed927315. Intervals are conditional on this target/configuration and unadjusted
for multiple reported endpoints.

| Metric | Beta only | Beta + helix kill | Paired difference (95% CI) |
|---|---:|---:|---:|
| Sheet | 11.4% | 19.4% | +8.0pp (-5.6,+20.7) |
| Helix | 54.1% | 33.9% | -20.2pp (-41.5,+2.3) |
| Coil | 34.4% | 46.7% | +12.2pp (+2.1,+22.9) |
| Binder pLDDT (0–100) | 78.1 | 67.7 | -10.4 (-17.2,-2.7) |
| Complex pLDDT (0–100) | 80.6 | 73.9 | -6.7 (-11.1,-1.7) |
| iPTM | 0.704 | 0.711 | +0.007 (-0.076,+0.091) |
| ipSAE | 0.323 | 0.327 | +0.004 (-0.107,+0.110) |

Neither cohort reaches both sheet>=25% and helix<40%. Mixed meets the helix
threshold but misses sheet. Individually,2/10 beta and3/10 mixed trajectories meet
both thresholds on their optimized-cycle means. At cycle05,3/10 and4/10 meet both.
Mixed sheet increases in7/10 matched seeds, decreases in2/10 and is unchanged in1/10.
The large decreases in some seeds explain why the sheet interval includes zero.

At final cycle05, beta has12.0% sheet,54.7% helix, binder pLDDT87.9; mixed has20.2%
sheet,34.9% helix, binder pLDDT82.9. These final-only results are secondary endpoints.

Cycle00 sheet was10.1% beta versus20.7% mixed; cycle05 was12.0% versus20.2%.
Confidence rose from51.2 to87.9 beta and44.5 to82.9 mixed. Thus the aggregate
secondary-structure split was already present at initialization and changed little
through normal MPNN cycles. This supports refinement of initial folds as an
interpretation; aggregate fractions alone do not prove topology conservation.

All50 optimized sequences per arm are unique. Mixed has higher average sequence
entropy (3.721 versus3.532bits) and lower largest-residue fraction (16.1% versus20.2%).
Its confidence cost therefore does not coincide with greater compositional collapse
on these metrics. Uniqueness is not experimental fold or binding validation.

## Decision and rationale

This completed experiment does not establish reliable beta-sheet control from
stronger patterned seed sampling. Adding helix kill has a favourable observed
sheet/helix trend, but more of the net helix decrease is balanced by increased coil
than increased sheet, with lower average confidence. The structural uncertainty
intervals include no change. Do not describe the mixed arm as a proven improvement.

The flat sheet trajectory argues against explaining the result simply as MPNN
progressively erasing an initially beta-rich fold. It also provides no observed
reason to expect more iterations alone to achieve the target. It does not isolate
whether the50% mask, residue weights, positional grammar or predictor preferences
limit initial sheet formation: those factors were not independently varied here.
No further scientific campaign was launched and no defaults were promoted.

## Reproduce

From the canonical repository after full campaign completion:

```bash
MPLCONFIGDIR=/private/tmp/iproteinstudio-mpl ~/.iproteinstudio/venvs/NanoHunter_protenix/bin/python Validation/experiments/secondary_structure_seed_mask_v1/inspect_results.py
```

Inputs: analysis/full/audit.json, comparison.json, audited_per_structure.csv,
audited_per_trajectory.csv. Existing summary.py reproduces the paired statistics;
their input hashes were verified without rewriting the completed audit.

## Limits and what was not tested

One target,90-residue binders, one hardware/model configuration, ten seed pairs.
No new matched natural arm; historical natural/weaker-prior comparisons are only
descriptive. No binder-alone or orthogonal predictions, experimental structure,
aggregation or binding tests. PSEA assignments and pLDDT are prediction-based.
No app code changes, app build, commit or additional inference in this analysis.

## Next

The requested comparison is complete. Keep the full cohort result as negative
against the declared joint threshold; retain individual successes as exploratory.
Any new experiment should be declared separately without selecting a winning subset.
