# 0063 — Test runtime consolidation without touching the trusted install

**Date:** 2026-09-01

**Status:** Complete for phase-one feasibility; no production promotion

**Hardware:** Apple M4 Max, 40-core GPU, 64 GB unified memory, macOS 26.6.1

## Why

Nine isolated Python runtime boundaries make the managed installation larger and
more complex, but merging them speculatively would exchange visible duplication
for dependency ambiguity and scientific risk. The immediate questions were
whether Boltz could move from PyTorch 2.13 to the imminent 2.14 release and
whether any existing engines could honestly share dependencies.

## Branch and safety boundary

The complete trusted application state was first built, tested, committed and
pushed as `agent/mps-runtime-stabilization` at commit `095c9cc`. Experimental
work then moved to `experiment/runtime-consolidation-pytorch214`; `main` was not
changed.

All generated environments, caches and predictor outputs live under ignored
`Validation/output/runtime_consolidation_v1/` and
`Validation/cache/runtime_consolidation_v1/`. The production
`~/.iproteinstudio` tree was used only as a read-only source of checkpoints,
chemical data, explicit source overlays and control executables. The harnesses
refuse output outside Validation, refuse overwrite, require MPS, disable general
CPU fallback, check output count and validate geometry.

## What was implemented

- `audit_locks.py` records package counts, important numerical-stack pins and
  every pairwise exact-pin conflict across shipped locks.
- `run_boltz214.py` creates a disposable environment from the complete current
  Boltz lock, replaces only PyTorch, checks consistency, runs the allocator
  reproducer and interleaves three control/candidate predictions.
- `boltz_no_reset.py` holds the scientific route constant without applying
  Studio's current allocator reset.
- `run_protenix_shared.py` compares dedicated Constraint dependencies with the
  ordinary Protenix environment while selecting the Constraint source tree
  explicitly.
- `RESULTS.md` is the durable, reviewable phase-one report. Raw outputs remain
  ignored because they include environments and large structures.

## Findings

The static inventory confirms that most boundaries genuinely differ in Python,
PyTorch, NumPy or compiled dependencies. Existing consolidation is already
sensible: four MPNN modes share one environment, both IntelliFold weights share
one, and Protenix v2/Mini share one.

Boltz 2.2.1 with PyTorch 2.14 final RC passed on M4 Max. Only `torch` changed in
the 69-package environment. Warm wall time was 16.650 +/- 0.791 s (n=2), versus
16.925 +/- 0.308 s (n=3) for PyTorch 2.13. The candidate retained pLDDT exactly,
changed pTM by approximately 0.00000006 and differed by 0.00001119 A CA RMSD.
It also removed the one observed SVD CPU-fallback line. The first candidate
process took 64.845 s despite a five-second model progress time; its additional
cold-start cost is unresolved and was not discarded from the manifest.

Ordinary Protenix dependencies successfully hosted the separate Constraint
source overlay. Against the dedicated Constraint environment, the structure
differed by 0.00004417 A CA RMSD, pLDDT by 0.000008 and iPTM by 0.00000018; wall
times were 60.999 and 64.065 s. Both used native MPS, strict checkpoint loading,
the same checkpoint/settings/MSAs, valid geometry and one exact output. The
ordinary environment must be the shared base because it contains `fair-esm`;
Constraint does not consume its ESM projection, but it need not forbid the
dependency when there is only one shared copy.

This is evidence for a possible reduction from nine logical environments to
eight, not permission to implement it yet. LASErMPNN/MPNN remains unproven and
has 11 lock conflicts plus compiled extensions. Boltz/RFdiffusion3 and
IntelliFold/OpenFold also remain separate because their broader stacks and NumPy
generations conflict.

## Promotion gates

1. Repeat Boltz against the final stable PyTorch 2.14 wheel and pin its exact
   released hash.
2. Run the same Boltz acceptance on the updated M1 Pro, including cold start,
   repeated monomer, multimer/ligand and resident campaign routes.
3. For Protenix sharing, run full v2, Mini and Constraint regressions with
   repeated seeds, then test fresh install, update, rollback, per-model removal
   and repair while proving the correct source overlay at every launch.
4. Only then change installer locks or production paths.

## Not tested

No stable PyTorch 2.14 wheel, M1 Pro candidate, LigandMPNN/LASErMPNN shared
environment, full Protenix model matrix or installer migration was tested. No
production dependency, runtime, model or source tree was modified.
