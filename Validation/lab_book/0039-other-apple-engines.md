# 0039 — Other Apple runtime comparisons

2026-09-19. Bounded screen complete. M4 Max /64GB /macOS26.6.1.
Base commit b629789d6187af08ec046f1c8547b5ab5ffb83e1; exact dirty source hashes in plans.
Manifest: `experiments/apple_runtime_throughput_v2/manifest.json`.
Paired identical sequences, explicit empty MSAs, seeds, models, scientific
settings and counts; runtime/implementation changes declared per arm. Exclude
Protenix Mini and leave CPU MPNN unchanged. No default promoted.
Immutable raw outputs and audit: `output/apple_runtime_throughput_v2/`.
[Full project entry](../../lab_book/0169-test-other-apple-engines.md).

Final: 48 terminal plans (38 completed, 8 retained failures, 2 cancelled before
inference); 60 unique completed blocks, 162 audited output units, zero completed
output-audit errors, 29 CPU tests passed. SUMO analysis excludes fixture residues
1–20 and uses the same baseline pLDDT≥80 core in both outputs. Previous audits
are retained. Installed runtimes and app defaults unchanged.

See [decisions](../output/apple_runtime_throughput_v2/DECISIONS.md),
[full report](../output/apple_runtime_throughput_v2/REPORT.md),
[runtime figure](../output/apple_runtime_throughput_v2/OVERVIEW.svg), and
[implementation figure](../output/apple_runtime_throughput_v2/IMPLEMENTATIONS.svg).
The RFD3 SDPA speed claim failed fresh-pair confirmation; custom Metal remains
unqualified after trajectory/oracle failures. Positive short-fixture padding,
CCD-cache and initialization results retain their timing and scope limitations.
No larger-complex, full-campaign, combined-change, restart/soak or fleet validation.
