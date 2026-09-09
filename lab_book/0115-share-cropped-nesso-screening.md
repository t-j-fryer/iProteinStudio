---
entry: 0115
title: Share cropped-interface NESSO screening across ligand design workflows
date: 2026-09-09
author: Codex
type: implementation
status: complete
machine: Local Apple Silicon macOS developer machine; deterministic model fixtures
tags: [nise, rfd3, predictors, correctness, provenance, ui]
---

## Context

The user accepted the recommendation to use NESSO's pocket-cropped protein–ligand
entropy and requested optional NESSO screening plus top-X structural verification
for Protein Hunter and RFdiffusion3 ligand designs. They explicitly chose
**completed-campaign ranking** for Protein Hunter, not screening within cycles.
This corrects the full-entropy choice in [[0114-nesso-placement-confidence-ranking]].

## What was done

- Shared `nesso-pbind-placement-v2`: P(bind) + (1 − `entropy_crop_pl`), excluding
  cropped entropy outside (1e-6, 1]. Full entropy remains diagnostic. NISE initial
  and optimization screens use the corrected contract. Old results keep their
  recorded policy; existing selection receipts are not silently re-ranked.
- Added shared native `LigandNessoOptions` and controls, off by default and dormant
  for protein targets. Shortlist maximum defaults to 20; verifier options are
  Boltz, IntelliFold Flash/full, Protenix Mini/v2 and OpenFold3. Missing components
  block launch. RFdiffusion's inactive standard verification settings are cleared
  from its execution payload while retained in the saved project form.
- Added `scripts/nise/ligand_screening.py`: CSV adapters preserve PH run/cycle or
  RFD3 backbone/derivative identities, exclude PH cycle 00, screen all candidates,
  reject invalid placements, and forward a deterministic global top-X shortlist.
  Repeated sequences remain independent designs. PH caps apply per engine campaign.
- Reused pinned resident NESSO+ESM and the shared RFD3 predictor adapters/scheduler.
  NESSO closes before folding. Verification uses explicit empty MSA, exact SMILES,
  and no pocket/template restraint, affinity head, or apo stage. NISE's separate
  Boltz atom and structure checks are unchanged.
- Broker preflight freezes code, selected checkpoint/data and script provenance,
  validates installation and preserves the exclusive execution lease. PH appends
  a second step; RFD3 routes MPNN output to the shared screen instead of standard
  all-sequence Boltz verification. Public MCP design schemas are unchanged.
- Durable scores, selection, per-fold receipts and result reports support interrupted
  runs. Unreceipted fold directories are quarantined before retry. Engine-batch
  receipts include NESSO's nested artifacts. Tests wait for worker exit as well as
  terminal state before resuming, eliminating an observed test race.
- Added native result groups, complete score/rejection CSV, progress messages and
  `docs/NESSO_SCREENING.md`. NESSO and structural confidence are separate; no new
  automatic hit or ligand-pLDDT claim is made.
- Preserved stereochemical SMILES backslashes through both real YAML parsing and
  OpenFold's lightweight query adapter by writing single-quoted ligand SMILES.
- Built local unsigned beta 0.2.0 build 31, MCP resource version 18.

## Results

No measurements — implementation and fixture validation only. No throughput or
biological ranking performance was measured.

Passed: 13 shared-screen tests; 18 NESSO screen/worker tests; 8 NISE science
fixtures; 11 native broker tests; 7 engine-batch broker tests; 17 MCP tests;
3 existing predictor scheduler tests; workflow pipeline fixtures; all six Swift
contract harnesses. Swift build passed. Tests cover ordering, cropped-vs-full
ranking, rejection, finite bounds, per-candidate resume, partial fold completion,
changed source/artifact/dependency rejection, full-checkpoint requirements,
MSA policy, stereochemical SMILES, native persistence and result separation.

The first sandboxed Swift build could not populate compiler caches and reported
an SDK/compiler mismatch; the normal-cache build passed. The MCP local gateway
test needed loopback access; it passed with that access. Neither was a scientific
model failure. Final package verification is recorded below.

## Decision and rationale

The [NESSO output guidance](https://github.com/recursionpharma/nesso/blob/main/docs/prediction.md#output-files)
recommends cropped interface entropy and warns about zero values. The guard 1e-6
is an explicit numerical policy, not a biological cutoff. We retain the requested
sum as an experimental screen, not a calibrated probability or pLDDT substitute.

A post-campaign PH stage preserves its validated inner-loop science. A shared
stage avoids separate ranking and resume implementations for two tabs. RFD3's
NESSO route selects one structural verifier instead of implicitly adding all
standard Boltz/apo work; the UI explains this and preserves the inactive form.

## Reproduce

From the repository root:

```bash
python3 Tests/test_nesso_screen.py
"$HOME/.iproteinstudio/venvs/NanoHunter_boltz/bin/python" Tests/test_ligand_screening.py
"$HOME/.iproteinstudio/venvs/NanoHunter_boltz/bin/python" Tests/test_nise_science.py
"$HOME/.iproteinstudio/venvs/NanoHunter_boltz/bin/python" Tests/test_workflow_pipelines.py
python3 Tests/test_desktop_jobs.py
python3 Tests/test_iterative_engine_batch.py
python3 Tests/test_mcp_bridge.py
python3 Tests/test_rfd3_predictor_scheduling.py
python3 Tests/run_swift_contracts.py
swift build
bash release/release_app.sh --unsigned-beta --allow-dirty
```

## Limits and what was not tested

No real NESSO, ESM, RFdiffusion3 or structure-predictor inference was launched.
No new large campaign, ligand-binding validation, throughput benchmark, M1
installation or GUI interaction test was performed. Exact selected neural-model
outputs and scientific ranking effectiveness require a separately governed
small end-to-end campaign before large runs. The new optional screens have no
apo checks or atom-exposure gates in the verification fold; earlier design
restraints do not certify that new fold. Public MCP iterative/RFD3 schema
exposure remains outside this native UI implementation.

## Package verification

Debug and release Swift builds passed. The packaged-resource contract and strict
ad-hoc code-signature verification passed. All 168 source resources under the
pipeline, RFD3 preparer and RFD3 overlay matched their packaged hashes. No model
weight files were present. Both archive SHA-256 checks passed; `hdiutil verify`
validated the DMG. A read-only mounted DMG matched all 393 app entries, including
bytes, modes and symlinks. No app was published or installed on another Mac.

Artifacts:

- `build/iProteinStudio.app`
- `build/unsigned-beta-0.2.0-31/iProteinStudio-0.2.0-unsigned-beta-apple-silicon.dmg`
- `build/unsigned-beta-0.2.0-31/SHA256SUMS.txt`

This is a dirty-tree local-test build with ad-hoc signing, not a notarized public
release. The DMG device needed filesystem-sandbox escalation to mount read-only.

## Next

Validate a small ligand campaign through the governed bridge before a large
scientific campaign; test installation and the new controls on the user's M1.

