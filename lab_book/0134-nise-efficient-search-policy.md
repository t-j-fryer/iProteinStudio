---
entry: 0134
title: Add the biotin-inspired NISE search policy without rollback or rescue
date: 2026-09-16
author: GPT-6 Codex
type: implementation
status: complete
machine: Apple M4 Max, 64 GB unified memory, macOS 26.x; software fixtures only
tags: [nise, boltz, nesso, rfd3, resume, ui]
---

## Context

The user supplied a workstation biotin retrospective and requested its early
score gate, selective affinity evaluation, eight-cycle cap and adaptive proposal
top-ups, explicitly excluding rollback and bounded rescue. This follows the NISE
run audit (0131) and RFdiffusion3 repair (0132). Other uncommitted work, including
the OpenFold queue repair (0133), was preserved.

The pasted chat reports ~52% fewer affinity evaluations and a reduction from
27,300 to 17,205 structure evaluations under particular retrospective policies.
Those numbers come from the user's supplied chat, on an unspecified workstation;
the original biotin outputs and analysis were not provided or independently
verified here. They are not Studio measurements or guarantees on another ligand.

## What was done

- Added shared policy code in `scripts/nise/search_policy.py`, used downstream of
  either Protein Hunter hallucination or RFdiffusion3 initial generation, with
  initial/optimisation NESSO screening independently enabled or disabled.
- New typed requests default to 100 starts, eight distinct-lineage seeds, beam
  three, eight optimisation cycles, five-cycle patience and a 0.80 first-refinement
  Boltz score gate. The existing initial sampling counts remain 3/3/5. Starts
  stay adjustable; the optional clarification about switching to 1,000 received
  no response during implementation, so the user's earlier explicit 100 default
  was retained.
- Added selective affinity: requested atom/RMSD checks precede the head; cycle00
  and the unconstrained gate omit it. Eligible candidates are visited in decreasing
  ligand pLDDT and skipped only when their strict upper bound cannot reach the
  relevant lineage/seed/beam boundary. Ties are evaluated. Missing scores remain
  null with reasons. The final objective is still Boltz ligand pLDDT/100 + P(bind).
- Split resident Boltz structure/affinity requests using the installed Boltz CLI's
  `filter_inputs_structure` / `filter_inputs_affinity` boundaries. Retained affinity
  properties in YAML to preserve chemical preprocessing and full-precision
  `pre_affinity_*.npz` output. Affinity reads that audited NPZ without refolding.
  Separate receipts bind inputs, structure artifacts and affinity results. The
  cached structure and affinity checkpoints retain their distinct identities.
- Added experimental opt-in adaptive sampling: 16, 32, 64 cumulative proposals
  per parent by default, implemented as +16, +16, +32. Parents stay fixed within
  a cycle. Each trajectory independently stops topping up after >0.01 improvement;
  all evaluated candidates compete for its next beam. Patience increments only
  once per completed cycle. No rollback, rescue, budget reset or shared survivor
  pool exists. Any new best, including a sub-threshold gain, remains available.
- NESSO screens each new proposal batch separately, with a per-trajectory cap;
  folded candidates are pooled across rounds. This can increase the maximum
  folds to three shortlists per cycle. UI/Python budget estimates account for it.
  Invalid placements in an adaptive optimisation batch can yield an empty
  shortlist and another top-up, without substituting a weaker score.
- Recorded full current/last-improving beams and structure hashes in advancement
  checkpoints, incremental parent/count decisions in proposal-round files, and
  completed unique-operation costs in `search_cost.json`.
- Versioned saved request migration, Swift controls/validation, MCP schema/guide,
  upstream adaptation notes and NISE documentation. Old saved requests retain
  exhaustive affinity and their original budgets; frozen running jobs are unchanged.

## Results

No measurements — implementation and software validation only. No neural model
was launched, no active campaign was changed, and no throughput claim is made.

Executed checks (logs under `artifacts/0134-nise-search-policy/`):

- **35 NISE tests passed**: input contracts, real Boltz atom parser with installed molecular
  dictionary, RFdiffusion3 adapter, search/funnel and efficient-policy integration.
- Six new policy tests cover randomized exact-selection comparisons, ties,
  independent stopping, eight-cycle cap, all four generator/screen combinations,
  geometry-first rejection, interruptions in initial affinity and in a top-up,
  replay without new model calls, full beam/counter checkpoints, and split-worker
  artifact reuse/tamper rejection.
- **18 NESSO screening tests passed; 14 resident-prediction tests ran with one
  optional Accelerate CPU-loader test skipped.**
- **18 desktop-job and 17 MCP bridge tests passed**, using inert worker fixtures.
- Swift saved-workspace/default validation and result-display harnesses passed,
  as did `swift build`. Unscored candidates are labelled distinctly from geometry
  failures in the result browser and MCP output.
- Isolated import of the request contract without `scripts/nise` on `sys.path`,
  matching MCP's file-based module loading.

One initial regression run exposed a missing optional argument on the direct
candidate-evaluation test path; fixed with the legacy default. The real-parser
test also required the actual managed `NANOHUNTER_ROOT`, not the test checkout;
rerunning with that installation passed. No model weights were copied.

## Decision and rationale

The upper bound is mathematically valid because validated P(bind) is in [0,1],
but only when applied to the actual selection boundary after geometry filtering.
Distinct-lineage seed selection requires a separate diversity-aware boundary.
The 0.80 gate remains a pilot threshold; its success on biotin does not calibrate
NESSO or establish generality. NESSO remains a prescreen, not a substitute final
objective. Adaptive proposals are off by default because savings are unmeasured.

Kept top-ups rather than rollback/rescue as requested. A whole exhausted cycle
counts once toward patience and the configured cycle limit. Recorded exact
sampled sequences are the replay authority because LASErMPNN lacks seed control.

## Reproduce

```bash
bash "$HOME/.iproteinstudio/setup_pipeline.sh" --detect
NANOHUNTER_ROOT="$HOME/.iproteinstudio" \
  "$HOME/.iproteinstudio/venvs/NanoHunter_boltz/bin/python" \
  -m unittest discover -s Tests -p 'test_nise*.py'
"$HOME/.iproteinstudio/venvs/NanoHunter_boltz/bin/python" Tests/test_nesso_screen.py
"$HOME/.iproteinstudio/venvs/NanoHunter_boltz/bin/python" Tests/test_resident_prediction_resume.py
CLANG_MODULE_CACHE_PATH=/private/tmp/iproteinstudio-modules \
SWIFTPM_MODULECACHE_OVERRIDE=/private/tmp/iproteinstudio-modules \
  swift build --disable-sandbox --skip-update
```

## Limits and what was not tested

No real-model end-to-end run of split Boltz stages, GPU performance/memory test,
independent biotin retrospective, prospective ligand campaign, GUI click test,
DMG build, installed-app update or publication. Model boundaries use deterministic
fixtures. The split hook matches the inspected installed Boltz source; future
upstream changes may require adaptation. Exact selection for fixed scores does
not promise identical random-number consumption or bitwise identity with a prior
combined structure-plus-affinity invocation. Final best-so-far output retains its
original stage qualification; the historical later-gate qualification issue in
0131 is not silently changed here.

## Next

Run a managed small end-to-end acceptance trial before any large campaign, then
compare fixed/adaptive search under identical gates using compute per independently
qualified final candidate. Package/install when requested. Do not quote the biotin
retrospective percentages as measured Studio savings.
