---
entry: 0052
title: Audit and archive the pre-standalone runtime
date: 2026-08-31
author: codex-gpt-5
type: audit
status: complete
machine: Apple M4 Max, 40-core GPU, 64 GB unified memory, macOS 26.x
tags: [installer, storage, migration, projects, alphafold3, boltz]
---

## Context

The active managed runtime still coexisted with
`~/.iproteinstudio_before_standalone_20260813`, a 23 GB snapshot made during the
standalone migration. It was not installer-v2 rollback state. The owner asked to
recover the space, but the snapshot contained projects and licensed AlphaFold 3
parameters that must not be treated like reproducible package caches.

The same audit also found that the active legacy Boltz installation retained the
downloaded `mols.tar` after successfully extracting the runtime `mols/` dataset.
The current installer already removes that archive.

## What was done

- Recomputed the active Boltz archive's SHA-256 and confirmed it matched the
  installer pin, then confirmed the extracted dataset contained 45,227 files.
- Removed only the redundant active `models/boltz2/mols.tar` and reran the Boltz
  MPS import and Studio component detection.
- Checksum-compared the historical projects, MSA cache, target predictions,
  thumbnails and scaffold MSAs against the active installation. No historical
  project path was absent from the active tree, but an older Cobratoxin result
  and prediction configuration differed from the later active rerun.
- Confirmed the historical Boltz confidence and affinity checkpoints were
  byte-identical to the active copies.
- Identified the historical `af3.bin` as licensed, non-installer-reconstructable
  user material and fingerprinted it before preservation.
- Created the visible archive
  `~/iProteinStudio Legacy Archive/before_standalone_20260813` containing the
  complete historical project snapshot, app configuration, user-facing caches,
  RFdiffusion3 oracle/benchmark/notes artifacts and the AF3 parameters.
- Checksum-verified the copied project and RFdiffusion3 trees and the AF3 file.
- Requested and received explicit user confirmation for the exact irreversible
  deletion, then removed only
  `~/.iproteinstudio_before_standalone_20260813`.
- Rechecked the preserved AF3 fingerprint, active-runtime footprint, filesystem
  availability and every Studio engine's detection state after deletion.

## Results

| Condition | n | Metric | Value |
|---|---:|---|---:|
| Redundant active Boltz archive | 1 | removed bytes | 1,855,662,080 |
| Extracted active Boltz CCD dataset | 45,227 files | retained logical size | 1.8 GB |
| Boltz after archive removal | 2 checks | MPS import / Studio detection | passed / passed |
| Historical project snapshot | 1 tree | logical size | 68 MB |
| Preserved visible archive | 1 tree | logical size | 1.2 GB |
| Preserved AF3 parameter file | 1 | SHA-256 | `8be886bf5a798e4bbaeee3af14ba4c827674041f44b71fadccee2dd6020dd1c7` |
| Obsolete historical installation | 1 tree | post-audit state | removed |
| Filesystem before / after historical-tree deletion | 1 deletion | available space | 399 GiB / 421 GiB |
| Active managed runtime after both cleanups | 1 tree | logical size | 31 GB |
| Active component detector after deletion | 12 reported capabilities | healthy states | 12/12, `NHDONE|ok` |

No predictor-speed or structure-quality measurement was performed.

## Decision and rationale

Installer payload and user state must have different deletion policies. A model
or environment may be reproducible, but an old prediction, configuration or
licensed parameter file is not. The historical tree will therefore be removed
only after its user material has a verified independent copy and the owner has
explicitly approved the exact irreversible deletion. Both conditions were met,
and the obsolete tree was removed.

The old AF3 parameters are archived rather than restored into the active model
directory. AlphaFold 3 remains retired from Studio's Apple-GPU engine set; this
preservation is data custody, not engine re-enablement.

## Reproduce

```bash
test ! -e ~/.iproteinstudio/models/boltz2/mols.tar
find ~/.iproteinstudio/models/boltz2/mols -type f | wc -l
NANOHUNTER_ROOT=~/.iproteinstudio \
  bash Sources/iProteinStudio/Resources/pipeline/setup_pipeline.sh --detect
shasum -a 256 \
  ~/iProteinStudio\ Legacy\ Archive/before_standalone_20260813/alphafold3_parameters/af3.bin
test ! -e ~/.iproteinstudio_before_standalone_20260813
du -sh ~/iProteinStudio\ Legacy\ Archive/before_standalone_20260813 \
  ~/.iproteinstudio
```

## Limits and what was not tested

- The visible archive is a preservation snapshot, not an app-import format. The
  active app continues to use its newer project state.
- The old retired IntelliFold-JAX checkpoint was not preserved separately.
- No restoration drill was performed because the archive is a direct,
  checksum-matched file-tree copy rather than a transformed backup.
- The pre-deletion source-to-archive `rsync -ainc --delete` comparison cannot be
  repeated after deletion; its zero-difference result is the audit evidence that
  authorized the deletion.

## Next

No immediate follow-up. Keep the visible legacy archive until the older
Cobratoxin result and licensed AF3 parameters are deliberately retired or moved
to the owner's long-term research backup.
