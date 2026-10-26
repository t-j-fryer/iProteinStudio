---
entry: 0490
title: Support original motif residue templates
date: 2026-10-21
author: Codex
type: implementation
status: complete
machine: Local Apple Silicon Mac; CPU input checks and development build only
tags: [rfd3, motifs, templates, boltz, native-protein, beta]
---

## Context

Following [[0489-implement-atomic-motif-beta]], the user asked whether isolated
motif residues can be used without a generated backbone, and requested support
for motifs extracted from native proteins. Representation and folding/design
capability must be distinguished: sparse coordinates are valid, but folding
still needs a full sequence and residue placement. Full source residue frames
also constrain more geometry than the benchmark's functional atom masks.

## What was done

- Added the GUI choice between generated RFD3 frames (default) and original
  benchmark residue frames, retaining identical RFD3 query placement and the
  immutable scoring reference. Added original PDB-entry links.
- Added CPU `source-guide` input export independent of any RFD3 root. Requires
  an explicit source-selector to query-position map and complete sequence. An
  optional native PDB/mmCIF is selected by original chain/residue identifiers;
  missing observed frames, identity changes and ambiguous selected conformers
  fail explicitly. Only selected residues enter the guide, in one common frame.
- Preserved source coordinate hashes, mappings and diagnostic motif RMSD.
  Native-protein import is a workbench operation; the GUI option uses released
  benchmark residues. Protein templates do not lock ligand poses.
- Audited all 41 cases: every one of their 172 selected residues has N/CA/C/O.
  Prepared and parsed all 41 as sparse Boltz templates without an RFD3 root.
- Downloaded the full public 13PK mmCIF from RCSB, retained bytes/hash/URL, and
  extracted the four benchmark residues. A single rigid selected-atom fit to
  the released benchmark is equal within floating-point precision. No full
  native coordinate downloads for the other 40 cases were performed.

## Mapping defect found and repaired

The earlier native sparse-template test in entry 0489 was insufficient. Boltz's
polymer parser aligns the observed sparse sequence against the full query and
can move residues among repeated amino acids despite correct label_seq_id.
For M0024_1nzy with artificial query positions 2/6/10/14/18/22, it mapped the
alanine at 6 to 3. This affects original and generated residue-frame templates.

Added a marked-file-only positional adapter. It executes upstream parser code
with explicit label_seq_id correspondence in place of sequence alignment;
native atom handling/masks remain upstream. It verifies the parsed positions.
Ordinary unmarked templates use the original parser. Only the beta resident
installs it; one preprocessing worker is required so a spawned worker cannot
lose the override. A real native YAML parsing test checks the resulting query
mapping. Exports record this required adapter and version; they are not safe to
assume correctly mapped in unmodified Boltz. Incompatible older template
receipts fail instead of being silently reused. Prediction helper scripts are
included in beta cycle provenance.

## Results

No inference performance measurements — implementation and CPU input checks only.

- 14 motif contract/geometry/export/orchestration tests passed. Fake model
  outputs exercise both template sources and the complete comparison budget;
  these are not scientific design results.
- 5 native CPU template/chemistry tests passed, including repeated-sequence
  correspondence through native Boltz YAML parsing.
- 1 managed bridge/provenance test passed.
- Resident regression suite: 14 tests run, 12 passed and 2 skipped by the
  existing suite. No model weights loaded.
- All 41 standalone source templates parsed with the corrected adapter.
  Native 13PK import also parsed successfully.
- Swift build, local development app build and app signature verification
  passed. The app remains at `build/iProteinStudio.app`, not installed/launched.
- `git diff --check` passed. No commit made; pre-existing work preserved.

Logs, source bytes, audit script, parsed-position inventory and hashes are in
`artifacts/0490-source-motif-templates/`. The `prepared/` directory retains the
small failing pre-adapter example; `mapped-prepared/` contains corrected inputs.

## Decision and rationale

RFD3 is useful for proposing a compatible scaffold and motif insertion map,
and supplying an initial backbone to inverse folding. It is not necessary to
represent disconnected motif residues in a file. Original frames are an
explicit alternative intervention; retain generated frames as the default.
Tip-only motifs are not automatically promoted to complete-residue templates.

M0630_1j79 selects just two protein atoms. Its residue template is usable, but
the existing selected-atom rigid-fit scoring guard is underdetermined. Record
null for that diagnostic and reject beta inference before execution rather
than report a fabricated zero/pass. A ligand-anchored guard needs qualification.

## Reproduce

Run `Tests/test_motif_beta.py` with the installed Protenix Python (Biotite),
`Tests/test_motif_beta_native.py` with Boltz Python, and
`Tests/test_motif_beta_bridge.py` / `Tests/test_resident_prediction_resume.py`
with the repository's ordinary test Python. Use `MPLCONFIGDIR=/tmp/motif-beta-mpl`.

Run `artifacts/0490-source-motif-templates/audit_sources.py CCD_CACHE_PATH`
with Boltz Python. It needs the retained `13PK.cif`; it performs no downloads
or model inference. CLI and mapping syntax are in `docs/MOTIF_BETA.md`.
Build with `swift build` and `bash build_app.sh debug`.

## Limits and what was not tested

The existing memory policy still blocks live inference; no profile or guard
was bypassed. No RFD3/MPNN/predictor model execution, native Protenix/IntelliFold
features, assay or throughput comparison. Correctly parsed sparse inputs do
not establish successful scaffolding. The original beta remains scientifically
unqualified as recorded in entry 0489. Native import currently requires the
benchmark's original chain/residue identifiers; arbitrary custom motif authoring
and its GUI, automatic assembly/conformer selection, and ligand variants remain
outside this change. No model weights or installed runtime were modified.

## Next

Qualify memory profiles and one real root with both designers, then compare
generated versus original residue-frame guidance using untemplated checks.
Qualify native Protenix/IntelliFold features and ligand-anchored low-atom scoring
before expanding automatic cycling support.
