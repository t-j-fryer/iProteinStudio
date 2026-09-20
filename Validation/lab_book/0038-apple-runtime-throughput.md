# 0038 — Isolated Apple runtime and CPU-thread screening

Date:2026-09-19. Status:complete initial Boltz screen; no defaults promoted.
Host:M4 Max /64GB /macOS26.6.1 (25G76).
Base commit:b629789d6187af08ec046f1c8547b5ab5ffb83e1; exact source hashes in plans.

Hypothesis: a newer runtime, bounded CPU threading or equivalent implementation
can improve unchanged Boltz work without practically meaningful accuracy loss.
User explicitly excludes smaller models, fewer steps and disabled guidance;
MPNN stays on CPU. Selective precision is a separately declared arithmetic arm.

Manifest/code: `experiments/apple_runtime_throughput_v1/`.
Outputs/audits: `output/apple_runtime_throughput_v1/`.
Full methods, results, failures, commands and untested cases:
[Project Lab Book0168](../../lab_book/0168-test-isolated-apple-runtimes.md).

Controls fix sequences, seeds, checkpoint, recycles, steps, full potentials,
requested samples and allocator reset. MSA is explicitly empty in both arms;
no MSA service or replacement. Immutable plan provenance fingerprints checkpoint,
canonical component assets, code and runtime seals. Completed raw outputs remain
unchanged; derived analysis is separate. All inference uses the shared broker.

| Experiment | Result |
|---|---|
| Torch2.13→2.14 | Three paired blocks; all accuracy gates pass. Two-input time reductions7.08%,20.70%,0.11%; not stable enough for a universal claim. |
| CPU threads1/4/8/12 | Two-input totals26.820/27.937/27.636/29.135s. All numerical gates pass; more cores do not help this small GPU workload. |
| Batched schedule host reads | Same output coordinates,5.35% slower; do not adopt. |
| Diffusion-network BF16 |8.92% slower. SUMO RMSD1.881A and displacement p952.669A exceed declared0.5A/1.5A margins. Retain failed arm. |
| Synchronized profile |~78% in diffusion;200 SVD calls per prediction. Preprocessing0.173/0.221s. Diagnostic, not headline throughput. |
| Interruption/recovery | Completed reference receipt reused unchanged; partial attempt retained; old child group gone; resumed thread job completed. |

48 completed outputs in16 process blocks, including16 warmups; an extra warmup
from the interrupted attempt remains separately audited. Only two proteins and
two seeds, not48 independent cases. Twelve harness and two broker fixture tests
pass. Final byte audits confirm runtime seals and installed helper preservation;
installed Torch remains2.13. No physical-quality violations appeared in the
limited backbone-distance check, including the numerically rejected BF16 arm.

Reference1UBQ was checked post hoc for context, with all residues and separately
reported1–72 retained. It is not a blind holdout and no threshold was widened.
All confidence/PAE gates passed even in BF16; coordinate divergence alone caused
its rejection. Numerical agreement is not experimental binding validation.

Limits: no other engines, interfaces/ipSAE/rankings, larger/deep-MSA cases,
ligand affinity, M1/M2/M3/M5, long memory/thermal soak, device-profile promotion,
release packaging or app deployment. Source plan and project entry detail
cache/thermal/bytecode-provenance limitations and the reverse-order label fix.
