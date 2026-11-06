---
entry: 0793
title: Fix atom-label interference in geometry stereochemistry validation
date: 2026-11-06
author: Codex
type: bugfix
status: complete
tags: [ligand, geometry, privacy, regression]
---

## Context

User still encounters the geometry preflight chemical-state mapping rejection.
Do not inspect their confidential molecule, workspace, failed run or scientific
outputs. Reproduce from source using declared generic/public chemistry only.

## Diagnosis and change

Temporary atom-map numbers used to trace Boltz standardization alter RDKit's CIP
ranking. The traced molecule's cached CIP labels were compared against an
unlabelled input. Native standardization of generic deprotonated free biotin
reproduced the rejection despite identical unlabelled stereochemical graphs.
Remove tracing annotations and recompute CIP on copies of both molecules before
comparison. Keep original atom IDs, isotope/edge checks, exact native parser
provenance, output-state equality, symmetry rejection and immutable receipts.
Original generation chemistry and scientific outputs are unchanged.

A reviewed-scoring-state selector was considered and prototyped, then removed
from the final change once a concrete mapping defect was isolated. Such a new
selection basis would need separate handling of native and secondary engine
geometry and must not weaken those contracts.

## Validation

Eight native Boltz CPU regression tests pass, including public deprotonated
free biotin with fused-ring stereochemistry, user atom-map annotations, actual
Figure 4 CLI preflight, real synthetic holo geometry measurement and receipt
reuse. Inverted/lost atom stereo, bond stereo, connectivity, labels, native parser
provenance and symmetry protections still reject invalid inputs. Both generic
holo structures remain byte-for-byte unchanged. The public geometry suite passes
12 tests and explicitly skips one private-coordinate replay. All 24 portable MCP
regressions pass. Private and public Swift builds pass. No GPU work or
confidential inputs are needed. Packaging and delivery are recorded separately. This does not establish that every possible
chemical-state change is mappable; genuine ambiguity/loss remains an error.

## Delivery

Published public release `v0.2.38-beta`, app0.2.38/build89, CLI/MCP58
(bridge1.19.1), from clean public commit
`c1e9d0d50ee9211986e599966069a513dfa6bcfb`. Reviewed the entire public
change; it contains the generic mapping correction, regressions and records.
Public source and live signed update feed are updated. Downloaded ZIP/DMG and
provenance match local artifacts; independent Ed25519 verification passes. All
four changed packaged resources match source, with no weights. Actual geometry
preflight from the downloaded signed app passes the declared public regression;
its sealed code signature remains valid afterward.

Installed and reopened Beta0.2.38-dev/build89 and public0.2.38/build89 using the
previously approved macOS quit/open commands. Retained rollback app copies
locally. No workspace snapshot, UI inspection or confidential molecule access.
Installed shared CLI/MCP58 helper matches source and passes the same public
preflight. There were no active managed jobs, so none was paused or resumed.
Existing frozen jobs and failed run snapshots were not modified; retry using a
new plan/run. The confidential case itself has deliberately not been rerun.
