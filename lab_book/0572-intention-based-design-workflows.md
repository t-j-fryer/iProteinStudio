---
entry: 0572
title: Organize design by intention and add recommended workflows
date: 2026-10-26
author: Codex
type: implementation
status: complete
tags: [studio, workflows, rfd4, ligand, design, artwork]
---

## Request

Match RFD4's form to RFD3, expose small-molecule sequence searches, add six easy/
hard recommended binder workflows with target/hotspot/time inputs, organize custom
workflows by scientific intention, save custom workflow buttons, and generate
matching artwork. Existing unrelated work and production job snapshots remain intact.

## Implementation

Design home now has the six requested easy/hard buttons, minimal target/hotspot/
active-minute inputs, six intention cards, immediate NISE and original Protein
Hunter routes, and versioned saved workflow buttons. Saved buttons restore editable
settings and never start work. Existing workspace decoding remains compatible.
RFD4 uses RFD3's card layout, quick/advanced selector and fixed start bar; compatible
models and tasks are filtered by intention. An existing-structure optimization
choice opens partial redesign/partial diffusion rather than an unrelated de novo run.

Confirmed user choice: hard protein/nanobody starts with RFD4, then seven cycles of
SolubleMPNN/AbMPNN plus ESMFold2 Full, with four proposals/parent and four survivors.
Easy uses native RFD4 sequences plus Full. The simple nanobody route assembles the
previously audited 7XL0 apo framework and preserves its framework sequence while
redesigning CDR1/2/3. Target MSA auto resolves through the existing cache/server
policy; scaffold MSA comes from the selected framework. Custom alignments remain
explicit. Automatic molecule preparation reuses Studio's conformer routine and
checks graph, charge and stereochemistry before native input authoring.

Ligand fixed/iterative/greedy/beam routes reuse the existing NISE LASErMPNN sampler
and Boltz workers. Selection is P(bind) + ligand pLDDT/100, with all evaluated
proposals and ancestry retained. Native during-diffusion rollout beams remain
separate. Timed families checkpoint active execution (not queue/downtime), finish
the current atomic operation, retain partial-family candidates and resume by
verified receipts. The explicit existing memory override remains required for
uncalibrated RFD4 workloads; no admission bypass was added.

Six transparent ceramic-style icons were generated with `image_gen.imagegen`
using the existing NISE/backbone icons as style references. The originals were
copied without raster editing into `Resources/Brand/workflow-*.png`; prompts,
reference names and SHA256 identities are in `workflow-artwork-provenance.json`.

## Verification

Evidence: `Validation/output/studio_design_home_v1`, declared manifest and audit
script under `Validation/experiments/studio_design_home_v1`, Validation Lab0255.
Hardware: Mac16,6, Apple M4 Max, 64 GiB. This was technical acceptance, not a speed
or efficacy benchmark. Exact code/runtime/model fingerprints are in the broker
plans; no weights are copied into the repository.

- Swift build and the signed local app build pass. Twenty-eight bundled adapters,
  scaffold resources and icons match source hashes.
- All Swift and workspace navigation contract harnesses pass, including six preset definitions, seven-cycle
  proposal semantics, saved snapshot round trips, legacy request decoding and
  invalid-number rejection. Seven RFD4, four time/search, two real upstream native,
  two actual RDKit input tests and 24 bridge tests pass. CPU molecule cases include
  aromatic bonds, charge, explicit stereo and rejection of ambiguous/disconnected
  inputs. Syntax checks were not used as acceptance.
- Managed SUMO/7XL0 smoke: native RFD4 → AbMPNN → Full completes, with 29 mutable
  positions and unchanged framework/target sequences. MSA receipts are audited.
- Managed biotin smoke: one timed RFD4 family, two beam cycles, two proposals and
  two survivors produces six scored candidates with exact combined objectives.
  Broker cancellation after five completed proposals, then resume of the same
  immutable plan, preserves all five receipt hashes and completes the sixth.
- A six-second monomer budget stops during model setup with zero candidates and
  an explicit time-budget completion report. Unit tests also cover keeping an
  unindexed completed generation when the deadline occurs before the next stage,
  interrupted active-time accounting, and propagating real failures.
- Native UI inspected: Design home/artwork, hard nanobody minimal inputs, molecule
  customization, restricted Boltz/LASErMPNN controls, saving/reopening a custom
  button without compute, and persistence across app restart. A clearly named
  `Small-molecule beam · demo` button was retained from this UI check.

Failures are retained: unknown new test workspace (reused the existing acceptance
workspace), disconnected target singleton contigs (fixed contiguous segment
construction), missing ligand handoff import path (fixed and tested in the actual
Boltz interpreter), and Swift type-checker timeouts (split the RFD4 form into
smaller view sections). No completed raw run was edited. Production job `job-b3e3f8606412` is running again; `job-4df41f91d918` is queued behind it. Both original digests are unchanged and neither reports an error; final status is recorded in the evidence.

## Limits / not tested

No full seven-cycle efficacy experiment, broad chemistry/target study, production
memory soak, every model/condition combination, public release or portable runtime
publication. Timed scheduling currently processes one family at a time and has no
new throughput claim. The builder composes supported routes, not arbitrary graphs.
Whole-chain ESMFold2 X-token hallucination, retrospective adaptive depth, multi-cycle
RFD4 inverse/refold controllers and unqualified fusion experiments remain research
work (see the integration audit). This change does not promote those experiments
or new scientific efficacy claims.
