---
entry: 0149
title: Explain the biotin versus overview Boltz timing difference
date: 2026-09-17
author: Codex
type: audit
status: complete
machine: Apple M4 Max, 64 GB; recorded historical and current local timings
tags: [nise, boltz, timing, audit]
---

## Context

User compared the initial biotin rate in0148 with
`Validation/output/bgx_completed_overviews_v1/01_minibinders_overview.svg`.

## What was done

Read the figure caption, timing.csv, provenance, original Boltz session configs
and twelve 50-input resident-response receipts. Compared them with the fixed
12-prediction biotin progress snapshot. Inspected both frozen resident workers,
the current split-affinity adapter, and installed Boltz steering/diffusion code.
Ran `Validation/experiments/biotin_boltz_timing_audit_v1/analyse.py`; all receipt
count, status and phase assertions pass. Raw outputs and live settings unchanged.

## Results

Historical h0/h1 figure bars:25.3982/26.2206 seconds per optimized design, defined
as campaign span including initialization/MPNN divided by250 optimized outputs.
The original resident requests contain300 predictions per campaign and average
20.1266/20.7683 seconds per prediction. Current biotin snapshot:12 initial
structure requests averaging51.6436 seconds. These are descriptive observations,
not a paired performance comparison. Both use one resident structure-model load.

Historical launch arguments explicitly use `--boltz-no-potentials`, and session
configs confirm `use_potentials:false`. Current biotin uses potentials plus forced
head-atom pocket contacts. Both resident worker implementations use3 recycles,
200 diffusion steps and1 requested output sample; configs do not override them.

The installed Boltz `BoltzSteeringParams` defines3 particles. Enabling potentials
activates FK steering and physical guidance; diffusion multiplies requested
sample multiplicity by3 internally and performs guidance/resampling before
returning the requested output. This is substantive extra sampling work, not
just a cheap final geometry check. Contact guidance also enforces the initial
pocket. The settings are the strongest concrete explanation for higher latency;
their individual wall-time contributions have not been measured.

Historical runs submit50 inputs per worker request; NISE submits1 per request.
Boltz's data-loader batch size is1, so this is request amortization rather than
50 simultaneous GPU predictions. Extra per-request preparation is a possible
secondary overhead, not a quantified cause. Current affinity-head execution is
explicitly skipped at cycle00 (`phase:structure`, model-load count1); affinity
does not explain this initial slowdown. Inputs/targets/MSA and seeds differ too.

## Decision and rationale

Explain the real protocol difference rather than attributing it to lost residency
or affinity. A potential-on/off test with identical biotin inputs would be needed
to isolate its cost and assess effects on generation. Do not disable guidance or
change the ongoing immutable campaign in response to this explanatory question.

## Reproduce

```bash
NANOHUNTER_ROOT="$HOME/.iproteinstudio" python3 \
  Validation/experiments/biotin_boltz_timing_audit_v1/analyse.py \
  --output Validation/output/biotin_boltz_timing_audit_v1/audit.json
```

The experiment manifest, output source hashes and Validation entry0029 document
inputs. Current weights/code fingerprints remain in0148's plan; historical
checkpoint-byte equivalence has not been established.

## Limits and what was not tested

No inference, paired benchmark, isolation of preprocessing/guidance overhead,
setting promotion, GUI change or build. No assertion that disabling potentials
would reproduce the historical rate or preserve scientific outcomes.

## Next

Follow-up clarification: inspected installed Boltz `main.py`,
`model/potentials/potentials.py` and `model/modules/diffusionv2.py`, plus official
prediction documentation. `--use_potentials` toggles FK steering and physical
guidance; `contact_guidance_update` defaults to true independently. The Studio
resident adapter preserves that distinction. A YAML pocket with `force:true`
therefore retains its contact potential even when global physical/FK steering is
off. Contact-only generation need not use the three-particle FK mechanism.
Turning off every form of guidance would be different from omitting this flag.

Particles are alternative noisy coordinate hypotheses for the same input, not
different designed sequences or NISE beam members. FK sampling propagates three
particles, periodically resamples them using potential-based weights, and samples
one final particle per requested output. It is not three wholly independent
completed folds followed by deterministic highest-pLDDT/P(bind) selection.
This follow-up is source verification only; no live setting change or speed test.
Official reference: https://github.com/jwohlwend/boltz/blob/main/docs/prediction.md

If a throughput change is requested, measure on identical benign biotin inputs
before proposing a new execution plan.
