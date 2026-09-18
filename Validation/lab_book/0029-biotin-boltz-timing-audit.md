# 0029 — Explain biotin versus historical Boltz timing

2026-09-17; complete read-only audit, no inference or setting promotion.
Hardware: recorded local Apple M4 Max /64 GB. Source base:f6ca410.

Executed [analysis](../experiments/biotin_boltz_timing_audit_v1/analyse.py) with its
declared manifest. It verifies6 ×50-input successful resident responses for each
historical campaign and the recorded12 successful current structure requests.
Results/source hashes: `Validation/output/biotin_boltz_timing_audit_v1/audit.json`.

Historical plot:25.3982/26.2206 s per optimized output, including initial/MPNN
span. Historical worker requests:20.1266/20.7683 s per prediction (300 per arm).
Current biotin snapshot:51.6436 s per initial prediction (n=12). Same attributed
hardware, differing inputs and settings; no paired causal comparison.

Both use resident Boltz with3 recycles/200 steps/1 requested output. Historical
potentials off; current physical/FK guidance on, with3 internal particles and
initial pocket contacts. Historical50-input requests versus current1-input
requests amortize preparation differently (actual data-loader batch size1).
Current initial stage does not execute affinity. Contributions were not profiled.

Current empty MSA; historical target-MSA hashes and source snapshots are recorded
in the overview provenance. Current engine/weight fingerprints are in Lab Book0148
plan; historical model-byte equivalence not proved. No raw artifact edits or live
run changes. Detailed reasoning, reproduction and limits in project Lab Book0149.
