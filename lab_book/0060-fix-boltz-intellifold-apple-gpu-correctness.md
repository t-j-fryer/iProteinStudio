---
entry: 0060
title: Make Boltz and IntelliFold Apple-GPU output fail-safe
date: 2026-09-01
author: codex-gpt-5
type: bugfix
status: superseded
machine: Apple M4 Max, 40-core GPU, 64 GB unified memory, macOS 26.6.1; affected external Apple-Silicon Mac model not recorded
tags: [prediction, boltz, intellifold, mps, numerical-correctness, geometry]
---

## Context

Five plain-Predict exports from the external DMG installation folded the same
74-residue disulfide-rich protein with a Protenix-generated MSA. Protenix Mini
returned a plausible structure, two Boltz runs returned visibly fragmented
structures despite exit code 0, and IntelliFold v2-flash aborted inside Apple's
MPS `GatherND`. The sequence identity was incidental; a predictor that accepts
an input must either produce valid coordinates or fail clearly.

## What was done

- Proved that every engine received the same A3M byte-for-byte. It contained an
  exact 74-column query and 5,179 valid aligned records; every record retained
  exactly 74 aligned columns after lower-case insertions were removed.
- Compared the downloaded outputs with PDB 2ABX and checked backbone continuity,
  nonlocal clashes and the five expected disulfide pairs. This established that
  the Boltz files—not the viewer—were chemically broken.
- Re-ran the exact Boltz 2.2.1 command, checkpoint, seed, sequence and MSA on the
  M4 Max. It was good there, isolating a device/OS-sensitive numerical path.
- Found that pinned Boltz unconditionally requests `bf16-mixed` for Boltz 2 on
  every GPU, including Apple MPS. Added `scripts/boltz_mps.py`, which requires
  native MPS, forbids user-enabled CPU fallback and forces FP32. Plain Predict,
  target preparation, RFdiffusion3, iterative cycle waves and resident workers
  now all use this launcher.
- Found IntelliFold's exact failing v2/v2-flash expression: a broadcast
  multidimensional token-pair lookup lowered to MPS `GatherND` with the 550-atom
  index width reported by the crash. Replaced it with an equivalent flattened
  per-batch `index_select`, applied atomically under a file lock. The trained
  v2 configuration, weights, recycles, sampling steps and MSA remain unchanged.
- Added a shared coordinate validator. Any protein CA-CA step over 4.5 Å,
  peptide C-N distance over 2.2 Å, non-finite coordinate or output with no
  protein CA atoms fails the job before its completion marker is written.
  Previously completed outputs are checked again before resume reuse. The
  PDB/mmCIF validator uses only Python's standard library so independently
  installed IntelliFold does not acquire a hidden dependency on Boltz.
- Overrode Boltz's faulty asset downloader boundary. Upstream checks for
  `mols.tar` even when the verified extracted `mols/` library exists; Studio now
  treats its managed extracted assets as authoritative and never downloads
  checkpoints or CCD data silently during inference.
- Removed the 601 MiB truncated `mols.tar` that the upstream check created during
  diagnosis; the complete 45,000-file extracted CCD library was retained.

## Results

| Condition | n | Metric | Value |
|---|---:|---|---:|
| External Protenix Mini control | 1 | Cα RMSD to 2ABX / pTM | 3.318 Å / 0.831 |
| External Boltz, no potentials | 1 | Cα RMSD / maximum peptide C-N | 11.355 Å / 6.406 Å |
| External Boltz, potentials | 1 | Cα RMSD / maximum peptide C-N | 13.169 Å / 15.418 Å |
| External IntelliFold v2-flash | 1 | result | MPS GatherND assertion, exit -6 |
| M4 Max repaired Boltz FP32 | 1 | Cα RMSD / pTM / pLDDT | 4.827 Å / 0.857 / 0.850 |
| M4 Max repaired IntelliFold v2-flash | 1 | Cα RMSD / pTM / pLDDT | 3.509 Å / 0.681 / 0.865 |
| M4 Max repaired Boltz | 1 | prediction pass / command wall time | 5.2 s / 22.4 s |
| M4 Max repaired IntelliFold v2-flash | 1 | inference pass | 39.3 s |
| Geometry gate, known broken Boltz export | 1 | accepted | no; 30 discontinuities reported |
| Geometry gate, good Protenix export | 6 structures | accepted | yes |

RMSDs are Cα least-squares superpositions against the crystallographic chain
and are used only as a regression diagnostic, not as a general predictor
benchmark. The local Boltz mixed-precision reproduction was also valid on the
M4 Max, so FP32 is a portability/correctness boundary rather than a claim that
every Apple GPU produces bad bfloat16 results.

## Decision and rationale

Boltz uses FP32 on Apple MPS. A modest precision optimization cannot be allowed
to vary scientific validity by Mac model, especially when the engine reports a
high-level success. IntelliFold retains v2/v2-flash and native MPS because its
failure was a single unsupported indexing formulation with an exact equivalent;
retiring the model or enabling CPU fallback would be disproportionate.

Independent geometry validation remains mandatory even after both root-cause
repairs. It converts future numerical regressions into explicit failed jobs and
prevents bad outputs from becoming resumable/library results.

This root-cause interpretation was superseded by [[0061-finish-m1-predictor-correctness]].
Build 8 on the affected M1 Pro proved that FP32 did **not** repair Boltz: it
produced 113 backbone discontinuities that the new validator correctly rejected.
The first IntelliFold replacement also exposed a second upstream `GatherND`
formulation. The geometry gate remains valid; the assertion that bfloat16 was
the Boltz root cause does not.

## Reproduce

```bash
python3 -m unittest Tests/test_prediction_engine_safety.py Tests/test_prediction_msa_reliability.py

NANOHUNTER_ROOT="$HOME/.iproteinstudio" \
  caffeinate -dimsu "$HOME/.iproteinstudio/venvs/NanoHunter_boltz/bin/python" \
  "$HOME/.iproteinstudio/scripts/boltz_mps.py" predict INPUT.yaml \
  --out_dir OUTPUT --cache "$HOME/.iproteinstudio/models/boltz2" \
  --accelerator gpu --devices 1 --num_workers 0 --override

NANOHUNTER_ROOT="$HOME/.iproteinstudio" PYTORCH_ENABLE_MPS_FALLBACK=0 \
  caffeinate -dimsu "$HOME/.iproteinstudio/venvs/NanoHunter_intellifold/bin/python" \
  "$HOME/.iproteinstudio/scripts/intellifold_predict.py" INPUT.yaml \
  --out_dir OUTPUT --precision no --num_workers 0 --model v2-flash \
  --cache "$HOME/.iproteinstudio/models/intellifold" --override
```

The real validation used the exact downloaded A3M and seed 42, 200 diffusion
steps, ten IntelliFold recycles and one diffusion sample.

## Limits and what was not tested

- The repaired beta has not yet been run on the external Mac that produced the
  original Boltz corruption and IntelliFold assertion; the geometry gate makes
  a false success impossible there, but that machine is the decisive portability
  acceptance test.
- One 74-residue monomer and one seed/sample were used for the paired repair.
  Multimers and ligands use the same affected launchers but were not rerun here.
- Full IntelliFold v2 shares the repaired advanced-conversion expression but
  was not rerun in this acceptance; v2-flash was the observed failure.
- FP32 throughput was measured once on the M4 Max and is not a cross-device
  performance claim.

## Next

Install unsigned beta build 8 on the affected Mac and repeat Boltz and
IntelliFold on the same cached MSA. Record that Mac's model and macOS version in
the follow-up. If either engine fails, share its preserved log; invalid geometry
will now be reported explicitly rather than entering the prediction library.
