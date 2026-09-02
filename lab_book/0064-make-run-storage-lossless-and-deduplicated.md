# 0064 — Make run storage lossless and deduplicated

**Date:** 2026-09-02

**Status:** Complete implementation and M4 smoke acceptance; M1 acceptance pending

**Hardware:** Apple M4 Max, 40-core GPU, 64 GB unified memory, macOS 26.6.1

## Why

The active managed runtime was 31 GB, but only 348 MB was ordinary user projects;
models and genuinely incompatible environments were the dominant fixed cost. The
scaling problem was instead output representation. Protenix and IntelliFold kept
dense confidence matrices as plain JSON, and iterative campaigns copied selected
structures and one batch log into several convenience directories. Exact MSAs and
the 12 MB scientific policy snapshot were also copied per run.

## What was implemented

- `storage_policy.py` provides streamed SHA-256 gzip verification, transparent
  plain/gzip JSON discovery, atomic relative result references, content-addressed
  immutable inputs and a campaign result index.
- Protenix v2, Mini and Constraint compress `*_full_data_sample_*.json` only after
  ipSAE/normalization; IntelliFold compresses detailed `*_confidences.json` only
  after cardinality, ipSAE and geometry validation. Resident and directory modes
  use the same adapters.
- `pred_min`, `cifs_all`, threshold-hit structures and per-trajectory batch logs
  now refer to canonical output. Existing unknown files are not migrated silently;
  a successful explicit rerun may atomically update its app-owned alias.
- Plain Predict, iterative design, RFdiffusion3 target preparation and OpenFold
  adapter inputs materialize A3Ms through `~/.iproteinstudio/objects/sha256`.
- Iterative pipeline snapshots are content-addressed and materialized as independent
  APFS clones. A test modifies one snapshot and proves the object and a second
  campaign remain byte-identical.
- Sampling provenance now states the real defaults: Protenix v2/Mini use five
  samples at zero/auto; Boltz, IntelliFold, Constraint and OpenFold use one.

## Results

The prior read-only audit measured 1.190 GB of Protenix full-confidence JSON,
336.9 MB of IntelliFold detailed-confidence JSON and 518.3 MB of exact duplicate
structures across current projects plus the governed resident validation output.
Those figures describe the audited data, not space already reclaimed; historical
outputs were deliberately not modified.

Two fresh, isolated native-MPS predictions exercised the production adapters:

| Engine/input | n | Original detailed JSON | Verified gzip | Reduction |
|---|---:|---:|---:|---:|
| IntelliFold v2 Flash, 121-aa VHH, seed 42/sample 0 | 1 | 358,794 B | 130,699 B | 63.6% |
| Protenix Mini, 121-aa VHH, seed 42/sample 0 | 1 | 726,563 B | 85,470 B | 88.2% |

Both runs used native MPS, explicit single-sequence input, emitted the exact
requested structure count and passed the production geometry validator. Protenix
`pred_min` entries were verified relative symlinks to its canonical CIF and summary.
These are storage smoke tests, not quality or throughput benchmarks.

Behavioral contracts also proved exact gzip round trips, safe retry after a
hypothetical crash between gzip publication and original deletion, compressed
Protenix ipSAE Resume, stale-alias replacement, durable MSA materialization after
source deletion, campaign indexing and independent APFS pipeline snapshots.

## Decision and rationale

The default policy is lossless compaction, not deletion of scientific arrays.
Summary-only output would save more space but would prevent later metric work.
Hardlinking pipeline code was rejected because editing one run could mutate every
campaign; APFS clones retain block sharing with independent inodes. Gallery copies
were replaced by references because they were byte-identical views, not distinct
scientific samples.

## Reproduce

```bash
python3 Tests/test_storage_policy.py
bash Tests/test_pipeline_snapshot.sh
~/.iproteinstudio/venvs/NanoHunter_boltz/bin/python Tests/test_workflow_pipelines.py
bash Tests/test_iterative_cli_contract.sh
swift build
```

Real smoke-test outputs were written under
`/private/tmp/iproteinstudio-storage-smoke.EZq5mr/`. Commands used the repository
adapters with `NANOHUNTER_ROOT=~/.iproteinstudio`, one seed and one sample.

## Limits and what was not tested

Historical projects were not compacted or rewritten. No interrupted live GPU run
was killed between compression transaction steps; that boundary is covered by a
synthetic two-copy recovery test. Boltz/OpenFold/RFdiffusion3 did not need dense
JSON compression and were not re-folded for this entry. Full Protenix v2 and
Constraint use the same tested adapter but were not separately run. The updated
DMG still requires acceptance on the owner's updated M1 Pro, including a real
Predict job, iterative Resume and result-gallery opening.

## Next

Run the unsigned-beta DMG on the updated M1 Pro. If accepted, consider an explicit
user-invoked historical-project migration that reports estimated and actual bytes
without ever touching active or incomplete campaigns.
