---
entry: 0085
title: Add explicit iterative secondary-structure sequence priors
date: 2026-09-04
author: gpt-5.6
type: implementation
status: inference-validation-in-progress
machine: Apple M4 Max, 40-core GPU, 64 GB unified memory, macOS 26.x
tags: [iterative-design, secondary-structure, beta-sheet, solublempnn, mcp]
---

## Context

The iterative de-novo form exposed a single `helixKill` slider. Its runner rule
downweighted A/E/K/L/M/Q globally, penalized another helix-prone residue at
sequence lag four, and boosted Ser. The UI then described lower helix as
favouring "sheet & loop" and displayed predictor-specific expected percentages.
That conflated three different outcomes: less α-helix, more β-strand, and more
unstructured coil. It also acted mainly on the cycle-00 seed; later MPNN cycles
only inherited the unrelated global Pro suppression called `loopkill`.

The supplied design discussion proposed separating anti-helix pressure,
β-compatible composition, alternating strand faces, and localized turns. That
separation is scientifically more defensible, but remains a hypothesis about a
sequence prior. Only secondary-structure assignment on predicted coordinates
can establish whether it makes β-rich folded binders.

The originally requested 10-trajectory × 5-cycle Cbx/Boltz experiment was
explicitly withdrawn while implementation was in progress: "Just establish the
code for this, ignore the target for now." No target campaign was therefore
started and no effect size is claimed here.

## What was implemented

- Replaced the helix-only form control with four explicit choices:
  `Natural diversity`, `Reduce α-helix`, `Encourage β-rich`, and
  `β-rich + reduce α-helix`.
- Added independent 0–1 controls for anti-helix pressure, β-compatible residue
  bias, alternating-face pattern, and localized-turn bias. Pattern and turn
  details remain under Advanced; the feature is visibly labelled experimental.
- Removed the old unvalidated expected-helix percentages and the statement that
  helix suppression itself favours sheets.
- Added `secondary_structure_control.py`, a standalone and testable policy
  helper. For β/mixed modes it creates exact alternating 5–8-residue strand and
  2–5-residue turn blocks using a seed-derived RNG stream independent from the
  historical sequence RNG.
- Protects both ends of every proposed strand with polar/solvent-friendly bias,
  uses a deliberately noisy hydrophobic/polar alternating pattern internally,
  suppresses G/P inside proposed strands, favours G/D/N/S in proposed turns,
  and boosts Pro only at the turn core. This is intended to avoid turning a
  β-pattern control into a global hydrophobic repeat or global Pro enrichment.
- Writes one atomic `secondary_structure_plan.json` per trajectory. Its schema,
  positions, blocks, controls, seed and `experimental-sequence-prior-not-fold-guarantee`
  status are durable run provenance.
- Added an explicit application scope: `seed-only` applies the sequence grammar
  while generating cycle 00 and then restores normal MPNN redesign; the
  compatibility-preserving `seed-and-cycles` default additionally converts the
  same position plan into an MPNN bias map at every redesign. The scope is saved
  in the plan and run request. For a fixed seed, both scopes produce the same
  cycle-00 sequence, positions and blocks, isolating persistence of the prior as
  the experimental variable.
- Converts that same plan into LigandMPNN's native
  `--bias_AA_per_residue` JSON for every ProteinMPNN/SolubleMPNN/LigandMPNN
  redesign cycle. The resident and cycle-wave schedulers both reach the shared
  redesign function, so neither silently drops the control.
- Preserved the released no-bias and helix-kill cycle-00 random streams
  byte-for-byte for fixed seeds. Historical `--helix-kill` and
  `--negative-helix-constant` flags remain compatibility aliases, and old saved
  GUI requests with nonzero `helixKill` migrate to explicit anti-helix mode.
- Rejects irrelevant/contradictory strengths and scaffold/motif/partial-redesign
  combinations. `seed-and-cycles` rejects LASErMPNN because it has no compatible
  position-bias interface; `seed-only` does not require that interface.
- Added the same flags, bounds and scientific warnings to the MCP planner and
  workflow guide. The bridge is MCP contract v8 / package version 1.3.0.
- Allowed MCP iterative plans to pin the already-supported predictor seed and
  sample count, with integer validation, so paired Validation arms do not rely
  on an implicit runner default.

## Code-level validation

No predictor or inverse-folding model was loaded. These checks establish the
software contract only:

| Check | Result |
|---|---|
| Deterministic helper unit tests | 5/5 pass |
| Historical no-bias seed, length 90, seed 101 | byte-identical |
| Historical anti-helix seed, strength 0.5, length 90, seed 101 | byte-identical |
| β plan cardinality/index coverage | exact 90/90 positions |
| Strand/turn bounds | all strands 5–8; all turns 2–5 |
| Strand edge and turn-core bias signs | pass |
| Matched scope cycle-00 sequence and architecture | byte-identical |
| Seed-only redesign bias | empty, while seed-phase bias remains active |
| Swift request/command/migration contract | pass |
| Shell CLI routing/range contract | pass |
| MCP suite including β arguments and invalid bounds | pass |
| Full `swift build` for arm64 macOS | pass |

Commands:

```bash
cd /Users/thomasfryer/iProteinStudio

python3 -m unittest \
  Tests/test_secondary_structure_control.py \
  Tests/test_mcp_bridge.py

CLANG_MODULE_CACHE_PATH=/tmp/iproteinstudio-secondary-clang \
SWIFT_MODULECACHE_PATH=/tmp/iproteinstudio-secondary-swift \
swiftc -parse-as-library \
  Sources/iProteinStudio/Models/ProteinSequenceInput.swift \
  Sources/iProteinStudio/Models/Predictor.swift \
  Sources/iProteinStudio/Models/RFD3Request.swift \
  Sources/iProteinStudio/Models/DesignRequest.swift \
  Sources/iProteinStudio/Models/DesignPoint.swift \
  Sources/iProteinStudio/Models/RunResult.swift \
  Sources/iProteinStudio/Core/ResumeContract.swift \
  Sources/iProteinStudio/Core/TemplateWriter.swift \
  Sources/iProteinStudio/Core/CommandBuilder.swift \
  Sources/iProteinStudio/Core/MetricsWatcher.swift \
  Tests/IterativeCommandContractHarness.swift \
  -o /tmp/iproteinstudio-secondary-contract
/tmp/iproteinstudio-secondary-contract

bash Tests/test_iterative_cli_contract.sh

SDKROOT=/Library/Developer/CommandLineTools/SDKs/MacOSX15.4.sdk \
CLANG_MODULE_CACHE_PATH=/tmp/iproteinstudio-secondary-build-clang \
SWIFTPM_MODULECACHE_OVERRIDE=/tmp/iproteinstudio-secondary-build-swift \
swift build --triple arm64-apple-macosx15.0 \
  --scratch-path /tmp/iproteinstudio-secondary-build
```

## Decision

The code is available, but `none` remains the default and every active mode is
labelled experimental. This is intentional: a sequence grammar can change
composition and periodicity without producing a stable β topology or a usable
interface. The removed UI percentages must not be reinstated from old DSSP/P-SEA
campaigns because those campaigns did not test this implementation.

## Inference validation started

After the user restored the Cbx validation request, the matched experiment in
`Validation/experiments/secondary_structure_priors_v1/` ran its mandatory smoke
gate. All five arms completed cycle 00 plus five redesign cycles (30/30 expected
structures), and both scope pairs reproduced byte-identical cycle-00 sequences.
The full five-arm 10-trajectory campaign was then submitted through immutable
MCP v8 plans. See Validation Lab Book entry 0006 for job identifiers and status.

## Still not tested

- The full Cbx 10 × 5 jobs have not completed, so no comparative effect size is
  reported yet.
- IntelliFold, Protenix, OpenFold, ProteinMPNN and LigandMPNN were not exercised
  by this validation; the smoke gate used resident Boltz and SolubleMPNN.
- No completed P-SEA comparison, interface analysis, aggregation assessment,
  hit-rate comparison, memory measurement or performance benchmark is reported.
- The control has not been checked on the M1 machine.

## Required follow-up before promotion

Run paired, seed-matched control and experimental campaigns with identical
target, MSA, predictor, MPNN, lengths, temperatures, cycles and scheduler.
Exclude cycle 00 from design endpoints. Assign H/E/C from predicted coordinates
with Biotite P-SEA and report β-segment count, longest and mean β-segment length,
not just total sheet fraction. Retain interface/hit/developability filters so a
gain in sheet content cannot hide loss of folding or binding quality. A 10 × 5
campaign is useful development evidence, but is not by itself enough to promote
a global default.
