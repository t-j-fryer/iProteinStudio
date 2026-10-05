# 0095 — Corrected RFD3 motif runtime release

2026-10-05; Apple M4 Max/40 GPU cores/64GB. See project entry0298 for full evidence,
limits and reproduction. Parent commit7677ea5; source experiment
`experiments/rfd3_motif_release_v1/manifest.json` declares runtime and settings.

Fourteen CPU preprocessing cases pass; two one-backbone jobs complete through
MCP and independent Boltz complex/monomer checks. The actual motif fixture has
nine selected fixed atoms. All six structures are finite and have zero
nonadjacent CA pairs below2 Å. Motif derivative fails standard quality gates;
partial derivative passes. This is pipeline/correctness acceptance, not a claim
of binding or a measured success-rate/throughput improvement. Original outputs
are immutable; output-audit.json records hashes and filter verdicts. No MSA
intervention or performance claim; model/checkpoint hashes are in frozen plans.
