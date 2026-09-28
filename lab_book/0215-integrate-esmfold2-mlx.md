---
entry: 0215
title: Integrate portable ESMFold2 Fast and Full MLX
date: 2026-09-28
author: Codex
type: port
status: qualified; release deployment in progress
machine: Apple M4 Max, 40-core GPU, 64 GB unified memory, macOS 26.6.1
tags: [predictors, esmfold2, mlx, install, ui, mcp]
---

## Context

The user requested the recently tested Fast/Full MLX models across structure
prediction contexts, excluding Protein Hunter X-token hallucination, with portable
installation, upstream credit, and app/MCP/GitHub/releases updated. They explicitly
approved NESSO/PSICHIC objective folding routes as well as final refolds, and pausing
the biotin RFD3 campaign through its job manager for exclusive GPU qualification.

## What was done

Port c26b9af872158d822a8c95589708eedd3b9c0831 of Fausto Milletari and contributors'
unofficial MLX implementation is packaged with the existing validated Biohub CPU
feature/decode helpers. Strict offline loading: folding FP32, ESMC-6B BF16. Fast
3/50 and Full20/100 retain the tested loop/requested-step profiles. Full can use
per-chain A3M; Fast explicitly cannot. No affinity, template/pocket guidance or
X-hallucination claim. CPU preparation/decode and the upstream tiny CPU SVD are
explicit; learned inference is MLX/Metal.

Predict, target preparation, RFD3 sequence verification, Protein Hunter completed
sequence checks/post-screening, and NISE final checks offer both heads. NISE also
supports complete-sequence ESM folding when NESSO/PSICHIC drives selection. Initial
Protein Hunter X generation remains Boltz; RFD3 generation is unchanged. Postfold
geometry/RMSD and sequence-objective gates remain authoritative; NISE ESM inputs
are explicitly unrestrained and sequence-only. One session persists across later
producer requests when requested; the Boltz two-worker pool is not applied to ESM.

Native outputs commit atomically per input and publish live. NISE renames ligand
atoms by audited identical-SMILES input order and element identity, preserving
native CIFs and mapping receipts. Missing/changed identities fail. Predict resumes
through native receipt verification rather than trusting an outer chunk marker.
RFD3's orchestration request is preserved inside each atomic native output.

Portable CPython3.12.10 package uses MLX/MLX-Metal0.32.2, Torch2.11 and the tested
ESM3.4.0/Transformers4.57.6 helpers. Publisher-side setup clones the validated
runtime, changes only MLX packages, copies the pinned MLX source, and invokes
`tools/build_runtime_package.py` with standalone CPython and ESMFold2MLX source.
Client installation never invokes pip, Git or a compiler. Source and dependency
licences are retained; weights download separately from checksum-pinned upstream
revisions. Both heads share one ESMC-6B/CCD installation. Minimum macOS26.2 comes
from the portable native closure, not the app's macOS14 minimum.

## Results

All GPU checks used frozen preflight plans via MCP `job_start`, under the shared
exclusive lease. Baseline source HEAD was bb408add8bb84ef525196cd603f8999b38d93167;
each attempt freezes and hashes its modified adapter/helpers before execution.

| Attempt under Validation/output/esmfold2_app_v1 | Result |
| --- | --- |
| 20260928T232055735621Z / job-15735dfda8b1 | 12 Fast/Full monomer/complex/biotin inputs audited, 12 live records; interruption after first committed input, resume preserved it for each model |
| 20260928T232744260092Z / job-5897211048ca | Harness failure: passed Python None as MPNN designed-position text; no production algorithm defect, preserved raw failure |
| 20260928T232948734000Z / job-1032408486f3 | NESSO→Fast and PSICHIC→Full→geometry→real MPNN→later fold; one unchanged worker PID/load per route, checkpoint reuse, no affinity; Full real cached-MSA input passed |
| 20260928T233632153707Z / job-7c500a9a9e33 | Predict 2 seeds ×2 samples and resume passed; RFD3 predictions passed but result collection exposed a lost outer request receipt |
| 20260928T233850903285Z / job-98ff7fc1dcbf | Receipt fix qualified: Predict 4 samples/resume, RFD3 two inputs/result collection/resume all passed |

All these are execution/identity tests, not binding-accuracy evidence. The PSICHIC
fixture's low score would not pass the default campaign early gate; the handoff
fixture deliberately tests plumbing, not survival of that candidate.

Swift build and all13 Swift tests pass. Eight adapter/NISE regressions,66 NISE
checks,14 prediction checks,22 MCP bridge checks,10 runtime checks, portable
installer tests, shared adapter and RFD3 scheduling checks pass. Native NISE request
harness covers old-workspace migration, new engine validation and round-trip.
Both release shell contracts pass. Initial test invocations with incomplete test
interpreters failed on missing gemmi/biotite/ALA; rerun with the documented engine
environments passed. An initial package import under sandbox lacked Metal access;
normal package relocation imports passed, including spaces/Unicode paths.

Historical speed evidence remains [0214](0214-test-esmfold2-fast.md): two small
contexts on this M4 Max, about1.2–1.6× Fast/Full matched3/50 model-call speedup;
about4–13× comparing different default budgets. Excludes load/preparation/decode,
not a whole-campaign or general accuracy guarantee. No new throughput promotion.

## Decision and rationale

Expose opt-in alternatives with explicit capability limits. Keep structure
confidence separate from sequence-objective scores; Fast and Full are the same
model family. Use the upstream implementation rather than reproducing its model.
Separate atom mapping and checkpoint validation from model code. Preserve original
Boltz defaults and saved-run identities.

## Reproduce

`Validation/experiments/esmfold2_app_v1/preflight.py --mode adapter|routes|workflows --start`
uses the broker after its workflow guide and creates immutable attempt directories.
The manifest, coordinator, inputs, scripts, runtime/weight hashes and output audits
are retained. Shared cached MSA SHA256:
`c5c2ee22f8430f0144c602338fdb250d6ce69e1f851753bf8a8ce5046702f0ff`.
Publisher logs and installer/package checks: ignored `build/esmfold2-publisher`.

Public runtime release `runtimes-2026.09.28-1` is published. Archive SHA256
`539e742a71dd8dd13c7e8b1d6371622d0aca4250137b2fb1316853beab75b748`;
manifest `e01c09cc34165e20cf6252a8f6fd75d09d0878f11ee7fc01322b1d4e67f3b61f`.
Public portable installation into `build/esmfold2-publisher/install Ω space`
passed with PATH restricted to system bins (no developer tools). The archive
download, digest, relocation and imports passed. Large model weights were
preseeded from the hash-verified qualification assets; both head configurations
were deliberately removed, downloaded and verified from upstream. All three
component detector results were OK. This is not a fresh 25 GB model download.

## Limits and what was not tested

No fresh physical Mac, M1/M4 Pro24GB acceptance, long campaign/memory soak, broad
ligand/stereochemistry accuracy, or experimental binding validation. No complete
new RFD3 generation campaign or Protein Hunter design campaign rerun; existing
science remains covered by its regression tests, and the new prediction handoff
is qualified separately. Model numerical equivalence to reference PyTorch is not
claimed. Protein Hunter postchecks retain their existing per-task scheduling;
Predict/RFD3 directory reuse and NISE across-request residency are distinct.
Unsigned trusted beta is not Apple notarized. Do not imply universal speedup.

## Next

The initial0.2.12/build58/MCP33 assets finished uploading before the release
process could be interrupted. Its update feed was not published. A final
installation-path audit found the overlay version had not been advanced, and
portable RFD3 campaigns still launched prediction orchestration from the retained
engine package. Corrected new jobs to use app-frozen orchestration while retaining
the engine's generation helpers, runtime and weights. Small-molecule configs now
record both roots; both desktop and MCP plans freeze the app overlay helpers.
Existing saved jobs retain their original plans. Functional routing regressions
cover protein holo/apo and ligand checks; workflow contracts and22 MCP tests pass.
The4 RFD3 scheduling/routing tests and another Swift build pass. The correction
will ship as0.2.13/build59/MCP34 rather than replacing published artifacts.

Publish0.2.13/build59/MCP34, replace the open
app through normal staging, resume job-18ca87a890d9 from its original immutable
plan, and append deployment verification. No changes to that campaign's settings.
