---
entry: 0113
title: Add initial NESSO screening and separate inactive run metadata
date: 2026-09-09
author: Codex
type: implementation
status: complete
machine: Local Apple Silicon macOS developer machine; model fixtures, no neural inference
tags: [nise, predictors, ui, provenance]
---

## Context

Following [[0112-audit-minibinder-inactive-settings]], the user requested clearer
run metadata and optional NESSO screening of initial NISE refinement and survivor
expansion sequences, independently of optimisation screening. They specified a
one-per-lineage refinement shortlist and a total expansion shortlist of 20,
maximum one per original lineage, with the existing Boltz gate and atom checks.

## What was done

- New version-2 Protein Hunter manifests project applicable settings into
  `request` and retain the full typed request under explicitly labelled
  `savedFormState`. Nanobody scaffold/CDR and retired beta controls disappear
  from the applicable minibinder request. Restoration prefers saved form state;
  version-1 manifests still decode. Actual arguments/environment/snapshot remain
  the execution authority. No historical campaign was edited.
- Added stage-neutral NESSO lineage selection with explicit ancestry, deterministic
  binding-probability/name ranking, per-lineage limits and an optional total cap.
  The installed adapter has no ligand pLDDT output; its affinity/entropy outputs
  are preserved separately and never substituted into the Boltz objective.
- Added `Backend.screen_initial` after LASErMPNN in each refinement and expansion
  round, using the existing NESSO/ESM resident client and audited score receipts.
  Refinement defaults to one folded candidate per lineage. Expansion first caps
  at one per original lineage, then takes 20 total. Gate derivatives retain
  their original lineage rather than becoming new diversity groups.
- The gate remains unscreened, with pocket restraints off. Initial sequence-bearing
  folds still pass through Boltz ranking and atom checks. Failed shortlisted
  candidates receive no automatic backfill. The separate trajectory count still
  limits seeds entering optimisation (six by default).
- Added independent `phase0_nesso_screen`, initial shortlist sizes,
  `phase0_gate_seqs`, and advanced initial/optimisation RMSD controls across native
  model/UI, Python contract, campaign arguments, budgets and MCP schema. Missing
  gate counts migrate from the historical shared refinement count. New screening
  remains off by default; either screening switch requires the pinned NESSO/ESM
  installation and fingerprints it in the plan.
- Added advanced disclosures, visible stage summaries and separately labelled
  initial/optimisation controls. Existing Small molecule atom controls retain
  their scope. CSV reports now include both stages, cycle, lineage and selection
  status, including candidates never folded. Score/shortlist receipts remain
  immutable replay units.
- Documented the exact funnel, constraints, migration and separate score meanings
  in `docs/NISE.md`, run metadata in `docs/CLI.md`, and MCP v16 / bridge 1.10.0.
  Build number is 29; upstream adaptation provenance and release notes updated.

## Results

No performance measurements. Calculated initial Boltz upper bounds with default
initial screening enabled are 620 for Protein Hunter or 520 plus 100 RFdiffusion3
backbones. NESSO additionally scores up to 2,100 sequences. These are arithmetic
budgets, not speedup measurements or efficacy claims.

- 14 NESSO contract tests passed: original optimisation selection/residency,
  initial ancestry caps, missing/changed ownership, independent dependencies,
  budget validation, interrupted-score replay, corruption and stage-aware CSV.
- Eight search/science tests passed. The new complete-funnel fixture covers both
  backbone generators, two screened refinement rounds, unscreened gate,
  original-lineage-limited expansion, correct pocket on/off routing, rejection
  by atom checks without backfill, and identical resume without new model calls.
- Nine NISE request/broker/checkpoint tests, nine atom/real-parser/SASA tests,
  and three RFdiffusion3 preparation/conditioning/resume tests passed.
- Six native Swift harnesses passed, including the new active-vs-restoration
  manifest assertions, legacy decoding, native NISE budgets, invalid controls
  and saved-request migration. `swift build` passed.
- Release build 29 completed. Ad-hoc app signature and packaged-resource checks
  passed, including MCP v16. Eight changed pipeline/schema resources matched
  source bytes. No `.safetensors`, `.ckpt`, `.pt` or `.pth` model files were found
  in the app. DMG/ZIP SHA-256 checks passed; `hdiutil verify` passed. A read-only
  mount matched all 391 app entries (file hashes, modes and symlinks) and was
  unmounted. No publication was performed.

Artifacts: `build/iProteinStudio.app` and
`build/unsigned-beta-0.2.0-29/iProteinStudio-0.2.0-unsigned-beta-apple-silicon.dmg`
(with the ZIP, checksums and local provenance alongside).

Logs: `/private/tmp/studio-build29-contracts.log`,
`/private/tmp/studio-build29-swift.log`, `/private/tmp/studio-nise29-*.log`,
`/private/tmp/studio-build29-release.log`.

## Decision and rationale

Use independent optional screens instead of changing the unscreened default
recipe. Keep Boltz folding and structural/atom selection after NESSO because the
sequence-only adapter cannot establish pocket geometry or solvent exposure.
Ancestry-based shortlist limits preserve independent initial lineages; these are
not measured structural-clustering guarantees. Expose existing RMSD criteria
rather than inventing a new combined NESSO confidence score.

Keep inactive UI state for exact restoration, with an explicit separate name,
rather than stripping it from saved workspaces or altering old run provenance.

## Reproduce

```bash
python3 Tests/run_swift_contracts.py
NANOHUNTER_ROOT="$HOME/.iproteinstudio" "$HOME/.iproteinstudio/venvs/NanoHunter_boltz/bin/python" Tests/test_nesso_screen.py
NANOHUNTER_ROOT="$HOME/.iproteinstudio" "$HOME/.iproteinstudio/venvs/NanoHunter_boltz/bin/python" -m unittest discover -s Tests -p 'test_nise_science.py' -v
NANOHUNTER_ROOT="$HOME/.iproteinstudio" "$HOME/.iproteinstudio/venvs/NanoHunter_boltz/bin/python" Tests/test_nise_contract.py
NANOHUNTER_ROOT="$HOME/.iproteinstudio" "$HOME/.iproteinstudio/venvs/NanoHunter_boltz/bin/python" Tests/test_nise_atoms.py
NANOHUNTER_ROOT="$HOME/.iproteinstudio" "$HOME/.iproteinstudio/venvs/NanoHunter_boltz/bin/python" Tests/test_nise_rfd3.py
swift build
bash release/release_app.sh --unsigned-beta --allow-dirty
```

## Limits and what was not tested

No neural-model campaign, biological affinity validation, screened-vs-unscreened
comparison, memory/throughput benchmark, interactive GUI/VoiceOver acceptance,
or second-Mac installation was run. Scientific model calls in the new funnel
fixture are fake; real atom/parser/SASA and ligand preparation tests cover the
existing geometry plumbing separately. No settings are promoted as scientifically
validated. Packaging is local ad-hoc beta, not a notarized public release.

## Next

Before a large scientific campaign, use the
broker's preflight and a 1–5-backbone end-to-end trial. A declared validation
campaign is needed to measure screening losses and total NESSO/ESM/Boltz cost.
