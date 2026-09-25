---
entry: 0191
title: Transfer the pre-affinity biotin cohort between Studio installations
date: 2026-09-25
author: Codex
type: implementation
status: complete
machine: Local Apple-silicon development Mac; no inference benchmark
tags: [nise, portability, ui, checkpoints, nesso, psichic]
---

## Context

The user requested the 1,491 geometry-passing cycle01 candidates from the active
biotin campaign for another Mac's iProteinStudio NISE tab. They explicitly chose
to resume Phase 0 screening/refinement/seed selection, not start Phase 1 directly.
Earlier cycle00 restart support could not express this boundary.

## What was done

Added `scripts/nise/cohort_transfer.py` with an explicit versioned
`phase0.cycle01.after_geometry.before_affinity` boundary. Export selects
`geometry_passed`, not later affinity-dependent `passed` or `final_eligible`.
It exports sequences, source references, validated structures, original geometry
diagnostics, structure-stage receipts and pre-affinity native caches. Earlier
p(bind), rankings and advancement decisions do not enter the new campaign.

Added the native NISE import picker and count preview. Ligand/geometry settings
are loaded and locked; screening engine and subsequent search controls remain
editable. The controller copies the package into a new run. The desktop broker
validates and fingerprints every required asset, and uses the existing
stage-directory resident route under the normal queue/lock/provenance contract.
No new inference scheduler or alternate launch route was introduced.

The search skips generation and first-round MPNN sampling, screens every imported
sequence with NESSO or PSICHIC, reuses selected folds, rechecks geometry and runs
selective Boltz affinity before the normal early gate and remaining Phase 0.
Boltz ligand pLDDT/100 + P(bind) remains the objective. This is not a replacement
of Boltz by either screening model.

Native RDKit molecules travel as base64 native binary JSON, not Python pickle.
Boltz stores `pocket=None` as a NumPy object scalar. Export replaces it with a
numeric marker, and import reconstructs that known local value after loading all
portable arrays with `allow_pickle=False`. Unknown object arrays are rejected.
Native caches and receipts are reconstructed per candidate and resume safely.

The source run, running application and installed runtime were not changed.
No weights were copied or distributed; no model inference was launched.

## Results

- Exact cohort: 1,491 candidates, 1,491 unique sequences, 712 original lineages.
- Package tracks and hashes 20,099 files.
- Full relocated-package test loaded all 1,491 predictions through the real
  BatchBackend with no pending inference. All 8,946 NPZ caches matched the source
  arrays exactly after round-trip conversion. A second materialization reused
  every receipt.
- 61 NISE tests passed, including full-cohort screening, lineage preservation,
  skip/replay boundaries, molecule round trips, corruption/path/pickle rejection,
  and broker asset binding for both NESSO and PSICHIC.
- Archive CRC and every manifest file hash verified; no weights or `.pkl` files.
- Release app build passed; packaged-resource contract and deep strict ad-hoc signature verification passed. Matching source hashes verified in the packaged scripts. DMG integrity verification passed.
- No performance measurements or scientific outcome claims.

Evidence is under `lab_book/artifacts/0191-phase0-cohort/`. Export is
`build/transfers/Biotin-Phase0-1491.zip`; the archive audit records its hash and size.

## Reproduce

```bash
NANOHUNTER_ROOT="$HOME/.iproteinstudio" "$HOME/.iproteinstudio/venvs/NanoHunter_boltz/bin/python" -m unittest discover -s Tests -p 'test_nise_*.py'
"$HOME/.iproteinstudio/venvs/NanoHunter_boltz/bin/python" Sources/iProteinStudio/Resources/pipeline/scripts/nise/cohort_transfer.py verify build/transfers/Biotin-Phase0-1491
```

Source run: `~/.iproteinstudio/projects/test2/nise_runs/nise-3ea5fa63a1effece`,
job `job-221c7d6db092`. Manifest records its config and original receipt hashes.
The standalone full relocation audit script is saved with the evidence.

## Limits and what was not tested

No receiving-Mac inference, real NESSO/PSICHIC scoring, affinity-head execution or
GUI interaction smoke was performed. Existing engine qualification remains
separate. This schema supports Protein Hunter first-refinement cohorts with
explicit hotspots, not arbitrary RFD3/upstream exports. Backward compatibility
requires the updated app; old apps do not offer this import. Model/runtime
incompatibilities fail explicitly rather than silently refolding or substituting
an engine. The exporter reads trusted local native caches; it is not an arbitrary
pickle reader for third-party files.

This is a local, uncommitted test distribution built with the current shared
working tree, not a published GitHub/Sparkle release.

## Local app artifact

`build/transfers/iProteinStudio-NISE-cohort.dmg` contains app version
0.2.6-cohort1 (50), development/ad-hoc signed. No installed app was replaced.
Initial Swift Build attempts hit a sandbox-restricted debug-symbol generator and
then stalled in the SDK stat-cache helper. Only the build processes started for
this task were stopped. The final build used SwiftPM's native build system and
no debug symbols, and completed successfully:

```bash
IPROTEINSTUDIO_VERSION=0.2.6-cohort1 IPROTEINSTUDIO_BUILD_NUMBER=50 \
CLANG_MODULE_CACHE_PATH=/private/tmp/ips-cohort-clang \
SWIFTPM_MODULECACHE_OVERRIDE=/private/tmp/ips-cohort-swift bash -c \
'swift() { command swift "$@" --build-system native --disable-sandbox -debug-info-format none; }; export -f swift; bash build_app.sh release'
```

The build workaround changes packaging only, not model execution or search
settings. Transfer instructions and archive hashes are in `build/transfers/`.
