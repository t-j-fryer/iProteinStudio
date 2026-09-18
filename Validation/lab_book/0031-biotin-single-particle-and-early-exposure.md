# 0031 — Physical guidance without FK; exposure during diffusion

2026-09-17; complete. See project Lab Book0151.

Declared experiment: experiments/biotin_single_particle_v1/manifest.json.
M4Max64GB; Boltz2.2.1 FP32/MPS. Same30 original inputs, conformers, empty-MSA
YAML and imported RNG states from0030. Model/source/CCD hashes frozen by plans.
Two resident arms, each one directory request: clean and snapshot-observed.
Physical/contact guidance on, FK off; unchanged3 recycles,200 steps,1 sample.
Pilot2 inputs ×2 before main30×2. No affinity or early termination.

Measure geometry/time and retrospective failure-detection versus false rejection
of eventual exposure passers at step1 and every5 steps. No default promotion.
First pilot job-4e24c9760222 completed but failed the executed-settings audit:
Lightning recorded the old FK-on initial hyperparameters while the sampler ran
FK-off. Fixed logging via save_hyperparameters and launched corrected pilot
job-d6800e2b6e42. Both pilots are excluded from main timing. Raw outputs retained.
Observer, RNG/preflight and retrospective recovery-policy tests pass; swift
build passes. Corrected pilot audit passed: 2 inputs per one-request arm,
1 model load each, all snapshot/final-PDB mappings exact, paired filter verdicts
identical. Clean/traced requests 77.0138/78.1620 s (2 inputs, startup excluded),
maximum aligned Cα difference 0.00581 Å. L000 fails the first denoised exposure
check but passes finally. These are pilot results, excluded from main timing.
Early noisy coordinate extents exhausted FreeSASA's grid allocation; only
denoised estimates enter exposure analysis. Original full
campaign remains paused.

Main: job-1927596b1a7e, plan-1927596b1a7ee001, launched 22:30 UTC.
Managed output test2/validation_runs/biotin-single-particle-3dedc8197fecf15d;
60 total predictions (30 clean + 30 traced). All 108 installed Boltz source and
checkpoint fingerprints equal the prior replay plan.

Main completed exit0; all 60 outputs and 1,230 snapshots audited. One request,
one model load per arm; 3 recycles, 200 steps, no affinity, MPS, only documented
SVD fallback. Clean 1206.5465 s / 30 = 40.2182 s each (startup 9.6942 s separate).
Traced 1266.7645 s / 30 = 42.2255 s each (startup 10.4979 s). Prior controls in
0030: original physical+FK 48.6888 s; pocket-only batch 14.4290 s. Same M4 Max
64 GB. Original includes preprocessing while replays freeze it; fixed arm order,
one timing trial each, no default promotion.

Physical/FK-off preserves correct biotin chirality in 30/30 (pocket-only19/30),
and 11/30 pass pocket+exposure (all11 correctly chiral). Original13/30 passed.
No severe internal-protein overlaps:8/30 versus original13/30. Hence this is a
speed/quality tradeoff, not a blanket quality improvement.

At diffusion step100, exposure would falsely reject9/11 final passers. Starting
at step150 and requiring3 consecutive failed observations (5-step spacing)
catches19/19 eventual failures with0/11 passers lost, exiting at steps160–190.
Retrospective opportunity:11.33% of diffusion steps,9.22% of traced model time,
before live filtering costs. No actual early termination; not independently
validated and selected on the same30-input sample.

Clean/traced exposure verdicts match30/30; max aligned Cα RMSD0.1882 Å and
ligand RMSD1.0724 Å (L015); numerical identity is not claimed. Figures/report,
raw audit and snapshot metrics under output/biotin_single_particle_v1/main/analysis.
Original campaign remains paused. No app defaults or installed engines changed.
