---
entry: 0146
title: Clarify the effective two-parent noising search
date: 2026-09-17
author: Codex
type: audit
status: complete
machine: Local development Mac; source review only
tags: [nise, partial-noising, beam, decision]
---

## Context

After the real branch test in0145, the user asked whether the partial-noising beam
logic makes sense. This is an assessment, not authorization to change the policy.

## What was done

Traced current-parent selection, candidate scoring, branch selection, next-cycle
parents, best-so-far updates and patience in `nise_run.py` and `partial_noising.py`.
Reviewed the fixture assertions in `Tests/test_nise_partial_noising.py` and the
real output audit from0145. No inference, code change or scientific default change.

## Results

From cycle2, the best two current designs each produce32 ordinary proposals.
Independently, the best current design produces32 masked predictions; the best
passing intermediate yields32 complete MPNN repairs. The next saved state contains
up to two ordinary winners plus one repair. However, the following cycle takes
only the top two from that saved state as ordinary parents, and its best member
as masking parent. A third-ranked repair gets no descendants. This is effectively
a two-parent search with an extra perturb-and-repair proposal route. The third
saved candidate is not a protected continuing exploratory lineage. First-cycle
64 proposals can save three winners, but only two are sampled in cycle2.

The existing fixtures explicitly confirm both lower-ranked repair exclusion and
higher-ranked repair promotion. Thus this is a description/policy mismatch rather
than a newly discovered departure from tested implementation. No new tests run.

The ordinary winners are pooled across parents, not one winner per parent.
Neither separate origin nor a reserved slot guarantees sequence/structure diversity.
Masked intermediates never become final winners. Historical bests remain archived
even when all current candidates score worse; archive retention does not feed the
old best back into sampling. Four consecutive rounds without an improvement greater
than0.01 relative to the previous recorded best stop the trajectory, capped at30.
Smaller improvements still update that recorded best without resetting patience.

Mask predictions compare against the original current parent; repairs compare
against the selected mask prediction. Backbone and atom checks apply at both
steps. Ligand RMSD is ungated in cycle2 and gated at both steps from cycle3.
Two passing local comparisons do not enforce a direct end-to-end pose bound.
In0145, the selected repair was1.615 Å from the intermediate ligand pose but4.988 Å
from the original parent. Both masked predictions would fail a2.5 Å gate if active
at that step. The test therefore does not establish later-cycle branch survival.

## Decision and rationale

Recommend describing and exposing two active parents plus an optional noising
proposal route: score complete ordinary/repair candidates, allow the best repair
to compete for a parent place, and retain at most two active parents. Keep other
candidates in history. This makes the existing effective behaviour explicit and
retains the128-fold later-cycle ceiling (64 ordinary+32 masks+32 repairs).
Recommendation only; not implemented in this review.

A genuinely continuing third parent would require another32 ordinary proposals
(160 total), or allocation of some existing ordinary budget to it. Merely saving
a low-scoring repair in a reserved third slot does not grant it future exploration.
Keep the geometry-first affinity policy, separate best archive and existing
stopping rules. Do not weaken RMSD gates solely to make the small test pass;
local refinement and permissive pose exploration are distinct scientific choices.

## Reproduce

Review `nise_run.py` lines620–717, `partial_noising.py` lines85–145 and the
partial-noising fixture's next-cycle parent assertions at source commitf6ca410.

## Limits and what was not tested

Static control-flow audit plus previously recorded evidence. No new model runs,
software changes, tests/build, efficacy experiment or timing claims. Recommendations
are algorithmic judgments, not experimentally validated search improvements.

## Next

Discuss the explicit two-parent proposal-route interpretation before changing UI,
serialized settings, immutable plans or scientific search behaviour.
