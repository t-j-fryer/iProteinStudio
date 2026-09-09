---
entry: 0013
title: Verify distinct ligand models across an MPNN gap and replay
date: 2026-09-05
author: gpt-6
type: experiment
status: complete
machine: Apple M4 Max, 64 GB unified memory, macOS 26.6.1
tags: [nise, fluorescein, resident-worker, affinity, preorganisation, recovery]
---

## Context

The user requested a dedicated ligand-NISE workflow in Studio and asked that it
incorporate the resident-worker lessons. Existing Boltz residency reused its
structure model for every checkpoint load, whereas ligand affinity requires a
different checkpoint of the same class. Project entry
[[0095-integrate-ligand-nise]] records the complete implementation.

## What was done

Declared a bounded acceptance experiment in
`experiments/nise_integration_v1/campaign.py`. Before inference it wrote an exact
manifest, copied its executed code, fingerprinted source/input/model files and
created a preflight plan in Studio's shared registry. `protocol.json` indexes the
same acceptance endpoints. No paired throughput default was proposed.

The raw attempt is `output/nise_integration_v1/smoke-01/`:

* Plan `plan-7a0b79a61ae67f90`, SHA-256
  `7a0b79a61ae67f904e1acc7dcad6d84e2eeb094ee93c19e74614b78dc60b0064`.
* Broker job `job-7a0b79a61ae6`, completed with exit code 0.
* Input: the recorded sequence of `c09_t4_n0_s23` from the original fluorescein
  trajectory table. The manifest and plan retain that source checksum. This is
  the fluorescein-hydroxyethylamide ligand, not a protein target.
* Two holo requests: first the recorded sequence, then one sequence actually
  sampled by LASErMPNN from that new holo structure. Both requests use the same
  resident session. Apo follows in a separate no-affinity/no-restraint session.
* The driver replays the same work and asserts that no new session starts.

Inputs use explicit empty protein MSAs, so there is no target-A3M checksum or MSA
server request. Code/model fingerprints and the uncommitted working-tree status
are recorded in the raw manifest/plan; the copied snapshot is authoritative.
`system_profiler` and `platform.mac_ver()` confirmed the machine in this header.

## Results

| Condition | n | Metric | Value |
|---|---:|---|---:|
| Holo predictions separated by real LASErMPNN work | 2 predictions | resident sessions | 1 |
| Same holo session | 1 session | distinct structure/affinity model loads | 2 |
| LASErMPNN expansion | 1 parent | sampled sequences, saved for replay | 1 |
| Apo prediction | 1 prediction | separate structure-only sessions | 1 |
| Replay of the complete acceptance sequence | 1 replay | new sessions | 0 |
| Broker job | 1 job | exit code | 0 |

`audit.json` reports passed. Prediction receipts include successful geometry
checks, input checksums and worker load counts; readiness records report MPS and
blanket fallback disabled. The original raw session logs remain available for
the separately documented Boltz SVD exception; those readiness fields alone do
not prove every individual operation ran on MPS.

The acceptance fixture intentionally sends the child to apo analysis regardless
of search selection. Its recorded binder/ligand self-consistency RMSDs were below
the existing thresholds, so its `passed` field does not mislabel a failed
candidate in this attempt. That fixture is not a claim of binding or search
efficacy. Later atom-correspondence and ligand-cardinality guards were executed
against these frozen outputs without refolding them and passed.

No throughput measurements are reported. Raw wall-time and memory fields exist
in the receipts, but this sequential smoke is not a matched speed comparison.

## Decision and rationale

The real structure/affinity lifecycle is usable behind the new explicit
experimental option. Preserve the conservative within-cycle default until a
paired ligand campaign justifies changing it. Apo owns a separate session so
affinity/pocket state cannot carry into a nominally ligand-free check.

## Reproduce

Run the commands in `experiments/nise_integration_v1/README.md` with a new attempt
directory and the original fluorescein run as source. Use the returned plan
digest with `studioctl.py start`. Never edit `smoke-01` to retest newer code.
The raw plan stores the exact full command and source/checkpoint fingerprints.

## Limits and what was not tested

No full real Phase-0-to-convergence campaign, paired scheduler benchmark, long
memory soak, mixed-length stress, worker-death injection during MPS inference,
other Apple hardware or wet-lab binding assay was run. Search Phase-0 interruption
and deterministic replay have fixture coverage in `Tests/test_nise_science.py`;
shared broker cancellation/resume has its separate fake-worker tests. These are
different evidence classes and do not replace the missing real-campaign tests.

## Next

Declare a matched ligand scheduler campaign with explicit model/sample settings,
full output auditing, true MPNN gaps, process death, cancellation/resume and a
memory soak. Record it in both Lab Books before promoting a throughput default.
