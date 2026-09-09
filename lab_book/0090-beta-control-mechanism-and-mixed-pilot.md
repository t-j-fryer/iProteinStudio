---
entry: 0090
title: Diagnose secondary-structure priors and start a bounded mixed pilot
date: 2026-09-04
author: gpt-6
type: analysis-and-experiment
status: analysis complete; mixed pilot submitted
machine: Apple M4 Max, 64 GB (prior campaign provenance)
tags: [secondary-structure, beta-sheet, sequence-priors, mixed]
---

## User request

Analyze the present secondary-structure control and think through a better way
of increasing beta content; also try combined anti-helix and beta control.

## What the existing implementation controls

`secondary_structure_control.py` changes initial sequence sampling and optionally
adds per-position amino-acid logits during later SolubleMPNN redesigns. It does
not condition the predictor/backbone on sheet topology. The saved random grammar
partitions the sequence into 5–8-residue strands and 2–5-residue turns, with an
independently chosen alternating side-chain face offset for each strand.

It contains no strand pairing, orientation, register, backbone hydrogen-bond or
sheet-curvature constraint. The first and last positions of each planned strand
are labelled `edge`, but these are strand endpoints, not a coordinate-derived
identification of lateral sheet edges. Current negative-design wording must not
be interpreted as a validated anti-aggregation mechanism. About 31.6% of positions
in the completed beta plans are designated turns; this alone does not specify
how those turns connect a physically consistent sheet. The 50% X initialization
mask also hides part of the seed pattern, and is retained in this pilot to avoid
confounding the previous controls.

MPNN conditions sequence choice on the previous backbone. Repeated sequence
bias on a helical backbone can therefore oppose its conditional sequence model
without specifying an alternative coherent fold. This is an inference consistent
with the measured coil/confidence effect, not a demonstrated full causal account.

## Additional measurements on completed outputs

Executed `Validation/experiments/secondary_structure_priors_v1/diagnose_prior.py`
against the audited coordinate/sequence data. Means use all 10 trajectories,
each averaged across optimized cycles 01–05. Cycle 00 remains excluded.

| Planned-strand endpoint | Beta seed-only | Beta sustained |
|---|---:|---:|
| V/I/T/F/Y/W sequence fraction | 19.96% | 22.89% |
| Glycine/proline sequence fraction | 10.67% | 5.09% |
| Actual sheet assignment | 15.39% | 16.56% |
| Actual helix assignment | 44.01% | 44.09% |

Thus the prior affects sequence composition, but planned strands largely fail
to become strands in predicted coordinates. Increasing composition bias alone
is not justified by these results.

## Temperature and mixed-mode interactions

The installed upstream LigandMPNN `model_utils.py` samples
`softmax((logits + bias) / temperature)`; SolubleMPNN uses this implementation
with its appropriate checkpoint. The runner uses T=0.30 for the first redesign
and T=0.10 afterward. At anti-helix strength 0.50, A/E/K/L/M/Q each receive -0.60.
Holding other logits/biases fixed, the corresponding relative-odds multiplier
versus an unbiased residue is exp(-0.60/0.30)=0.135 initially and
exp(-0.60/0.10)=0.00248 later. These are analytical conditional odds factors,
not measured residue frequencies or performance numbers. A displayed strength
of 0.50 does not mean a gentle or constant 50% suppression.

Mixed mode simply adds both bias maps. Its global penalty includes E/K/Q, which
the polar beta-face prior also encourages. At strength 0.50, a planned edge gives
E/K/Q +0.35 from beta patterning and -0.60 from anti-helix: net -0.25. Serine gets
the same +0.35 plus +0.125 from anti-helix. This creates a compositional conflict,
not coordinated negative design against a particular helical alternative.

## Better design direction — proposals, not promoted settings

1. Prefer a coherent beta-rich backbone/scaffold or preserved multi-strand motif,
   then use SolubleMPNN to design a compatible sequence. Pairing, register, turn
   geometry and burial should come from coordinates or a validated fold-conditioned
   model. Starting geometry changes must be a separately controlled experiment.
2. For a revised sequence-prior implementation, define bounded odds adjustments
   and convert to upstream logit biases with `bias = T * log(weight)`, retaining
   upstream sampling itself. This holds the added prior's odds contribution
   constant across temperatures; it does not make the backbone model temperature
   invariant. Version this separately rather than changing existing replay semantics.
3. Replace global A/E/K/L/M/Q suppression with milder, position/context-dependent
   interventions. Preserve polar/charged residues needed at exposed beta faces
   and core residues compatible with the intended fold. Confine turn rules to
   geometry-supported turns. Arbitrary proline enrichment or blanket glycine
   exclusion is not a general sheet-design solution.
4. Select for confident, connected beta structure rather than helix loss or
   sequence propensity. Retain P-SEA as the primary coordinate endpoint; add
   strand-pair connectivity/backbone hydrogen-bond checks, binder pLDDT, ipSAE,
   iPTM, geometry, exposed hydrophobic patches and sequence diversity. Preserve
   hard quality gates and compare identical proposal budgets. Keep both complex
   and binder-alone confirmation predictions free of binder-template constraints.
5. Test a revised scheme using identical structural starts for each paired
   trajectory across natural/anti/beta/mixed redesign conditions, if supported by
   a validated upstream initialization interface. Separately test seed changes.
   Do not modify immutable cycle-00 records to simulate a shared-start experiment.

These ideas require validation. No new scientific bias algorithm, predictor
restraint, default, engine installation or weight change was made in this turn.

## Literature and capability check (accessed 2026-09-04)

- [ProteinMPNN primary paper](https://pmc.ncbi.nlm.nih.gov/articles/PMC9997061/):
  inverse folding designs sequence for supplied backbone geometry. This supports
  using a desired backbone as the positive structural constraint.
- [Koga et al., 2012](https://www.nature.com/articles/nature11600): consistent local
  and non-local interactions and loop/secondary-structure relationships underpin
  designed topology; amino-acid propensity alone is insufficient as a design plan.
- [Marcos et al., 2018](https://pubmed.ncbi.nlm.nih.gov/30374087/): experimentally
  characterized non-local beta-sheet design used loop geometry, side-chain
  directionality and strand-length relationships arising from hydrogen bonding
  and packing constraints.
- [Upstream LigandMPNN sampling code](https://github.com/dauparas/LigandMPNN/blob/main/model_utils.py):
  confirms the bias/temperature equation also inspected in the installed runtime.
- [Original RFdiffusion fold conditioning](https://github.com/RosettaCommons/RFdiffusion#fold-conditioning):
  supports secondary-structure plus block-adjacency conditioning. This is the
  original RFdiffusion capability, not an assertion about Studio's RFdiffusion3.
- [RFdiffusion3 input documentation](https://github.com/RosettaCommons/foundry/blob/production/models/rfd3/docs/input.md):
  explicitly says direct secondary-structure guidance is currently unavailable;
  `is_non_loopy` reduces loops but does not select beta over alpha. Studio's
  validated partial/motif workflows are a more relevant starting point for
  preserving a beta core than inventing an unsupported beta-conditioning flag.

## Mixed pilot executed to submission

Workflow guide and system_detect were called first; Boltz and MPNN were ready.
Prepared and reviewed all four immutable plans (including normalized settings,
commands, scheduler, no-post-prediction policy and digests), then submitted:

| Arm | Job |
|---|---|
| Mixed anti 0.25, seed-only | job-00cbe4524ea5 |
| Mixed anti 0.25, sustained | job-f016478ac89a |
| Mixed anti 0.50, seed-only | job-373cb38a0fa0 |
| Mixed anti 0.50, sustained | job-0e3ab3ba07e2 |

Each has one 90-residue trajectory and five optimized cycles; beta, pattern and
turn strengths all remain 0.50. Total: 24 predictions including four initial
structures. Each strength has an identical-start scope control. Existing runner
and helper SHA-256 values match the previous campaign. No raw output was changed.
Jobs serialize under the shared broker lock, using resident Boltz and the
recorded MSA/seed policy. See [Validation entry 0008](../Validation/lab_book/0008-mixed-prior-pilot.md)
and `Validation/output/secondary_structure_mixed_v1/manifest_smoke.json` for the
full declaration and current git/runtime/input fingerprints.

## Tests and limits

The diagnostic script ran and produced `analysis/prior_diagnostics.json` under
the original ignored output tree. Planning and job submission were executed,
not merely syntax checked. The pilot was running/queued at initial review;
no mixed efficacy claim is made before its completed output audit. One trajectory
per arm is insufficient to estimate an effect or choose an optimum even after
completion. The backbone-based and temperature-normalized proposals have not
been implemented or tested. No independent folds, wet-lab experiment, new
benchmark, app build or commit was performed.
