# 0263 — ESMFold2Fast-600M integration qualification

Date: 2026-10-26. Status: software qualification passed; release delivery pending.
Base commit 0295016. Hardware: Apple M4 Max, 40 GPU cores, 64 GB unified memory,
macOS 26.6.1. Exact pre-release source/runtime/asset identities are frozen in the
managed plans, rather than represented as a clean source commit.

## Changes

Add the separately pinned Synthyra 600M model/encoder to the native app, CLI,
bridge 48, custom recipe schemas, target preparation, sequence refinement,
RFD3 verification, RFD4 protein/nanobody search and NISE sequence-objective
folding/final checks. Install component `esmfold2_600` reuses the immutable MLX
runtime without ESMC-6B weights. Complete sequences only; X-token starts,
template/pocket guidance, MSA conditioning and affinity heads remain excluded.
Same model family as Fast/Full. Recommended workflows retain their Full/Boltz
choices. Chunk/cache settings and the low-memory preset are explicit and saved.
Memory admission is uncalibrated and requires a recorded override.

The live parser audit exposed duplicate `pred_min` representative copies and
prefix-related input cross-attribution. Exact input matching, original sample
selection and seed/model labels now preserve all samples once. RFD4 displays
confidence from the exact saved predictor file; MCP exposes those same metrics.
No affinity metric is fabricated. Unit/schema checks also caught one remaining
RFD4 Fast fallback and removed it before the actual beam run.

## Executed qualification

Manifest and audit programs: `Validation/experiments/esmfold2_600_integration_v1`.
Immutable requests, plans, outputs/receipts and logs:
`Validation/output/esmfold2_600_integration_v1` and the managed acceptance project.

- `job-7080ff5195b8`: 12 predictions, SUMO monomer/two-chain protein/ethanol
  complex, two seeds × two samples each. Audited exact chains/sequences, finite
  coordinates, pTM/ipTM/pLDDT/ligand pLDDT/ipSAE/PAE, model revisions and hashes.
  Native app parser and MCP overview each recover exactly three inputs/12 samples.
- `job-82d527108cec`: imported complete two-chain control, SolubleMPNN proposals,
  two-cycle beam width two, six 600M refolds. Target sequence preserved, multiple
  distinct proposals, correct checkpoint and interface scores. Resident model
  stays loaded across proposals. This tests refinement, not new RFD4 generation.
- `job-0f499b684953`: actual interruption after a committed input and managed
  resume. The eight committed files retained identical hashes and mtimes;
  all three final predictions passed the output audit.
- Completed prediction/beam submission replay returned their existing jobs;
  all 81/156 run files retained identical hashes and mtimes.
- Initially empty isolated installation of control + 600M succeeded from public
  pinned downloads, without preseeded models or 6B assets. Detection reports
  600M ready and Full/Fast/shared-6B assets absent. `job-279354e7231c` then produced
  an audited monomer in that root; `job-8b2b685f69d4` produced an audited two-chain
  target with automatic MSA correctly skipped. All used recorded memory overrides.
- Swift build and all ten native request/results harnesses passed. Dedicated
  600M tests cover model selection, schemas/custom recipes, installer dependency
  isolation, NISE/resident command routing and invalid input rejection. Adapter,
  CDR, profiles, Hunter, RFD4, NISE contract/objective, memory admission, MCP bridge,
  RFD3 scheduling and MSA regression suites passed. Skill validation passed.

## Failures and limits

Two compile errors from initial integration edits were corrected before the
passing build. Some test attempts lacked Gemmi/Biotite in the chosen interpreter;
reruns in the appropriate installed environments passed. Sandbox-only Xcode,
process-inspection and audit-log failures were rerun on the host. The legacy
Protenix link-existing shell harness fails its synthetic usable-state assertion
on both unchanged 0295016 and this source. Six of 12 legacy MCP composition
fixture tests fail on both versions because their fake runtime lacks the current
input/preflight contract. These baseline failures were retained, not hidden or
counted as passes. The new 600M custom-recipe test and actual managed plans pass.

No full NISE optimization campaign, AbMPNN nanobody campaign, RFD3 generation
campaign, long memory soak, physical 16 GB Mac, general accuracy/confidence
calibration, binding efficacy or whole-model CUDA parity is newly qualified.
These integrations reuse existing stages; they are experimental, not efficacy
claims. No default memory calibration or performance setting is promoted.
Prior Figure 2a evidence remains Lab0582/Validation0262. No model weights are
committed or packaged. Public app delivery and queue restoration are recorded
below once verified.

## Production restoration

After all bounded model tests, `job-1e0a8a779e14` was resumed with its unchanged
plan digest `1e0a8a779e14273c4cdcc57774da6febbebecc0c5796a32063b668df767cb6ed`.
It was the only active/queued job in the captured pre-test queue. Bridge 48 is
staged in the managed installation. Final MCP RFD4 overview contains six
600M proposals with pTM and interface metrics; the native results harness
passes against those same six outputs.
