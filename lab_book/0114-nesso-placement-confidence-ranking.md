---
entry: 0114
title: Rank NESSO screens by binding probability and placement confidence
date: 2026-09-09
author: Codex
type: bugfix
status: complete
machine: Local Apple Silicon macOS developer machine; CPU tensor check and model fixtures
tags: [nise, predictors, correctness, provenance]
---

## Context

The user specified NESSO P(bind) + (1 − protein–ligand placement entropy),
rejecting invalid or near-zero entropy so missing placement cannot be rewarded.
This supersedes the probability-only screening choice in [[0113-initial-nesso-screening-and-run-metadata]].

A search of beta's scripts, NESSO experiment source, docs and Lab Book did not
locate the earlier combined ranking or its exact cutoff. The installed NESSO
source exposes normalized full `entropy_pl` and separate pocket-cropped
`entropy_crop_pl`. This change explicitly uses full `entropy_pl`, with a
numerical lower bound of 1e-6, as stated to the user during implementation. The
cutoff is not claimed as an inherited or biologically validated value.

## What was done

- Added shared `placement_score` and `nesso-pbind-placement-v1` policy: descending
  `affinity_probability_binary + (1 - entropy_pl)`, candidate name breaks ties.
  Both optimisation and initial lineage/expansion selection use the same score.
- Eligibility requires numeric, finite entropy in (0.000001, 1]. Missing,
  non-finite, out-of-range, zero and near-zero entropy have no screening score
  and are rejected before shortlist caps. The cropped field is never used as
  a fallback. Invalid affinity or other required scalar outputs still fail loudly.
- The worker preserves invalid non-finite/missing placement as JSON null and
  records its rejection assessment. Valid model outputs and installation assets
  are unchanged; no new neural inference protocol or dependency was introduced.
- Selection receipts include the exact formula, field, cutoff, tie rule, scores
  and rejection reasons. All-invalid screens save their report and then stop
  with an actionable error. Cached scores are replayed without new model calls;
  an old/changed ranking policy cannot silently reuse its saved shortlist.
- CSV reports include raw entropy, combined score, eligibility, reason and policy.
  Folded-candidate results show recorded NESSO placement entropy and screening
  score alongside probability/affinity. Old probability-only results are not
  assigned a new combined score retrospectively.
- Updated NISE UI explanations, result help, docs, MCP guide/contract v17
  (bridge 1.11.0), release notes and build number 30. Boltz advancement/ranking,
  structural gates, atom checks and resident-worker scheduling remain as before.

## Results

No neural-model or performance measurements.

- 18 screening tests passed, including ranking reversal, both grouping policies,
  exact entropy guard boundaries, full-vs-cropped field identity, invalid-value
  rejection, report contents, all-invalid failure, cached replay and old-policy
  rejection. Existing worker lifecycle and installation checks also passed.
- Eight search/funnel tests passed with model fixtures, including both initial
  generators and the optional optimisation screen.
- An ad hoc CPU tensor check used the installed NESSO
  `compute_distogram_entropy` implementation: uniform full-mask logits produced
  entropy_pl = 1; absent PL pairs produced 0. The new ranking guard rejected the
  missing-placement result. No model or ESM weights were loaded for this check.
- `swift build` and all six native Swift harnesses passed. Result fixtures verify
  the new entropy/combined-score display without inventing scores for old rows.
- Release build 30 and ad-hoc signature/resource checks passed. Changed Python
  resources match source; MCP v17 is packaged and no model weight files were
  found. DMG/ZIP SHA-256 checks and macOS image verification passed. A read-only
  mount matched all 391 app entries (hashes, modes and symlinks) and was detached.
  No publication or model-weight redistribution occurred.

Artifacts: `build/iProteinStudio.app` and
`build/unsigned-beta-0.2.0-30/iProteinStudio-0.2.0-unsigned-beta-apple-silicon.dmg`
(with ZIP/checksums alongside). Packaging log:
`/private/tmp/studio-build30-release.log`. This is a local ad-hoc beta, not a
Developer ID signed/notarized public release.

Logs: `/private/tmp/studio-build30-nesso.log`,
`/private/tmp/studio-build30-science.log`,
`/private/tmp/studio-build30-entropy-check.log`,
`/private/tmp/studio-build30-contracts.log`,
`/private/tmp/studio-build30-swift.log`.

## Decision and rationale

Use the requested additive placement-confidence term, preserving its components
and rejecting degenerate placement rather than clamping it into perfect
confidence. Use the normalized full protein–ligand field explicitly; a separate
cropped field is not silently interchangeable. Keep ranking policy separate
from the model-installation protocol, so the correction does not require a
NESSO/ESM reinstall. Historical campaigns retain their frozen pipeline semantics.

## Reproduce

```bash
"$HOME/.iproteinstudio/venvs/NanoHunter_boltz/bin/python" Tests/test_nesso_screen.py
"$HOME/.iproteinstudio/venvs/NanoHunter_boltz/bin/python" -m unittest discover -s Tests -p 'test_nise_science.py' -v
python3 Tests/run_swift_contracts.py
swift build
bash release/release_app.sh --unsigned-beta --allow-dirty
```

For the upstream entropy check, use the installed NESSO Python with two tokens
(PROTEIN and NONPOLYMER), zero distogram logits of shape [1,2,2,4], and compare
`token_disto_mask` [1,1] with [1,0]. Call `placement_score` on the resulting
`entropy_pl` and any valid probability to verify eligibility versus rejection.

## Limits and what was not tested

No real-model campaign, empirical binding/ranking validation, near-zero cutoff
calibration, throughput/memory benchmark, GUI/VoiceOver acceptance or second-Mac
installation. The tensor check verifies the missing-mask behavior only. The
combined metric is user-specified and experimental, not a validated binding
measurement. New runs use it; old campaign snapshots are not rewritten.

## Next

A declared small validation campaign is required
before promoting ranking accuracy or throughput claims.
