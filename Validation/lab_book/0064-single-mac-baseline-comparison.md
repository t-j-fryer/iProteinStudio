---
entry: 0064
title: Simplify paper benchmark to one baseline and one optimized implementation
date: 2026-09-30
status: research-complete; not-run
---

User clarification replaces the three-stage proposal in0063. `experiments/mac_intervention_baselines_v1/SINGLE_BASELINE.md` is now the active protocol; manifest schema2 explicitly declares two arms and no execution.

Baseline follows the adopted source: community OpenFold/ESM ports, developer Boltz/IntelliFold/Protenix variants with disclosed minimal Mac compatibility. Scientific settings and model weights fixed within each comparison; qualified historical dependency versions make selected runtime upgrades part of the intervention. Native source batching/reuse retained; no artificial per-input reload penalty.

Historical measured support is tabulated with workload/sample/accuracy limitations. Proposed540 measured predictions across nine models plus warmups; five SUMO complexes×five seeds plus monomer inset,128-row target MSA, native diffusion budgets, fixed precision/recycles/guidance and matching output products. Five independent counterbalanced blocks; report warm end-to-end throughput, cold load separately, memory and quality. No multiplication of unrelated historical gains or attribution of community MLX speedups to Studio. OOM has no numeric ratio.

No new raw outputs, numerical audit, installation, worker mutation or promoted setting. Existing checkpoint/MSA/source evidence retained. Future per-arm environment locks/input manifest/provenance and broker plan required before execution. Project record0232.
