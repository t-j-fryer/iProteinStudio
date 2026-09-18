---
entry: 0150
title: Compare pocket-only biotin replay and request batching
date: 2026-09-17
author: GPT-6 Codex
type: benchmark
status: complete
machine: Apple M4 Max, 64 GB unified memory, macOS 26.6.1 build 25G76
tags: [nise, boltz, performance, geometry, resident, validation]
---

## Context

Following [[0149-explain-biotin-boltz-timing]], the user requested pausing the
current biotin NISE campaign, replaying its completed inputs with physical/FK
potentials off but forced pocket restraints retained, then submitting the same
inputs as one request. Compare physical plausibility and time per prediction.

## What was done

Broker cancelled job-002ee4e5c61e at21:02:06UTC, preserving30 complete cycle00
receipts L000–L029. The1000-start campaign remains paused with its original
configuration and checkpoints unchanged. Normalized results_overview has no
optimization candidates; these are X-containing initializations.

Added a bounded private boltz_replay_validation planner/runner using the normal
immutable plan digest, script/model/input provenance, shared GPU lock and resident
Boltz worker. Freeze exact YAMLs, original preprocessing, atom map and structures.
No arbitrary commands exposed. One fresh resident model per new arm;30 singleton
requests, then one30-input request (native data-loader batch size1). Both retain
seed0, empty MSA,3 recycles,200 steps,1 output sample, FP32/MPS, force:true pocket,
contact guidance on, and no affinity head. Physical/FK guidance off changes
internal multiplicity from3 steering particles to1. Boltz2.2.1, torch2.13.0,
Lightning2.5.0, RDKit2026.3.5, NumPy1.26.4, Gemmi0.6.5.

Capture Python/NumPy/CPU/MPS RNG states at feature/prediction boundaries without
reseeding singleton inference; replay per input in the directory arm and verify
model tensor checksums. Original processed ligand conformers are held constant.
Native directory enumeration determines batch order; randomness remains paired
by input ID. Executed hyperparameters independently confirm physical/FK off and
contact guidance on. No app default or production scheduler was changed.

First pilot job-4317fffbe332 correctly failed on changed L001 model features:
Boltz ETKDG does not set randomSeed and batching produced another ligand conformer
(maximum raw coordinate difference10.223737Å). Preserve failed run. Corrected
pilot job-1029852023f5 froze original preprocessing; four folds completed with
matching input features and one model load per arm. Pilot excluded from timings.

Main plan plan-1fdba14287be8a93, digest
1fdba14287be8a932376c2aa01be5e9df519a6bee3c55bd7f98dec6fdcfa9236;
job-1fdba14287be completed all60 requested folds. Managed output
`test2/validation_runs/biotin-replay-efff2efa3233dd87`. All108 shared installed
Boltz code/checkpoint fingerprints match the original campaign plan. Raw outputs
and failed/interrupted units remain immutable and checksummed.

## Results

Thirty paired initializations per condition on the machine above. Times are
summed worker request durations divided by30, excluding startup. Original timing
includes original YAML/RDKit preprocessing; both replay arms reuse it, so the
original/replay contrast is not exclusively potential-computation time.

| Condition | Seconds / initialization | Pocket + exposure pass | Ligand stereochemistry correct | No severe protein–ligand overlaps |
|---|---:|---:|---:|---:|
| Original physical/FK on |48.6888|13/30|30/30|30/30|
| Pocket-only singleton |15.4844|11/30|19/30|28/30|
| Pocket-only one request |14.4290|11/30|19/30|28/30|

All90 structures pass backbone-continuity diagnostics and all pocket contacts.
Nonlocal protein severe-overlap-free counts13/9/9; ligand bond-length diagnostic
passes15/9/9. Mean ligand pLDDT33.90/33.31/33.32. Bond bounds use RDKit distance
geometry plus0.15Å; severe overlaps mean heavy-atom vdW overlap>1Å, not MolProbity
clashscore. Neither is a production acceptance threshold.

Ligand CIP assignment and independent signed-volume checks against each original
frozen input conformer agree at all270 assessed stereocentres. Physical/FK-off
has11 wrong-stereochemistry ligands: ten reverse all three biotin centres, one
reverses C31. Four (L009,L021,L027,L028) nevertheless pass existing hotspot/exposure
filters. A separate signed N–CA,C–CA,CB–CA volume check finds no reversed protein
Cα centres in any arm (only assessable non-glycine/non-UNK residues). One near-planar protein Cα centre appears in each pocket-only arm. The ligand
errors therefore cannot be explained by an overall reflected coordinate frame.

Batching reduces measured wall time by6.8159% here. Model-step means13.75 vs14.08s;
remaining request overhead1.73 vs0.35s. All30 singleton/batch contact/exposure
verdicts agree, as do the counted geometry outcomes. No PDB/confidence pair is
bitwise identical: aligned Cα RMSD median0.0005Å, maximum0.0420Å; ligand RMSD after
that alignment median0.0007Å, maximum0.0783Å. Maximum ligand-pLDDT difference0.1606.
Both workers load structure weights once; no affinity model load. Only the
allowlisted SVD CPU-fallback warning appears (one warning per worker, not a count
of individual fallback calls). Startup9.77/9.91s is reported separately.

44 NISE regression tests, two replay tests (frozen-input tamper checks plus real
MPS RNG preservation/replay) and swift build pass. git diff --check passes.
Initial plotting in Boltz's environment failed because matplotlib was absent;
audit had succeeded. Plotting now uses installed Protenix matplotlib3.11.1 with
no dependency installation. The overview PNG was visually reviewed.

Evidence: [results summary](artifacts/0150-biotin-guidance-comparison/results_summary.json),
full report/CSV/audit/SVG under `Validation/output/biotin_guidance_replay_v1/main/analysis`.

## Decision and rationale

Do not switch physical/FK guidance off as a default on this evidence: its raw speed
advantage accompanies incorrect biotin stereochemistry which confidence and the
current contact/exposure filters miss. Request grouping is a distinct, smaller
throughput improvement and preserves measured outcomes in this paired test.
No guided-batch prediction was tested, so the7% gain is not established for the
original guided campaign. Keep the campaign paused for user review.

## Reproduce

See `Validation/experiments/biotin_guidance_replay_v1/README.md`, declared manifest,
prepare.py, analyse.py and crosscheck_protein_chirality.py. Use managed Boltz
Python for audits, installed Protenix Python for figures, and the shipped broker
for every inference launch. Exact immutable plans/launch/status records live
under `Validation/output/biotin_guidance_replay_v1/{pilot,pilot_frozen,main}`.
Starting commit f6ca4108e14dcebc7c60c3d3b77703098c9b45cd plus fingerprinted snapshot.

## Limits and what was not tested

One ligand;30 X-containing initial backbones with incomplete side chains. No
optimization, affinity, binding experiment, Ramachandran/rotamer analysis,
additional hardware, randomized arm order or repeated timing trials. Original
preprocessing differs in timing coverage. Numerical outputs are not bitwise
identical. Native directory order differs from singleton order. No new
cancellation/resume or memory-soak test; completed units use the existing Journal
contract and an interrupted batch must be replayed as a whole. No default
promotion, app/DMG replacement or full campaign resume.

## Next

If pursuing throughput, separately benchmark batching with physical guidance
retained. Consider explicit ligand stereochemistry validation before treating
geometric contact/exposure passes as usable candidates. Neither change is
silently applied by this experiment.

## Follow-up clarification: stereochemistry and ligand templates

User asked whether the 11 contact/exposure passers are among the 19 correctly
chiral pocket-only predictions. Rechecked the per-input audit: 7 pass both;
4 pass contact/exposure but have wrong biotin stereochemistry (L009, L021,
L027, L028). Of the 19 failing contact/exposure, 12 have correct stereochemistry
and 7 do not. Both replay arms have exactly this overlap. Original guidance-on
outputs have 13 passing contact/exposure, all correctly chiral.

Biotin's three stereocentres encode handedness, not the overall rotation or
placement of the molecule. Ten affected pocket-only predictions reverse all
three centres; L027 reverses only C31. Input chemistry and atom identities were
unchanged. Correct input conformers were already reused by both replay arms;
providing a conformer does not rigidly enforce output stereochemistry.

Checked installed Boltz2.2.1 schema.py: template chain selection explicitly
requires protein chains, as does upstream docs/prediction.md#templates. A normal
protein template is not a supported ligand-coordinate lock. A future ligand
restraint/rigid-body implementation would need separate validation. Installed
get_potentials includes ChiralAtomPotential with physical guidance; Studio's
use_potentials currently toggles both physical guidance and FK steering. Keeping
physical/chirality guidance with FK off is a possible separate experiment, not
a measured speed/quality result and not launched here. Campaign remains paused.

## Follow-up: guidance controls and recommended next comparison

Inspected installed Boltz2.2.1 get_potentials, individual potential definitions,
BoltzSteeringParams and diffusionv2.sample. Three separate mechanisms are exposed
in the upstream steering configuration: physical gradient updates, contact/template
gradient updates, and FK particle weighting/resampling. Studio currently maps
use_potentials to both physical_guidance_update and fk_steering; contact guidance
remains independently true. Individual physical terms are bundled in upstream
get_potentials, not individually exposed Studio controls.

Physical terms: chiral-atom orientation; specified stereo-bond orientation;
planar bonds; RDKit/PoseBusters distance bounds for bonds, angles and internal
clashes; connected-atom distance limits; nonconnected-chain van der Waals
overlap; symmetry-related chain centre separation. Contact terms: forced
pocket/contact distance restraints and supplied protein-template restraints.
Symmetric-chain separation is irrelevant to this single-protein/single-ligand
case; template restraint needs a supplied template. Exposed-atom SASA checks
remain post-prediction filters, not a guidance potential.

Recommendation: retain the complete default physical-guidance bundle and existing
stage-specific pocket policy initially; avoid guessing which chemical penalties
to remove. Compare physical=True, contact=True, FK=False against the original
physical=True, contact=True, FK=True on the frozen inputs. With one requested
output sample, FK=False removes the internal three-particle multiplier. This
proposed combination has not been benchmarked and was not launched. Guidance
weights, schedules, gradient-step counts and all geometry filters should remain
unchanged for that comparison. Chirality filtering remains desirable because
guidance is a soft bias, not a mathematical guarantee of valid final chemistry.
