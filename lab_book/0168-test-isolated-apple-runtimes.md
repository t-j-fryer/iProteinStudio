---
entry: 0168
title: Test isolated Apple runtimes and practical numerical gates
date: 2026-09-19
author: Codex
type: benchmark
status: complete
machine: Apple M4 Max, 64 GB, macOS 26.6.1 (25G76)
tags: [performance, mps, numerical-accuracy, cpu-threading]
---

## Context

User authorized testing of the [Apple throughput plan](../docs/APPLE_SILICON_THROUGHPUT_PLAN.md),
retaining models, diffusion steps and guidance, using practical numerical
accuracy margins and measuring CPU parallelism. MPNN CPU speed is satisfactory.
The current baseline is a comparator, not ground truth. This entry completes
**the initial Boltz screen**, not the all-engine optimization programme.

## What was done

Added the manifest, isolated environment preparation, narrow preflight factory,
resident worker, numerical audit, profiling, two implementation experiments,
recovery checks and reports under
[apple_runtime_throughput_v1](../Validation/experiments/apple_runtime_throughput_v1/README.md).
APFS copies retain installed Torch2.13 and replace only Torch with the official
SHA256-verified2.14 wheel in the candidate. Both dependency checks passed.
Runtime seals cover files except bytecode caches; no model weights copied.

Scientific jobs use the shipped workflow guide, immutable plan persistence,
run-profile job_start, script/checkpoint/chemical-component provenance, real
shared execution lease and serial resident blocks. No production MCP tool or
installed engine was modified. Inputs are ubiquitin76aa and SUMO96aa, with
explicit empty MSA, seeds42/43, three recycles,200 diffusion steps, one requested
sample, FP32 baseline, retained allocator reset and full potentials. Effective
settings confirm three internal FK particles and20 guidance steps.

Declared prospective investigation margins: aligned C-alpha RMSD<=0.5A,
displacement p95<=1.5A, normalized pLDDT/pTM change<=0.02, PAE MAE<=0.5A and
PAE absolute-error p95<=2A. Exact sequence/atom identities, finite outputs,
cardinality and no-new-backbone-break gates complement CPU-FP64 synthetic
references. Numerical thresholds were not widened after seeing failures.

## Results

**48 completed prediction outputs across16 process blocks** (16 warmups and32
measured calls), plus one retained warmup from an intentionally interrupted
attempt. All completed receipts and both runtime seals verified. Six jobs
completed; the selective-BF16 job failed its declared numerical screen after
saving all outputs. This is not48 independent inputs: only two small proteins
and two seeds were tested.

| Contrast | Replication | Timing result | Numerical result |
|---|---|---|---|
| Torch2.13→2.14, four CPU threads | Three paired process blocks, two measured inputs each; baseline/candidate, reverse, baseline/candidate | Aggregate two-input time reduction7.08%,20.70%,0.11% across blocks; inconsistent magnitude | All pass; maximum measured aligned C-alpha RMSD0.001577A |
| Candidate CPU threads1/4/8/12 | One process per budget, two measured inputs | Two-input totals26.820/27.937/27.636/29.135s | All pass; coordinates unchanged within numerical alignment precision |
| Batched host reads of unchanged sigma/gamma schedule | One paired process block, two measured inputs |25.278→26.631s;5.35% slower | Pass; identical saved coordinates |
| BF16 autocast only within diffusion score network | One paired process block, two measured inputs |24.755→26.965s;8.92% slower | Ubiquitin passes; SUMO RMSD1.881A and displacement p952.669A fail |

The BF16 arm recorded600 score calls with actual BF16 linear and score outputs;
it was not merely a precision label. Outer diffusion, guidance, alignment,
trunk, confidence and stored weights retained their original FP32 paths.
SUMO confidence/PAE changes still passed (pLDDT0.00252, pTM0.00520, PAE MAE0.179A),
and there were no new backbone-distance violations. Failure means the declared
coordinate agreement was not met, not that experimental design failure is proved.

Synchronized diagnostic spans put diffusion_sample at9.828/12.000s of
12.531/15.403s for ubiquitin/SUMO (~78%), with200 SVD calls each. Preprocessing
was0.173/0.221s. Profiled outputs passed comparison with their controls. These
are coarse wall spans, not individual GPU-kernel timings; diagnostic calls are
excluded from throughput conclusions.

The model_load_seconds field measures session initialization, including engine
imports, construction and checkpoint load. First-use values were56.735/55.553s;
subsequent paired values were9.292/9.480s. OS/import/cache state matters: do not
claim a cold-start speedup or interpret this field as checkpoint I/O alone.

Post-hoc [RCSB1UBQ](https://www.rcsb.org/structure/1UBQ) comparison retains full76
residues and separately reports residues1–72 because the crystal describes
mobile termini. Across included outputs, full RMSD1.112–1.307A and core
RMSD0.318–0.350A. Both FP32 runtimes have essentially identical agreement.
This familiar training-era protein is not a blind holdout and no gate was changed.

Twelve focused CPU tests and two existing broker fixtures passed. A real
cancel/resume test stopped the isolated one-thread arm, confirmed no surviving
old child group, preserved its incomplete attempt, reused the completed reference
with an unchanged receipt, and completed all remaining budgets. Interrupted
units were not silently counted as completed blocks. Installed helper hashes
and installed Torch2.13 remained unchanged at final audit.

## Decision and rationale

**No production promotion.** Torch2.14 is numerically compatible in this bounded
screen but has variable timing gains. More CPU threads did not help these
GPU-heavy small folds; do not set every process to every core. The schedule
change and selective BF16 arm do not warrant adoption. Retain negative results
and the practical, prospectively declared accuracy limits.

## Reproduce

See experiment README, [Validation entry0038](../Validation/lab_book/0038-apple-runtime-throughput.md),
and ignored output [REPORT.md](../Validation/output/apple_runtime_throughput_v1/REPORT.md),
[OVERVIEW.svg](../Validation/output/apple_runtime_throughput_v1/OVERVIEW.svg),
[FINAL_AUDIT.json](../Validation/output/apple_runtime_throughput_v1/FINAL_AUDIT.json).
Base commit `b629789d6187af08ec046f1c8547b5ab5ffb83e1`; every plan retains exact
source/runtime/weight fingerprints. Managed setup detect succeeded; queue was
idle before this work and all benchmark jobs are terminal now.

Job IDs: smoke `a662e687142c`, reverse `5d704d1d3750`, threads `7143e4ab561b`,
profile `6900fb9a0f77`, third pair `a8126151b01b`, schedule `6825010b3e44`,
precision `835e15c5ba1b` (each prefixed `job-`).

The first reverse-order comparison used execution-order reference/candidate
labels; its original JSON remains intact. Derived analysis_v1 consistently
orients2.13→2.14, including the asymmetric new-break check. Future preflight
records the direction explicitly. Plotting first failed because the scientific
venv lacks Matplotlib; the existing system plotting Python was used without
installing anything into the sealed environments. Final SVG/PNG were rendered
and visually inspected. The optional thermal query returned errors; only AC
power was confirmed near the end, not thermal stability.

## Limits and what was not tested

No interfaces/ipSAE/ranking selection, ligand affinity, larger shapes or deep
MSAs, full design cycles, full physical-quality battery, other engines,
M1/M2/M3/M5, low-memory Macs, sustained thermal/physical-footprint/memory soak,
sleep/wake or power-loss recovery, distribution packaging or app deployment.
SUMO has no preceding same-shape warmup in each process. CPU process time
includes extraction/audit overhead and excludes child validator CPU; thread
budgets are not evidence all cores were busy. Bytecode caches are excluded from
runtime seals. No universal speed claim or statistical confirmation from this
small screen. No Swift changes or commit; no Swift build run. Existing unrelated
dirty work was preserved.

## Next

Split sampler time into neural network, guidance, alignment and host waits;
measure larger benign complexes with interface/ranking gates before promotion.
Extend isolated runtime contracts to IntelliFold/Protenix and MLX engines:
IntelliFold currently enforces Torch2.6 and patches source on startup, so its
experiment needs an isolated source root and explicit experimental version
contract rather than changing the live pin. CPU-heavy preparation/scoring needs
its own bounded process-pool tests; retain satisfactory CPU MPNN. Cross-device
coverage and the all-engine programme remain outstanding.
