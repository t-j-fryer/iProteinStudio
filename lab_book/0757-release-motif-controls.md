---
entry: 0757
title: Qualify RFD4 motif controls for release
date: 2026-11-04
author: Codex
type: audit
status: completed
machine: Apple M4 Max, 40-core GPU, 64 GB unified memory
---

Explicit user authorization covers GPU testing and public release0.2.33/build82.

## Final GPU qualification

Public source d5810dee431b0c45cc37dd5769145d5b7530d9d6; full execution
fingerprints and geometry measurements are in artifacts/0757-motif-release/qualification.json.
On the M4 Max, all ten final outputs across eight routes passed cardinality,
finiteness, native atom provenance, fixed identities, 60-step/180-recycle scheduling
and per-design native length checks. Five matched standard/optimized designs
across four modes had exactly identical saved tensors and sequences. Variable
lengths were 66 and70 for seeds753 and754, matching native preparation independently.
Repeat start returned the same completed job with all23 output files unchanged.

The original strict0.05A maximum-error criterion was not met. Source-aligned motif
RMSD was0.169A (absolute),1.396A (relative indexed),6.317/3.623A (unindexed), and
0.180A (predicted backbone/redesign). Standard native controls were identical.
This validates software/native parity, not motif design quality. Do not interpret
these examples as validated motifs. Native RFD4 measures adherence separately:
https://rfd4-proteina.org/latest/reference/metrics.html.

The first six raw outputs and failed audit remain intact. Final acceptance uses
explicit native annotated controls and reports geometry failures separately;
there was no relaxation of atom identity or exact tensor equivalence checks.
The predicted source is a retained T4 sequence prediction without templates from
release032; this campaign did not launch a fresh source prediction.

Both Swift builds passed. Three motif contract tests, three generation scheduling/
receipt tests, Swift configuration contracts, packaged-resource checks, archive
checksums and independent Sparkle Ed25519 signature verification passed. Lab0747
records the68-group offline suite, six native input regression tests and viewer
acceptance. This release adds no runtime or model-weight changes. No new refolding,
functional assay, other-Mac qualification, GPU mid-run interruption or memory soak
was performed here; prior kernel qualification is recorded in Lab0741/0743.

Distribution is the existing trusted-beta channel (ad-hoc app signature and signed
Sparkle archive), not an Apple-notarized release. The public diff contains generic
app/CLI/MCP changes, tests, documentation and sanitized qualification evidence;
private research, raw campaigns and weights are excluded.
