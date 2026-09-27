---
entry: 0205
title: Expose independent NISE RFdiffusion3 conditioning and queue biotin
date: 2026-09-27
author: Codex
type: implementation
status: in-progress
machine: Apple M4 Max, 64 GB unified memory
tags: [nise, rfd3, mcp, release]
---

## Context

User approved app, MCP, GitHub and release updates followed by queueing 1,000
RFdiffusion3 biotin starts. Generation should use method-specific conditioning,
not be restricted to the Boltz initialization settings. Existing running biotin
work must remain intact. The user explicitly selected proceeding with 1,000
rather than a separate small campaign; no new end-to-end model qualification
is claimed by the source and annotation checks below.

## What was done

Added optional rfd3_conditioning object shared by native Swift, MCP schema and
Python contract. It contains independent hotspot, buried, partially buried,
exposed, H-bond donor and acceptor arrays. Null preserves legacy inheritance;
an explicit object replaces all generation selections, including terminal biotin
exposure. Geometry filters remain independent. Validate shared atom signature,
atom membership, disjoint accessibility bins and RDKit donor/acceptor roles.
Record explicit conditioning in generation receipts and reject changed resumes.

Native controls use a per-atom accessibility picker and contact/donor/acceptor
checkboxes. Saved requests decode with no conditioning override. Changing SMILES
clears both sets of choices. MCP also accepts a human-readable NISE run name.

Expose the existing stage-directory PoolBackend through explicit resident_workers
(0=legacy, 1/2=require resident scheduling), in native UI, saved request and MCP
command preview. No default promotion; RFD3 finishes before Boltz loads. Retain
continuation CLI compatibility and reject conflicting explicit worker counts.

## Validation

66 NISE tests passed, including real ligand preparation/translation and model-
boundary interruption/resume, explicit biotin conditioning independent of terminal
SASA suppression, mismatched saved-generation rejection, and fresh managed plan
worker flags. Swift build passed. All 59 fast-suite commands passed, including the Swift
request migration/round-trip harnesses, XCTest, MCP/broker and release contracts.

The installed Foundry DesignInputSpecification parser was exercised on the exact
biotin conformer prepared by the installed RFD3 runtime. Its actual atom arrays
contain nine hotspots, five buried ring atoms, exposed O19, N23/N24 donors and O17
acceptor; fixed-coordinate flags retained. Simultaneous buried/exposed bins survive
(the existing RASA merge repair is installed). Receipt:
artifacts/0205-nise-rfd3-conditioning/annotation_audit.json.
No model loaded or inference performed for this check. Source input preparation
and parser commands/logs remain in build/nise-rfd3-conditioning-check/.

## Planned campaign

New named campaign in test2, not a replacement for the active run. 1,000 RFD3
starts, 65-150 aa, 20 length bins (50 each), 200 diffusion steps, two recycles,
BF16 batch8, two shape queues, seed0 and one fixed stereospecific biotin conformer.
Head hotspots C31,S20,C29,C32,N24,C30,N23,O17,C21; buried
C31,S20,C29,C32,C30; exposed O19; donor N23,N24; acceptor O17.
Existing repeated biotin-carboxamide-v1 exit and 6-A hotspot contact filters.
LASErMPNN/Boltz objective, two refinements of three, early gate0.80, unrestrained
gate3 and 2-A C-alpha self-consistency, expansion5, eight independent lineages,
64 first-cycle proposals, later32 per parent and beam3, 30-cycle cap/patience4,
improvement0.01. No partial noising, adaptive sampling or sequence-only screen.
Two resident Boltz workers with stage batches and automatic bounded CPU geometry.

## Limits

No new throughput, biological efficacy, long campaign completion, fresh-Mac
installation or automatic update acceptance measurement. The conditioning is a
user-selected experimental setting, not a measured optimum. Existing live run
keeps its retained code and runtime; shared staging must respect the execution
lease. No weights are committed or redistributed.

## Next

Publish 0.2.9/build55/MCP30 after release checks; deploy and queue through the
immutable managed plan/job_start path, recording identities and final state.
