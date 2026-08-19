---
entry: 0020
title: Make checking scope explicit and audit RFD3/Predict
date: 2026-08-17
author: codex-gpt-5
type: audit
status: complete
machine: Apple M4 Max, 40-core GPU, 64 GB unified memory, macOS 26.x
tags: [iterative-design, post-prediction, rfd3, predict, ui, resume, validation]
---

## Context

After the iterative GUI/CLI contract was unified in
`[[0019-unify-iterative-gui-cli-contract]]`, independent checking still had no
user-facing choice between the completed checkpoint and every cycle. The same
handoff requested a thorough audit of the RFdiffusion3 and plain Predict routes,
including the Swift request, emitted configuration, Python orchestration,
checkpoint/retry behavior and installed overlay.

## What was done

### Independent checking

- Added an explicit `Final only (cycle XX)` versus `All cycles (00–XX)` control.
- Kept checkpoint scope independent from the hit-threshold gate. The four exact
  CLI modes are `final`, `final-iptm`, `all` and `iptm`.
- All-cycle mode emits `--post-include-cycle00`; previously the label and cost
  estimate included cycle 00 while the runner would have silently skipped it.
- Updated the prediction estimate and preserved final-only as the default for
  projects saved before this control existed.

### RFdiffusion3

- Made protein campaigns honor SolubleMPNN versus ProteinMPNN, temperature and
  every requested sequence per backbone. Sequence variants now have unique
  predictor input names and matching scoring identities instead of overwriting
  one another.
- Canonicalized verification engines, removed duplicate Boltz variants, scoped
  P(bind) to small molecules, disabled potentials when Boltz is absent and made
  hidden MSA dependencies visible to Setup validation.
- Added fail-loud checks for target files, sequence/structure mismatch, chain and
  contig inspection, component codes, SMILES required by structure-file ligand
  jobs, numeric bounds and top-N exceeding produced sequences.
- Added ligand SMILES beside a supplied 3D pose: the structure supplies geometry,
  while sequence design and verification still need molecular chemistry.
- Fixed no-apo completion detection, detached-launch startup races, resumable
  ligand stages, whole-process-group cancellation and strict requested top-N for
  protein ranking.
- Made P(bind) disabling reach the generated Boltz YAML, and corrected the
  eager root detection that made six overlay commands fail from a source checkout
  before an explicit `--nanohunter-root` or even `--help` could be processed.
- Bumped `OVERLAY_VERSION`, ensuring an installed managed runtime receives the
  corrected scripts on app launch.

### Plain Predict

- Canonicalized engines and stripped Boltz-only steering/affinity settings when
  Boltz is not selected. IntelliFold model settings are emitted only when an
  IntelliFold backend is active.
- Fingerprinted parsed inputs and pairing/MSA policies. Editing them now makes
  old jobs stale and blocks Start until **Read sequences** is run again. Choosing
  a file clears pasted text and pasting clears the file, eliminating silent file
  precedence.
- Parsing and orchestration now use the macOS Python runtime; selecting AF3 no
  longer requires Boltz's Python environment merely to read a FASTA or drive an
  already-installed engine. Automatic protein MSAs still declare Boltz as the
  real generator dependency.
- Rejected an ambiguous shared protein plus ligand, invalid/duplicate engines,
  unsafe output names, duplicate chain IDs, invalid chains and negative
  throughput overrides before alignment/network work starts.
- A cached/generated A3M must match the exact query and contain a homologue.
  Query-only output now fails instead of silently weakening an alignment request.
- Added per-chunk checkpoints. Retry reuses only chunks whose marker names match
  and that contain a structure attributable to every job; exit zero with missing
  structures is treated as failure.

## Results

No performance measurements — implementation and correctness testing only.

| Condition | n | Metric | Value |
|---|---:|---|---:|
| Framework-free iterative Swift harness | 1 suite | scope/mode/seed/template/dependency assertions | pass |
| Framework-free RFD3/Predict Swift harness | 1 suite | validation/canonicalization/staleness/budget assertions | pass |
| Isolated iterative CLI fixture suite | 1 suite | final and all-cycle task selection plus runner contracts | pass |
| RFD3/Predict Python fixture suite | 1 suite | multi-sequence naming, A3M, retry, affinity, inspection and parsing contracts | pass |
| Bash syntax and Python compilation | 1 pass | every changed shell/Python helper | pass |
| `swift build` under `caffeinate` | 1 | production package build | pass |
| Release app build + strict signature verification | 1 | local app bundle | pass |
| Fresh app launch and managed-runtime staging | 5 files | source/installed byte comparison | pass |

## Decision and rationale

**Expose scope and gating as separate choices.** “Which checkpoints?” and “only
successful checkpoints?” answer different scientific and cost questions. A
single combined picker would hide combinations and make the command harder to
predict.

**Count concrete outputs, not successful process exits.** Protein-design
campaigns and batch folds can exit zero while under-producing records or
structures. Checkpointing an underfilled stage makes Resume permanently preserve
bad data, so every stage now verifies its promised cardinality and identity.

**Fail when requested evidence is unavailable.** A query-only A3M is not an
alignment, a stale parsed batch is not the visible form, and a protein sequence
that disagrees with its structure is not reproducible input. None is silently
substituted.

## Reproduce

```bash
cd /Users/thomasfryer/iProteinStudio

caffeinate -dimsu bash Tests/test_iterative_cli_contract.sh
caffeinate -dimsu /Users/thomasfryer/.iproteinstudio/rfd3/.venv/bin/python \
  Tests/test_workflow_pipelines.py

CLANG_MODULE_CACHE_PATH=/private/tmp/iproteinstudio-clang-cache \
SWIFT_MODULECACHE_PATH=/private/tmp/iproteinstudio-swift-cache \
swiftc -parse-as-library \
  Sources/iProteinStudio/Models/Predictor.swift \
  Sources/iProteinStudio/Models/RFD3Request.swift \
  Sources/iProteinStudio/Models/PredictionRequest.swift \
  Tests/WorkflowRequestContractHarness.swift \
  -o /private/tmp/iproteinstudio-workflow-contract
caffeinate -dimsu /private/tmp/iproteinstudio-workflow-contract

caffeinate -dimsu swift build
caffeinate -dimsu ./build_app.sh release
codesign --verify --deep --strict --verbose=2 build/iProteinStudio.app
```

## Limits and what was not tested

- No new GPU-heavy RFdiffusion3 or plain-prediction campaign was launched. The
  audit exercised production request/config/helper code with small filesystem
  fixtures, but did not spend hours or days regenerating scientific outputs.
- Cancellation process-group topology was corrected from the launcher source
  contract; a live multi-process GPU campaign was not terminated as a test.
- Structure-file ligands were validated through preparation contracts, not a new
  arbitrary-component Foundry inference.
- Plain Predict checkpoint reuse was tested with representative output layouts;
  every installed predictor's real nested output tree was not regenerated.
- No VoiceOver, keyboard-only, large-text or contrast pass was performed.
- No performance claim or benchmark was added.

## Next

Run one deliberately small real RFdiffusion3 protein campaign with two sequences
per backbone and one small plain-Predict batch, interrupt each once, and confirm
that Resume reuses only complete named outputs while the results browser exposes
every sequence variant and predictor independently.
