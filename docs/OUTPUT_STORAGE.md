# Output storage and retention

Studio treats prediction output as scientific evidence. It does not silently
delete completed results, confidence tensors, failed-run diagnostics or files
needed for Resume. New runs use a lossless storage policy to avoid retaining the
same bytes under several convenient names.

## Canonical results

Each engine keeps its native stochastic structures and compact summary metrics.
`pred_min/model_0.cif`, iterative `cifs_all/` entries and threshold-hit entries
are relative references to the selected canonical structure rather than copies.
`results_index.json` records the canonical path, aliases, trajectory, cycle and
whether the checkpoint counts as an optimized design. Cycle 00 remains a seed,
not a design.

Cycle-wave and resident process logs are also stored once. Per-trajectory log
paths refer to the batch/worker log that actually generated the result.

## Detailed confidence

Protenix full-confidence JSON and IntelliFold detailed-confidence JSON contain
dense pairwise arrays and dominate result size for large jobs. After output
cardinality, ipSAE and geometry checks have completed, Studio writes a gzip file
beside the original, streams it back, and requires the decompressed byte count
and SHA-256 to match. Only then is the plain JSON removed.

`storage_compaction.json` records both sizes, the original SHA-256 and any
failure. A failed compaction leaves the original untouched and does not convert
a scientifically successful prediction into a failed run. Readers and Resume
accept either `.json` or `.json.gz`; small human-readable summary JSON remains
plain.

## Immutable inputs and Resume

Exact A3Ms are stored under `~/.iproteinstudio/objects/sha256/` by content hash
and materialized into each run with an APFS clone, hardlink or verified copy.
The run-local path therefore survives deletion of the source cache or old
project that supplied the alignment.

Iterative policy snapshots are stored once under
`objects/pipeline/sha256/<digest>/`. Each campaign receives an independent APFS
copy-on-write snapshot under `.studio_runtime/pipeline`; editing or deleting one
campaign cannot change another. Resume continues to launch the exact recorded
snapshot and fails loudly when it is missing.

## Sampling provenance

A sampling value of zero/`auto` preserves validated engine defaults; it does not
mean the same thing for every engine:

- Protenix v2 and Mini: five diffusion samples.
- Boltz-2, IntelliFold, Protenix Constraint and OpenFold-3: one diffusion sample.

Plain prediction writes the resolved per-engine values into
`run_summary.json`. Iterative design writes the requested and effective values
into `campaign_budget.json` and prints them at launch.

Existing outputs are never rewritten automatically. Re-running through a new
Studio build updates app-owned aliases safely, while an explicit future storage
management action should be used for bulk migration of historical projects.
