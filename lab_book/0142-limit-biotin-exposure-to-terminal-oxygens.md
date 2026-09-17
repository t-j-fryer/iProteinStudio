---
entry: 0142
title: Limit the proposed biotin exposure filter to terminal oxygens
date: 2026-09-17
author: Codex
type: decision
status: complete
machine: CPU atom-map validation only
tags: [nise, biotin, exposure]
---

## Context

The user questioned whether requiring exposure beyond biotin's terminal section
was unnecessarily conservative. This updates the free-biotin plan from
[0140](0140-correct-noising-parent-budget.md); the exposure method remains the
SASA method described in [0141](0141-compare-nise-exposure-methods.md).

## What was done

Prepared a new [draft request](artifacts/0142-biotin-terminal-exposure/draft_request.json)
with exposed atoms O18 and O19, the terminal carboxyl oxygens. Removed C22
(carboxyl carbon) and C25 (adjacent methylene) from the exposure list; they remain
unselected, rather than being forced to bind. Kept the existing ring-head Bind
atoms and 50% retained accessibility threshold for each exposed oxygen.

Regenerated the atom map with the installed Boltz parser, validated its signature
and selected atoms, verified the terminal acid substructure with RDKit, and checked
that exposed_atoms is the only request field changed. Older drafts remain historical.

## Results

The preparation script passes. No performance, efficacy or survivor-count
measurements. Maximum design scale remains 55,208 structure predictions. This
filter is no stricter than the old four-atom filter on identical structures; its
actual effect on survival has not been measured.

## Decision and rationale

Use a terminal-oxygen accessibility criterion as the requested free-biotin
screening proxy, allowing more packing around the tail and carbonyl carbon.
There is no general requirement that the neighboring carbon atoms independently
retain 50% of their isolated accessibility. Keeping the oxygen threshold unchanged
makes this a single, explicit relaxation rather than simultaneously weakening
the required degree of exposure. This is not a claim that oxygen exposure alone
guarantees linker or attached-protein clearance, or that both oxygens persist
unchanged after conjugation.

## Reproduce

```bash
cd /Users/thomasfryer/iProteinStudio
/Users/thomasfryer/.iproteinstudio/venvs/NanoHunter_boltz/bin/python \
  lab_book/artifacts/0142-biotin-terminal-exposure/prepare.py
```

## Limits and what was not tested

No inference, matched-complex pass-rate analysis, chemistry ensemble, build,
installed-app change, campaign launch or job creation. This changes a draft
request only; no shipped code was edited. The pilot reaching cycle 2 remains
required before the large campaign.

## Next

Use this request for the reviewed campaign rather than the earlier four-atom
exposure draft. Audit terminal accessibility and poses in the bounded pilot.
