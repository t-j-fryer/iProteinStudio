---
entry: 0080
title: Add fail-closed target templates to iterative design
date: 2026-09-03
author: gpt-5-codex
type: implementation
status: complete
machine: Apple M4 Max, 40-core GPU, 64 GB unified memory, macOS 26.x
tags: [iterative-design, boltz, protenix, intellifold, templates, ui, mcp, provenance]
---

## Context

Iterative design predicted the target afresh in every cycle. This is useful for
blind evaluation, but a target whose untemplated prediction drifts from a known
experimental or trusted fold can steer optimization against the wrong surface.
The requested product distinction was ordinary **Guide target fold** in the main
form and, if validated, a stronger coordinate restraint under Advanced.
OpenFold-3 was explicitly outside the iterative-design scope.

## What was done

- Added project-owned PDB/CIF/mmCIF import to the protein-target form. Guide mode
  is visible normally.
- Restricted ordinary guidance to upstream implementations with an explicit,
  validated structure route: Boltz 2.2.1, Protenix v2.0.0, and IntelliFold v2
  Flash/full. Protenix Mini/Constraint fail before launch rather than ignoring
  the file.
- Applied templates only to target chains B/C/... in design cycles. Binder A has
  an explicit empty Protenix template list, and post-check complex and binder-
  alone refolds strip all template metadata so their validation remains blind.
- Copied the source into each campaign, recorded its SHA-256 and prediction
  derivative in `target_template_provenance.json`, and made resumes reject a
  changed or non-reproducible artifact.
- Added a Boltz-specific derived mmCIF. Its pinned Gemmi 0.6.5 conversion fills
  missing entity sequence metadata in atom-only PDBs while preserving the
  checksummed original. This was necessary because Boltz's advertised PDB route
  raised an `IndexError` on the bundled atom-only 1CTX chain without `SEQRES`.
- Added Protenix v2 chain matching, a 70% identity/coverage safety boundary,
  inline mmCIF template JSON and per-cycle mapping receipts.
- Added a deterministic IntelliFold adapter. It matches query target chains at
  the same 70% identity/coverage boundary, normalizes PDB/mmCIF, writes paired
  query-MSA and HMMsearch-style A3M sidecars, and uses IntelliFold's explicit
  `template:` field only on target entities. Repeated identical target chains
  share one upstream entity/template; binder A receives IntelliFold's explicit
  `-1` no-template sentinel.
- Added a narrow runtime featurizer policy for content-addressed local template
  IDs. It bypasses the database-search duplicate/date filters only for IDs in
  the checksummed campaign manifest. It also suppresses upstream's unrelated
  optional full PDB template-database download; the user-supplied template
  bundle is self-contained.
- Fixed IntelliFold's upstream `template_id=-1` loader mismatch: the binder's
  synthetic `templates/-1_hmmsearch.a3m` path is removed at entity creation,
  while the checksummed target alignment remains intact.
- Added pinned Kalign 3.3.2 provisioning for Protenix template alignment. Setup
  verifies the official source archive SHA-256, compiles it with Apple clang,
  installs it transactionally beside Protenix, verifies the version, and the
  inference adapter passes its exact managed path. Setup detection now marks a
  Protenix runtime without this dependency incomplete.
- Removed the proposed strong Boltz coordinate restraint from the GUI and MCP,
  and made the CLI reject it actionably. Two controlled MPS samples produced
  reproducible target peptide breaks, whereas the same seed in Guide mode
  produced valid geometry.
- Extended the immutable MCP plan/broker schema with the same explicit fields
  and compatibility rules. Raw command flags remain reserved so an agent cannot
  bypass staging or scheduling policy.
- Documented the CLI and MCP behavior and extended command, runner, Protenix,
  YAML-preservation, snapshot, package-resource and MCP contracts.

## Results

No predictor performance comparison was made — these are implementation,
compatibility, and output-quality acceptance checks.

| Condition | n | Metric | Value |
|---|---:|---|---:|
| atom-only bundled 1CTX PDB, direct upstream Boltz parse | 1 | result before normalization | `IndexError` |
| normalized 1CTX mmCIF, Boltz Guide parse | 1 | mapped template records | 1 target / 0 binder |
| Protenix v2 inline target template | 1 | upstream featurizer errors | 0 |
| IntelliFold aCbx local template | 1 | matched target / binder template | 71 residues / none |
| IntelliFold explicit-template preprocessing | 1 | upstream preprocessing result | pass |
| cycle YAML rewrite | 1 design/post contract | ordinary fields preserved / post template absent | pass / pass |
| MCP bridge suite | 14 tests | passing | 14 |
| Boltz 2.2.1 Guide inference | 1 | target C-alpha RMSD / max target C-N | 2.819 A / 1.344 A |
| Protenix v2 Guide inference | 2 | successful full predictions | 2 / 2 |
| Protenix v2 Guide, rebuilt managed runtime | 1 | iPTM | 0.5644 |
| Protenix v2 Guide, first accepted sample | 1 | target C-alpha RMSD / max target C-N | 2.109 A / 1.334 A |
| IntelliFold v2 Flash Guide inference | 1 | target C-alpha RMSD / max target C-N | 2.482 A / 1.370 A |
| Boltz 2.2.1 Strong, threshold 2.0 A | 2 | geometry-valid structures | 0 / 2 |
| Boltz Strong repeat, target B | 1 | broken C-N links | 7 (maximum 5.68 A) |

The normalized 1CTX output was byte-identical across two independent
conversions. The final full Swift package build completed successfully in
42.83 s and the production app build in 31.36 s using the installed compiler's
matching macOS 15.4 SDK; these are build observations, not predictor-performance
claims.

## Decision and rationale

Guide mode is the only released option because it supplies known target-fold
context without turning coordinate adherence into an optimization force. The
proposed Boltz Strong mode was not merely lower quality: the geometry validator
rejected both samples for multiple target-chain peptide breaks. A hidden
Advanced control would still let a novice launch scientifically invalid work,
so the mode is unavailable until an upstream/runtime change passes the same
acceptance test.

Independent validation deliberately remains untemplated. Reusing the target
template for the complex post-check would make target recovery partly circular;
templating binder A would invalidate binder-fold recovery entirely. Pinned
IntelliFold accepts an HMMsearch-style alignment referencing an mmCIF rather
than a PDB/CIF directly. Studio now performs that deterministic conversion and
records the query-to-template chain mapping instead of asking the end user to
construct database-search artifacts.

## Reproduce

```bash
cd /Users/thomasfryer/iProteinStudio
bash Tests/test_iterative_cli_contract.sh
bash Tests/test_iterative_results_ui_contract.sh
"$HOME/.iproteinstudio/venvs/NanoHunter_boltz/bin/python" Tests/test_workflow_pipelines.py
python3 Tests/test_mcp_bridge.py
bash Tests/test_installer_hardening_contract.sh
bash Tests/test_installer_component_contract.sh
python3 Tests/test_installer_lock_contract.py
CLANG_MODULE_CACHE_PATH=/tmp/iproteinstudio-clang-cache \
SWIFT_MODULE_CACHE_PATH=/tmp/iproteinstudio-swift-cache \
SDKROOT=/Library/Developer/CommandLineTools/SDKs/MacOSX15.4.sdk \
swift build --triple arm64-apple-macosx15.0 \
  --scratch-path /tmp/iproteinstudio-template-build
```

The parser checks and full predictions used the installed Boltz 2.2.1,
Protenix 2.0.0, and pinned IntelliFold runtimes, not reimplemented schemas.
Each accepted run used one 20-residue random binder, the bundled 71-residue aCbx
target and its supplied MSA, one diffusion sample, and no optimization cycles.
The target RMSDs above are Kabsch-aligned C-alpha RMSDs to the supplied target
template. The Protenix installer was then run end to end and a second full
prediction succeeded using the newly built managed Kalign binary.

## Limits and what was not tested

- The implementation was not exercised on the user's M1 MacBook.
- These are engine-path acceptance tests, not binder-success benchmarks. The
  random 20-residue binders and their iPTM values must not be interpreted as
  evidence for design quality.
- The 70% Protenix mapping guard is a conservative product safety threshold, not
  a measured design-success cutoff. The same guard is used by IntelliFold. It
  is intended to reject an accidentally mismatched target, not rank template
  quality.

## Next

Repeat the three Guide acceptance samples on the M1 MacBook before calling the
feature cross-generation complete. Reconsider strong coordinate restraint only
after an upstream/runtime change produces valid target geometry under the same
validator.
