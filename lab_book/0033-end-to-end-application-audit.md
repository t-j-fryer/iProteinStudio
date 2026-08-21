---
entry: 0033
title: Audit the rebuilt app and preserve explicit MSA policy
date: 2026-08-21
author: codex-gpt-5
type: audit
status: complete
machine: Apple M4 Max, 40-core GPU, 64 GB unified memory, macOS 26.x
tags: [predict, openfold3, intellifold, rfd3, ui, msa, regression]
---

## Context

The app had accumulated several rounds of workflow, viewer, installer and engine
work.  A broad release-oriented pass was needed across the rebuilt GUI, the
standalone managed runtime and the production command paths.  A recent failed
OpenFold prediction was especially important: its saved Predict input explicitly
said `msa: empty`, yet the adapter attempted a live MMseqs2 request.  This follows
the shared-MSA and method-matrix work in [[0022-share-msas-and-adopt-py2dmol]] and
[[0024-editable-numbers-richardson-and-method-matrix]].

## What was done

- Exercised all three workflow tabs, the minimum 1080 × 772 window, long-form
  scrolling, fixed navigation/action areas, Quick/Advanced setup, editable number
  fields, engine-dependent Boltz controls, Predictions Library, Activity, Engines
  and the nested py2Dmol result browser.  The viewer exposed Style, Save and Rotate;
  the default style remained Cartoon with Richardson colouring.
- Checked prediction-library discovery and opened a completed multi-engine run at
  the minimum window size.  Structures and available pLDDT, iPTM, pTM and ranking
  metrics were visible without leaving the app.
- Added explicit accessibility names for Predict's engine checkboxes, cached-MSA
  toggle, Boltz potentials and small-molecule affinity control.  Removed stale UI
  copy that still referred to the retired IntelliFold JAX engine.
- Reproduced the OpenFold failure from the durable saved input.  The query builder
  treated an explicit `msa: empty` as if no policy had been supplied, then requested
  the server.  It also allowed a legacy positional target MSA to override an
  explicit per-chain choice.
- Made `scripts/openfold_query_json.py` preserve three distinct states: a real MSA,
  an explicitly empty/single-sequence MSA, and an unspecified policy that may use
  the server.  Mixed-chain inputs retain paths only on the chains that own them.
- Removed the older embedded query-builder copy from `nanohunter_run.sh`; iterative
  verification and standalone Predict now call the same implementation.  Added
  regressions for explicit single-sequence, mixed aligned/unaligned chains and
  runner/helper drift.
- Rebuilt and relaunched `build/iProteinStudio.app`, then verified that its staged
  copies in `~/.iproteinstudio` were byte-identical to the corrected source.
- Ran the complete deterministic source/CLI contract set and bounded production
  GPU jobs under `caffeinate -dimsu`.

## Results

All measurements below are single acceptance runs on the machine in the header.
They establish routing and completion, not comparative model quality.

| Condition | n | Metric | Value |
|---|---:|---|---:|
| Cached α-cobratoxin MSA, Boltz + Protenix Mini + Protenix v2 + IntelliFold v2-flash + OpenFold-3 | 5 folds | completed outputs | 5/5 |
| Same five-engine batch, one seed and one diffusion sample | 1 batch | wall time | 231.9 s |
| OpenFold-3, explicit `msa: empty`, server disabled | 1 fold | completed outputs | 1/1 |
| OpenFold-3 single-sequence acceptance | 1 fold | wall time | 56.2 s |
| IntelliFold full v2, cached α-cobratoxin MSA, 200 steps and 10 recycles | 1 fold | completed outputs | 1/1 |
| IntelliFold full-v2 acceptance | 1 fold | wall time | 315.2 s |
| RFdiffusion3 MLX, cached 65-residue binder fixture, 20 steps | 1 backbone | generated PDBs | 1/1 |
| RFdiffusion3 sampler | 1 backbone | sampler wall time | 0.912 s |
| Python/shell workflow, ligand, downloader and iterative contracts | 4 suites | passing suites | 4/4 |
| Swift iterative, workflow-request and result-discovery harnesses | 3 executables | passing harnesses | 3/3 |

The explicit single-sequence OpenFold query saved `use_msas: false`,
`use_main_msas: false` and no MSA path.  The experiment saved
`use_msa_server: false`; upstream reported that it constructed its intended dummy
query-only MSA, and a model CIF was produced.  The shared cached-alignment run
reported 1,087 MSA rows in Protenix and the IntelliFold logs confirmed the selected
v2-flash/full-v2 weights and ten recycles.

The RFdiffusion3 acceptance PDB contained 613 lines / 49,499 bytes.  Its metrics
reported 100% valid Cα geometry, 65 designed residues, zero motif drift and the
expected 71-residue target.

The rebuilt app satisfied `codesign --verify --deep --strict`.  Managed-runtime
detection returned `ok` for Boltz, LigandMPNN, AntiFold, IntelliFold, Protenix,
OpenFold-3, LASErMPNN and RFdiffusion3.

## Decision and rationale

An explicit single-sequence choice is a scientific input, not a recoverable cache
miss.  OpenFold must run its supported query-only route and must never silently
turn that choice into a server search.  Conversely, an omitted MSA field remains a
request for normal resolution.  Keeping these states distinct makes Predict,
target preparation and iterative verification reproducible.

The query conversion now has one owner.  Retaining an embedded shell heredoc would
make another policy drift likely, so the iterative runner delegates to the same
tested Python helper used by standalone prediction.

No release-blocking failure remained in the exercised routes.  This is not a claim
that every combinatorial input is bug-free; the standing known gaps in
`LAB_BOOK.md` still apply.

## Reproduce

```bash
cd /Users/thomasfryer/iProteinStudio

NANOHUNTER_ROOT=/Users/thomasfryer/.iproteinstudio \
  bash Sources/iProteinStudio/Resources/pipeline/setup_pipeline.sh --detect

/usr/bin/caffeinate -dimsu /usr/bin/python3 \
  /Users/thomasfryer/.iproteinstudio/rfd3_scripts/predict_batch.py \
  --config /private/tmp/iproteinstudio-audit-predict/config.json

/usr/bin/caffeinate -dimsu /usr/bin/python3 \
  /Users/thomasfryer/.iproteinstudio/rfd3_scripts/predict_batch.py \
  --config /private/tmp/iproteinstudio-audit-openfold-single.json

/usr/bin/caffeinate -dimsu /usr/bin/python3 \
  /Users/thomasfryer/.iproteinstudio/rfd3_scripts/predict_batch.py \
  --config /private/tmp/iproteinstudio-audit-intellifold-v2.json

/usr/bin/caffeinate -dimsu \
  /Users/thomasfryer/.iproteinstudio/rfd3/.venv/bin/python \
  /Users/thomasfryer/.iproteinstudio/rfd3/scripts/generate_backbones.py \
  --fixture /Users/thomasfryer/.iproteinstudio/rfd3/oracle/oracle_acbx_complete_acceptance.npz \
  --output /private/tmp/iproteinstudio-audit-rfd3-20260821 \
  --num-designs 1 --steps 20 --recycle 1 --batch-size 1 \
  --seed-start 210821 --precision bf16

/usr/bin/caffeinate -dimsu bash Tests/test_iterative_cli_contract.sh
/usr/bin/caffeinate -dimsu \
  /Users/thomasfryer/.iproteinstudio/rfd3/.venv/bin/python \
  Tests/test_workflow_pipelines.py
/usr/bin/caffeinate -dimsu \
  /Users/thomasfryer/.iproteinstudio/rfd3/.venv/bin/python \
  Tests/test_ligand_conditioning.py
/usr/bin/caffeinate -dimsu \
  /Users/thomasfryer/.iproteinstudio/rfd3/.venv/bin/python \
  Tests/test_verified_downloader.py

./build_app.sh release
codesign --verify --deep --strict --verbose=2 build/iProteinStudio.app
```

The three Swift harness compile commands remain those recorded in
[[0029-retire-untrusted-jax-metal-predictors]].

## Limits and what was not tested

- This was one small representative input per supported predictor/model variant,
  not a statistical structure-quality benchmark or an exhaustive cross-product of
  complexes, ligands, seeds, samples and sequence lengths.
- The RFdiffusion3 run re-used the validated cached α-cobratoxin fixture and tested
  backbone inference.  It did not repeat the hours-long full MPNN/predict/apo/rank
  campaign; that production path is recorded in [[0016-complete-campaigns-and-run-recovery]].
- Existing completed nanobody and protein campaigns were inspected and their
  command contracts re-run, but no new full nanobody campaign was launched in this
  pass.
- The live generic PDB ligand matcher passed on caffeine, aspirin, ibuprofen,
  glucose and acetate earlier in this same audit, but remote PDB availability is
  not controlled by the app.
- `swift test` still has no runnable XCTest/Swift Testing module under this
  CommandLineTools-only toolchain.  The production-file Swift harnesses are the
  executable regression mechanism and all three passed.
- Boltz reported its known PyTorch MPS fallback for one unsupported SVD operator;
  there is still no user-selectable CPU execution mode.
- VoiceOver reading order, keyboard-only traversal, large text, high contrast,
  reduced motion, interrupted GUI resume and signed/notarised distribution remain
  outside this pass or in the standing known-gap list.

## Next

Perform the deliberate GUI interrupt/quit/relaunch/resume acceptance described in
the top known gap, then a dedicated accessibility pass.  For model science, use
multiple targets and seeds before drawing any quality or performance conclusion
from the acceptance timings above.
