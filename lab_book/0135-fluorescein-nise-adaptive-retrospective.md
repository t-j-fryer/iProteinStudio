---
entry: 0135
title: Audit fluorescein score progression before choosing adaptive sampling
date: 2026-09-16
author: Codex
type: audit
status: complete
machine: Apple M4 Max, 64 GB unified memory; CPU retrospective only
tags: [nise, boltz, defaults, sampling, validation]
---

## Context

Follows [0134](0134-nise-efficient-search-policy.md). The user replaces the proposed
new-run defaults with 1,000 starts, maximum 30 optimisation cycles and four-cycle
patience, and requests analysis of the original fluorescein campaign before
choosing the adaptive 16→32→64 policy. No rollback or rescue is requested.

## What was done

Updated Swift NISERequest, Python request normalization/migration, MCP schema and
catalog, upstream adaptation record, documentation and contract tests to 1,000/30/4.
Explicit saved settings stay intact; legacy omitted fields restore 100 starts,
30 cycles and five-cycle patience. Adaptive remains off by default, 64 proposals
per parent, with no new adaptive algorithm or threshold promotion. The existing
shared improvement tolerance remains 0.01 pending the user's policy decision.

Audited `/Users/thomasfryer/NanoHunter/output/nise_fluorescein`: all 5,440 NISE
predictions, 85 trajectory-cycles and 79 confirmed next-parent advances. Code and
configuration live in `Validation/experiments/nise_fluorescein_adaptive_v1/`.
Source hashes, sequence identities, ligand atom correspondence, geometry gates
and parent Cα coordinates were checked. All 2,615 recorded passing rows agree
with recomputed geometry. Original inputs and outputs were not changed.

[Full report](../Validation/output/nise_fluorescein_adaptive_v1/analysis/REPORT.md),
[figures](../Validation/output/nise_fluorescein_adaptive_v1/analysis/GALLERY.html),
and [Validation record](../Validation/lab_book/0025-fluorescein-nise-adaptive-retrospective.md).
Compact numerical outputs and test logs are preserved in
`lab_book/artifacts/0135-fluorescein-retrospective/`.

## Results

The historical run had six trajectories, beam one and 64 proposals per parent;
initial starts were 100 despite the resumed configuration claiming 12. Score is
ligand pLDDT/100 + P(bind). Peaks for T0–T5 were respectively 1.7215, 1.8776,
1.6004, 1.9411, 1.9683 and 1.9586, at cycles 8, 3, 2, 13, 9 and 20.

| Conditional comparison | n complete trajectory-cycles | Mean proposals | Exact full-batch winner retained |
|---|---:|---:|---:|
| Fixed 64 | 79 | 64 | 100% |
| Adaptive 16→32→64, >0.01 | 79 | 56.35 | 92.3% |
| Adaptive 32→64, >0.01 | 79 | 58.39 | 94.5% |

2,000 permutations per observed group, not independent biological replicates.
The 16→32→64 proposal reduction is 12.0%, not a measured runtime reduction;
7.2% of decisions lose >0.01 relative to the full-batch winner. Actual sample
order changes 5/79 cycle winners, including T3 cycle 10 losing 0.1062.

Across all 85 groups, the median eligible count was 32 and only one candidate
was within 0.01 of its cycle winner. Median winner-minus-passing-median was 0.171.
All 79 actual advances were eligible maxima, but 24 had a better raw-scoring
geometry failure. Ten of 30 >0.0001 best-so-far gains were <=0.01. The global
winner's last two gains were about 0.0068 each. Four-cycle patience retains the
observed T0–T4 peaks but misses T5's late improvement from 1.94325 to 1.95860.

Validation: 35 NISE tests, 18 NESSO screening tests, Swift NISE request/migration
harness and `swift build --disable-sandbox --skip-update` passed. The migration
regression was then strengthened to explicitly assert 1,000/4/off versus legacy
100/5 and rerun. Raw-output audit verified 21,807 source hashes after reading.
Final figures were visually inspected. No new inference or speed measurements.

## Decision and rationale

Implement 1,000/30/4 because the user explicitly requested these defaults, not
because this single retrospective establishes optimal settings. Keep adaptation
off pending a decision. Prefer separating patience tolerance from the top-up
threshold: 0.01 ignores multiple recorded gains and does not guarantee that
stopping the proposal batch is safe. Consider 0.0001/0.001 patience and a 32→64
pilot against fixed 64; none is promoted here. Three-parent beam quality needs
its own prospective stopping criterion.

## Reproduce

See the [experiment README](../Validation/experiments/nise_fluorescein_adaptive_v1/README.md)
for exact extraction/report commands and new-output-directory replay.

```bash
NANOHUNTER_ROOT=/Users/thomasfryer/.iproteinstudio \
/Users/thomasfryer/.iproteinstudio/venvs/NanoHunter_boltz/bin/python \
  -m unittest discover -s Tests -p 'test_nise*.py'
/Users/thomasfryer/.iproteinstudio/venvs/NanoHunter_boltz/bin/python Tests/test_nesso_screen.py
CLANG_MODULE_CACHE_PATH=/private/tmp/iproteinstudio-modules \
SWIFTPM_MODULECACHE_OVERRIDE=/private/tmp/iproteinstudio-modules \
  swift build --disable-sandbox --skip-update
```

## Limits and what was not tested

53 cycle-five predictions lack affinity; no imputation. Six incomplete groups
excluded from subset simulations. Original runtime/checkpoint fingerprints cannot
be established from surviving metadata; the manifest says so. Empty MSA policy
verified in all candidate YAMLs. One historical ligand, one-parent beam, no
prospective adaptive descendants, beam-three test, NESSO or RFdiffusion3 efficacy
validation. No binding measurements, inference, GPU benchmark, app installation,
DMG or GitHub update. Existing unrelated uncommitted work remains intact.

## Next

Decide separate patience/top-up thresholds; only then run prospective paired
fixed/adaptive campaigns through the governed execution bridge. Compare several
independent final-filter-passing designs per unit compute, not just peak scores.
