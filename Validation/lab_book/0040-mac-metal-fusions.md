---
entry: 0040
title: Test same-runtime Metal fusions and NESSO preprocessing
date: 2026-09-19
author: Codex
type: benchmark
status: complete
machine: Apple M4 Max, 40-core GPU, 64 GB unified memory, macOS 26.6.1
---

## Request and environment
Research and test additional Metal kernels for Boltz2, Protenix v2 and NESSO,
then integrate supported speedups. Apple M4 Max,40-core GPU,64GB unified memory,
macOS26.6.1. Repository HEAD `b629789d6187af08ec046f1c8547b5ab5ffb83e1`;
working tree already contained unrelated work, which was preserved. No commit.

## Reproducibility and protocol
`Validation/experiments/apple_runtime_kernels_v3/manifest.json` declares the
experiments. Every attempt has immutable `frozen/run.json`, source/runtime seals,
`host.json`, broker `plan.json` with script/asset provenance, and an output inventory
receipt. Model/checkpoint fingerprints are in those plans and installed-component
receipts; no weights copied into source control. Explicit empty MSAs throughout;
no fetched/cached alignment substitution or associated MSA checksum is applicable.
Warmups and synchronized diagnostic profiles are excluded from speed comparisons.
Same-runtime paired controls retain seeds, sequences, sample counts, steps,
recycles, guidance and FP32. Torch remains Boltz2.13.0 /Protenix2.7.1 /NESSO2.11.0 /
IntelliFold2.6.0. Boltz physical/FK potentials stay on.

All model/GPU work used `workflow_guide`, immutable preflight plans, `job_start`,
script provenance and the real shared exclusive GPU lease. No direct competing
GPU process. The coordinator resumes audited complete blocks and retains partial
attempts. SUMO gates exclude its first20 residues and use the same baseline
pLDDT>=80 core in both outputs; an insufficient core is unassessable, not relaxed.

## Measured results and integration
- FP32 SiLU multiply and sigmoid multiply/add: all45 operator cases pass an
  independent FP64 oracle and stock FP32 comparison at relative L2<=1e-5.
  Isolated operator savings did not imply whole-engine gains.
- Boltz original wrapper:26.322→31.416s for two measured requests (19.3% slower).
  Lean follow-up:30.018→29.940s (0.3% less), exact checked outputs. Experimental only.
- Protenix: initial28.199→25.505s (9.6% less), but seed42 SUMO lacked an assessable
  confidence core. Reverse-order seed43 confirmation including synthetic228-residue
  input:134.617→132.038s (1.9% less); all gates pass. Individual short input slowed,
  synthetic228 input improved5.1%. No production Metal default.
- NESSO Metal:12.941→12.881s (0.5% less), exact outputs; not promoted.
- NESSO AA cache:19.665→13.310s (32.3% less). Recovery/repetition confirmation
  completed16 outputs, with exact outputs and the completed candidate receipt
  unchanged after a real broker cancel/resume. Controls were separated by the
  queue/recovery; its27.2% reduction is labelled accordingly.
- NESSO combined AA/conformer caches versus original:18.320→2.732s for two warmed
  short requests (85.1% less). Separate24-output confirmation with four ligands,
  two seeds across screens, changed sequences and76/96/228-residue lengths:
  saved parser arrays, embeddings and all scalars exactly equal. Confirmation
  mixed cold/warm requests improved27.2% against AA-cache-only, a different control.
  New ligand requests retain upstream first-use cost. Source worker enables both
  caches; immutable conformer bytes and fresh mutable AA clones preserve inputs.
  Cache capacity8; CCD identity checked each request. Noncanonical proteins retain
  original upstream preprocessing. No installed-app staging/deployment performed.

## Rejections and diagnostics retained
Raw in-process NESSO preprocessing changed RDKit ligand coordinates even though
scores passed0.02; rejected. Attempting to reset the exposed RDKit RNG did not
reproduce a fresh process and was not used. The replacement caches actual original
conformer bytes through upstream's supported conformer-input path.

Fused adaptive LayerNorm passed ordinary inputs but failed all six near-constant
FP64 stress cases; stopped before inference. Native normalization/GEMM retained.
Initial Boltz profile failed before inference because the worker set forbidden
MPS fallback; diagnosed broker error/log, corrected subsequent coordinator to0,
and retained failure. The earlier operator-only Boltz process inherited fallback1
but exercised native custom operators only; this is not a prediction result.

## Verification and commands
- `python3 -m unittest discover -s Tests -p 'test_nesso_*.py'`:26 passed.
- `python3 -m unittest discover -s Tests -p 'test_intellifold_padding.py'`:4 passed.
- `/usr/bin/python3 Validation/experiments/apple_runtime_kernels_v3/preflight.py ENGINE STAGE --start`
  plus recorded `--reverse`, `--seed 43`, `--larger` options in frozen manifests.
- `status.py`, `recovery.py`, `analyse.py`, `preprocessing_audit.py`, `report.py`
  under that experiment directory reconstruct status, receipts and comparisons.
- `finalise.py` produces `FINAL_AUDIT.json` only after all broker jobs are terminal.
- Initial sandboxed `swift build` could not access Swift/Clang user caches;
  final build/check result recorded below after GPU timings finish.

## Limits and what was not tested
One Mac. Computational fixtures with empty MSAs;228-residue fixture is a synthetic
repeat, not a claimed native fold. No MSA-rich interface ranking, complete NISE
mutation/design campaign, other chip, full-v2 padding promotion, installed-app
lifecycle or multi-hour memory soak. Repeated NESSO requests showed similar
shape-dependent MPS allocator growth in both arms (~6.40GiB final driver allocation
in the larger confirmation), not proof of unlimited leak-free operation. The
broker restart used AA-cache-only; conformer-cache fresh-session isolation was
checked separately. No Torch upgrade, reduced steps, smaller model, disabled
guidance, MPNN work or Protenix Mini change.

## Outputs and research
- `Validation/output/apple_runtime_kernels_v3/REPORT.md`, `DECISIONS.md`,
  `OVERVIEW.svg`, `measurements.json`, `timings.csv`, `FINAL_AUDIT.json`.
- `docs/research/APPLE_METAL_FUSION_TESTS.md`: primary Anthropic, PyTorch, Apple, MLX,
  NESSO and RDKit sources; explains transfer to MPS and rejected approaches.

## Final padding confirmation and integration
IntelliFold Flash reversed-order comparison completed8 outputs, all coordinate,
confidence and geometry gates passing; saved values identical. Measured short
requests93.352→44.879s (51.9% less time). The synthetic228-residue case retained
its original bucket and exact outputs; its timing difference is ordinary pair
variation, not attributed to the optimization. Both CLI and resident source
launchers now prepend128 for Flash only, preserve every upstream larger bucket,
and respect explicit overrides. All Full-v2 buckets remain unchanged.

After integration:4 padding-policy tests and4 prediction-safety tests passed;
resident-resume suite12 passed with2 dependency-conditioned skips in system Python;
iterative CLI contract passed. Model tests exercised explicit matching bucket
arguments in frozen launchers; final default-wiring changes are covered by the
policy/CLI/resume checks. No new model/runtime settings were inferred from speed.

## Final audit
All21 broker plans terminal:20 completed and1 retained pre-inference failure.
33 complete blocks /129 prediction or scoring outputs:88 measured,32 warmups,
9 profiled. No completed-output inventory/audit errors.57 operator cases, with
6 normalization numerical rejections retained. Installed runtime versions unchanged.
Managed IntelliFold Python rerun passed all14 resident-resume tests with no skips.
`swift build` passed after permitting normal compiler cache access. Relevant
`git diff --check` passed. Final figure inspected. Integration verification is
saved in `integration_checks.json`; source hashes and recovery evidence are in
`FINAL_AUDIT.json`. Work complete; no commit, release or running-app deployment.
