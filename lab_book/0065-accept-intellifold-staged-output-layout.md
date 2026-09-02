---
entry: 0065
title: Accept IntelliFold outputs below its staged input directory
date: 2026-09-02
author: GPT-5 Codex
type: bugfix
status: complete
machine: Apple M1 Pro acceptance run; implementation verified on Apple M4 Max
tags: [intellifold, mps, prediction, validation, release]
---

## Context

Build 10 was tested on the owner's M1 Pro after its macOS update. Boltz completed
successfully. IntelliFold v2 Flash also loaded its model, selected native MPS with
CPU fallback disabled, completed 10 recycles and 200 sampling steps, and wrote one
structure plus confidence outputs. Studio nevertheless recorded exit code 1.

The downloaded run was `prediction-20260902-124041`. Its log contained both
`IPROTEINSTUDIO_MPS_PATCH|intellifold|advanced_indexing=applied` and
`IPROTEINSTUDIO_DEVICE|intellifold|mps|fallback=0`. The summary confidence reported
pLDDT 0.898 and pTM 0.719. Direct validation of the resulting CIF passed.

## What was done

`validate_prediction_geometry.py` previously rejected any recursively discovered
path containing `_inputs`. Plain Predict deliberately stages YAML there, but
upstream IntelliFold also incorporates that directory name into its canonical
output path: `_inputs/predictions/<job>/<sample>.cif`. The blanket filter therefore
reported that no structures existed after a successful inference.

Structure discovery now excludes arbitrary files beneath `_inputs` while admitting
only its explicit `predictions` child. Unit coverage proves that a staged CIF is
excluded while IntelliFold and ordinary predictor outputs are accepted. The
workflow test now uses the exact `_inputs/predictions` layout and exercises the
complete IntelliFold output-verification function.

## Results

| Condition | n | Metric | Value |
|---|---:|---|---:|
| M1 Pro build-10 IntelliFold v2 Flash | 1 | Direct geometry validation | pass |
| Synthetic staged coordinate input | 1 | Accepted as prediction | no |
| Synthetic `_inputs/predictions` output | 1 | Accepted as prediction | yes |

No new performance measurement was made. The M1 confidence values describe this
single acceptance fold and are not a quality benchmark.

## Decision and rationale

Retain staged-input exclusion, but scope it structurally rather than matching the
directory name anywhere in the path. Removing the exclusion entirely could accept
a user-supplied coordinate as predictor output. Special-casing only the wrapper's
first validator call was rejected because the outer batch validator independently
checks the same output tree.

## Reproduce

```bash
python3 Tests/test_prediction_engine_safety.py
~/.iproteinstudio/venvs/NanoHunter_boltz/bin/python Tests/test_workflow_pipelines.py
python3 Sources/iProteinStudio/Resources/pipeline/scripts/validate_prediction_geometry.py /Users/thomasfryer/Downloads/prediction-20260902-124041/intellifold/bucket_128/chunk_0/_inputs/predictions/Cobratoxin/Cobratoxin_seed-42_sample-0.cif
swift build
```

## Limits and what was not tested

Build 11 was packaged and statically validated on the M4 Max. The corrected complete
Plain Predict handoff still requires one acceptance run from the build-11 DMG on the
M1 Pro. The successful build-10 coordinates were reused for diagnosis; inference was
not repeated because the defect occurred strictly after the completed fold. The
unrelated standalone pipeline-snapshot harness was not revalidated: the selected
Command Line Tools currently pair a Swift 6.3.3 compiler with a 6.3.2 SDK and reject
that clean one-file compile. The repository's required incremental `swift build`
passed, and no snapshot code changed in this fix.

## Next

Install build 11 on the M1 Pro, rerun the same Boltz plus IntelliFold prediction and
confirm both entries appear in the prediction library with exit code zero.
