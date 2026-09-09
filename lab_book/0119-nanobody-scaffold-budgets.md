---
entry: 0119
title: Add nanobody scaffold selection and budgets
date: 2026-09-09
author: Codex
type: implementation
status: complete
machine: local Apple Silicon development Mac; no inference benchmark
tags: [ui, nanobody, recovery, packaging]
---

## Context

The user requested multiple nanobody scaffolds per Protein Hunter run, with equal
or custom trajectory counts. They also supplied `rcsb_pdb_3EAK.fasta` and explicitly
chose to remove its terminal `RGRHHHHHH` purification tail. This extends the engine
checklist from [[0108-protein-hunter-engine-checklist]].

## What was done

- Added optional scaffold selections and equal/custom allocations to
  `DesignRequest`; legacy requests retain one scaffold with the existing budget.
  The UI presents checkboxes, an equal-split toggle and editable per-scaffold counts.
  It blocks empty selections, missing sequences and invalid allocations.
- Expanded `RunController` into engine–scaffold child campaigns. Every child saves
  its exact sequence, CDR positions and budget before submission. The existing
  sequential durable batch broker, execution lease, immutable snapshots and resume
  receipts remain authoritative. Version-2 batch descriptors record child budgets
  and engine/scaffold identities; the broker cross-checks manifests and CLI counts.
  Version-1 batches remain supported.
- Added 3EAK as an eighth available scaffold: 137 deposited residues become a
  128-residue domain. Saved original FASTA and SHA-256 provenance under the catalog's
  `sources/` directory. The existing CDR alignment resolver transferred boundaries
  from `7eow_caplacizumab` (77% identity): CDR1 27–37, CDR2 55–62, CDR3 100–117.
  These are inferred, not independently numbered. Catalog and runtime resolver
  output explicitly retain that provenance.
- The normal masked-CDR MSA generation/cache path applies to the new scaffold;
  there is no fabricated alignment or fallback. Deferred workflow updates now
  reload the scaffold catalog after staging succeeds.
- Documented behavior in `docs/NANOBODY_DESIGN.md` and the engine guide. Prepared
  build 32 release notes and extended the packaged-resource check for 3EAK.

## Results

No measurements — implementation only. Executed tests so far:

- Swift contracts: equal allocation 70/7, remainder allocation 72/7, custom budgets,
  saved-request round trips, empty selection, per-engine exclusions, exact child
  templates/commands and 21 engine–scaffold manifests. Existing failure-before-
  submission and other Swift request/recovery contracts passed.
- Nine real broker-worker tests with inert scripts passed, including version-1
  compatibility, variable budgets, rejection of malformed descriptors, interrupted
  child resume, cancellation and changed-output/provenance detection.
- Two catalog tests passed: all eight entries have valid ranges and sequences;
  3EAK hashes, exact tail removal and actual resolver output match provenance.
- Final debug Swift build and all six Swift contract harnesses passed after the
  catalog-refresh and empty-selection changes. `git diff --check` passed.
- Release build 0.2.0 (32) passed. The app's deep/strict code-signature check and
  packaged-resource contract passed. The packaged catalog, original FASTA,
  provenance, CDR resolver and batch broker match source bytes exactly.
  Local unsigned-beta app, ZIP and DMG were produced successfully; the local
  appcast carries the existing Sparkle archive signature. Nothing was published.
  ZIP/DMG SHA-256 checks and `hdiutil verify` passed.

Artifacts: `build/iProteinStudio.app` and
`build/unsigned-beta-0.2.0-32/iProteinStudio-0.2.0-unsigned-beta-apple-silicon.dmg`.

## Decision and rationale

Keep the existing total **per engine**, divided across scaffolds. Thus 70 with seven
scaffolds gives 10 each; adding a second engine gives 140 overall. Custom row edits
update the total, avoiding a second contradictory budget field. Equal splitting
assigns the remainder in selection order. Existing single-scaffold workspaces
retain their sequences and budgets rather than adopting every new catalog entry.

Use independent scaffold child campaigns rather than modifying the scientific
runner's trajectory loop. Each child retains validated resident/cycle-wave behavior
and durable recovery. Workers are not shared across child scaffold campaigns; no
cross-scaffold residency or speed improvement is claimed.

Record the existing resolver's inferred boundaries rather than inventing a new
antibody numbering method. The sequence import does not imply scientific validation
of its CDR assignment or design performance.

## Reproduce

From the repository root:

```bash
python3 Tests/run_swift_contracts.py
python3 -m unittest discover -s Tests -p test_iterative_engine_batch.py -v
python3 -m unittest discover -s Tests -p test_nanobody_scaffold_catalog.py -v
CLANG_MODULE_CACHE_PATH=/private/tmp/iproteinstudio-modules SWIFTPM_MODULECACHE_OVERRIDE=/private/tmp/iproteinstudio-modules swift build --disable-sandbox --skip-update
bash release/release_app.sh --unsigned-beta --allow-dirty
```

## Limits and what was not tested

No neural inference, first-use MSA request, independent antibody numbering,
wet-lab validation, manual GUI interaction or installation on another Mac was
performed. Inert workers establish orchestration behavior, not model performance.
The existing live design batch was not stopped or modified. Runtime staging waits
for the shared execution lease. Release artifacts are local test builds from the
existing dirty working tree, not published releases.

## Next

Validate the new scaffold's inferred CDR assignment independently before relying
on that assignment in a scientific comparison. Test first-use MSA generation and
a small inference run when compute is available.
