---
entry: 0203
title: Compare saved biotin RFdiffusion3 and Boltz initialization requests
date: 2026-09-27
author: Codex
type: audit
status: complete
machine: Local saved artifacts; no inference or benchmark
tags: [nise, biotin, rfd3]
---

## Evidence and findings

Read entries0131/0132,0199 and0167 plus authoritative saved requests/design YAMLs.
The older test2 NISE RFD3 attempt nise-CC39D6E2-90C1-4A59-B32B-D597A15D45C4
requested100 starts,65–150 residues, five length bins. Final design.yaml fixes
all ligand atoms, sets COM initialization, nine hotspots
C31,S20,C29,C32,N24,C30,N23,O17,C21, and exposure C25,C22,O18,O19. No buried
selection remains in final design.yaml; the intermediate ligand_base.json's
all-buried default was overridden. It failed at empty-buried-subset metrics;
0131 records two raw PDBs but zero completed backbones. The bug was repaired
and fixture-tested in0132, not a completed broad design comparison.

The0199 portable-launch acceptance includes completed direct ligand RFD3
rfd3-ligand-retry-fixed and NISE nise-dab5f7c8e404edb9. Each requested one65-aa
backbone. Final generator inputs fix all ligand coordinates, with no hotspot,
exposed, buried or donor/acceptor selections; direct RFD3 also sets is_non_loopy.
The direct case completes LigandMPNN/Boltz holo+apo; NISE completes one NESSO
objective cycle. Both use O=C(O)CCCCC1SCC2NC(=O)NC12 without explicit stereochemistry.
These are launch/contract tests, not matched stereospecific biotin quality trials.

Current production nise-3ea5fa63a1effece requests Protein Hunter starts and imports
exactly1000 saved cycle00 units from nise-7345aaf6c30d1a9e. Receipt inputs confirm
1000 sequences, lengths65–150, approximately50% X (rounding varies with length).
Saved YAML has empty MSA and forced pocket contacts to the same nine atoms,
max_distance6Å; physical potentials were enabled. It generates a complex from
sequence/SMILES, rather than fixing a ligand-coordinate motif as RFD3 does.

Current restart refilters the saved structures using biotin-carboxamide-v1 plus
hotspot contacts:754 advance (669open+85restricted, from0167). This replaces the
older terminal-oxygen50% SASA test; no rotation rescue, blocked/unresolved exits
are excluded. These postprediction checks are not generator conditioning. The
geometry policy is shared with the RFD3 route but was not active in the older
RFD3 attempt or the unconstrained one-backbone launch tests.

## Limits

Read-only retrospective audit, no inference, external literature or new geometry
recalculation. Global MCP runs_list failed on a pre-existing symlinked validation
project; inspected saved project requests and Lab Book evidence directly. Did not
establish an exhaustive history outside managed Studio campaigns. No controlled
RFdiffusion3-vs-Boltz efficacy or throughput claim.
