---
entry: 0111
title: Verify NISE atom identity and add linker exposure requirements
date: 2026-09-08
author: Codex
type: bugfix
status: complete
machine: Apple Silicon local macOS developer machine; no model inference
tags: [ui, nise, rfd3, correctness]
---

## Context

The user requested correct small-molecule atom numbering for Boltz/NESSO,
binding hotspots, and solvent-exposed linker atoms within NISE. They also asked
what initial backbone generation does and whether NESSO could help there.

Audit found that NISE's automatic contact selector invoked an unshipped
`scripts/nise/boltz_ligand_atoms.py` and expected its old array result. The
RFdiffusion3 handoff retained names ranked before Boltz affinity standardization;
count-only checks could not reconcile changed chemical state/names. Ligand
self-consistency rejected otherwise valid PDB row permutations. NESSO's native
parser names its heavy-atom molecule differently from Boltz's hydrogen-added
canonical ranking, but its current adapter needs no external atom indices.

## What was done

- Added a strict local resolver using the installed Boltz affinity standardizer,
  hydrogen addition, canonical ranks, stereo assignment and the existing
  MMFF/contact-spread convention. It refuses missing/failed standardization,
  invalid/disconnected molecules or unusable names/conformers. The original
  input, actual standardized SMILES, names/elements, mapping signature and
  RDKit/parser identity are saved in `ligand_atom_map.json`.
- All NISE stages receive the same explicit Boltz-affinity chemical state.
  This corrects the previous RFdiffusion3/NESSO discrepancy; it is recorded and
  described in the UI rather than silently treated as unchanged input chemistry.
- Added native labelled molecule depiction and per-atom None/Bind/Expose
  controls, contact distance and retained-accessibility threshold. The diagram
  displays the standardized molecule and verifies its atom symbols/order against
  the resolver. Conflicting, stale or wholly exposed selections block submission.
  Changing SMILES clears selections; changed mapper signatures require explicit
  reselection. Request decoding preserves older workspaces with no requirements.
- RFdiffusion3 receives explicit hotspot/exposure conditions. Its original atom
  map remains intact; input-order/element correspondence translates selections
  and maps NISE reference copies into Boltz names. The translation is audited
  through preparation/generation receipts. Existing scientific worker reuse,
  batching and model scheduling were not changed.
- Replaced count-only Boltz ligand acceptance with exact name/element checks,
  including replayed predictions. Ligand RMSD now matches identities rather
  than requiring the same PDB row order. Missing/duplicate/changed identities
  still fail.
- Added per-candidate positive contact and per-atom exposure checks before all
  sequence-bearing refinement/gate/expansion/optimisation advancement. Automatic
  initial contacts exclude selected exposed atoms. Pocket restraints remain off
  after refinement, as upstream. Cycle-00 backbones remain proposals.
- Exposure uses RDKit FreeSASA, Shrake–Rupley, a 1.4 Å probe and explicit elemental
  van der Waals radii on heavy atoms. It compares each atom's complex SASA with
  its isolated-ligand SASA at the same conformation. The adjustable 50% threshold
  is a new experimental geometry criterion, not a validated biological default.
  Internally inaccessible atoms (≤0.1 Å² unbound SASA) fail an exposure request.
- Recorded rejected candidates and measured failures in candidate JSON plus
  `atom_checks.csv`, including graceful failed-run exits. NESSO checks its own
  prepared ligand graph/state and records its native names separately using
  its upstream naming function; no Boltz indices are supplied to NESSO.
- Kept NESSO screening in optimisation only. Initial X-masked sequences are
  unsuitable for this sequence-screening adapter; earlier screening could begin
  after LASErMPNN but needs per-lineage shortlists and effectiveness/cost validation.
- Extended the shared request schema (MCP v15 / bridge 1.9.0), updated upstream
  adaptation notes, docs, changelog and local beta build number 28.

## Results

No performance measurements — implementation and functional fixtures only.

- Nine new atom tests passed, including exact labels from the actual Boltz
  parser on the fluorescein example, charged molecules and stereochemistry;
  selected pocket constraints accepted by the parser; strict failed
  standardization/stale map handling; synthetic exposed/buried geometry;
  reordered/mismatched ligand identities; failed requirements excluded from
  advancement and retained in reports; separate NESSO native naming.
- Real installed NESSO ligand preprocessing, without model loading, passed
  graph/state/name auditing for CCN and the 31-heavy-atom fluorescein example. It returned C1/C3/N2 where Boltz's matching
  chemical state uses C9/C10/N8, confirming names cannot be interchanged.
- Seven upstream-funnel fixture tests, three RFdiffusion3 preparation/resume
  tests (including selected hotspot/exposure conditioning), nine NISE contract
  tests and eleven NESSO screening/resume tests passed.
- Six executable Swift contract harnesses passed, including saved atom choices,
  old workspace migration, conflicting choices and invalidation after changing
  the molecule. Final debug Swift build passed.
- Final release build, packaged-resource checks and strict ad-hoc signature
  verification passed. ZIP/DMG SHA-256 checks and hdiutil verification passed.
  The read-only mounted DMG matched all 391 app entries (hashes, modes, symlinks),
  reported build 28 and was unmounted.
- Outputs: `build/iProteinStudio.app` and
  `build/unsigned-beta-0.2.0-28/iProteinStudio-0.2.0-unsigned-beta-apple-silicon.dmg`.
  This is a local dirty-tree beta, not a published release.

## Decision and rationale

Use Boltz affinity's chemical state explicitly across all stages, depict that
state directly and keep engine-specific names separate. A substructure-match
guess against an altered charged/tautomeric input would risk constraining the
wrong atom. Use the existing RFdiffusion3 conditioning and standard FreeSASA
geometry calculation rather than pretending Boltz or the NESSO affinity score
has a negative solvent-exposure restraint. Geometry checks are necessary even
when a generator was conditioned, because model conditioning is not a guarantee.

## Reproduce

```bash
NANOHUNTER_ROOT="$HOME/.iproteinstudio" "$HOME/.iproteinstudio/venvs/NanoHunter_boltz/bin/python" Tests/test_nise_atoms.py
NANOHUNTER_ROOT="$HOME/.iproteinstudio" "$HOME/.iproteinstudio/venvs/NanoHunter_boltz/bin/python" Tests/test_nise_science.py
NANOHUNTER_ROOT="$HOME/.iproteinstudio" "$HOME/.iproteinstudio/venvs/NanoHunter_boltz/bin/python" Tests/test_nise_rfd3.py
python3 Tests/test_nise_contract.py
python3 Tests/test_nesso_screen.py
python3 Tests/run_swift_contracts.py
swift build
release/release_app.sh --unsigned-beta --allow-dirty
```

The exposure API is documented at
[RDKit rdFreeSASA](https://www.rdkit.org/docs/source/rdkit.Chem.rdFreeSASA.html).
Logs for this pass are under `/private/tmp/studio-nise-*` and
`/private/tmp/studio-nesso-regression.log`.

## Limits and what was not tested

No new real-model campaign, binding experiment, throughput or accuracy claim.
Model boundaries in funnel/diffusion tests remain fixtures; parser and geometry
tests execute real CPU implementations. No complete neural NESSO score in this
pass, and no early-stage NESSO screening implementation or validation. Solvent
probe accessibility does not prove access for a large conjugated partner.
No interactive GUI/VoiceOver, M1-specific installation, Developer ID signing,
notarization or public release. Existing jobs keep their saved code snapshots;
the new checks apply to new runs.

## Next

Use a declared bounded real-model campaign before
claiming ligand-conditioning efficacy or choosing a scientifically validated
exposure threshold. Compare early NESSO screening only after preserving lineage
diversity and recording an unscreened reference.
