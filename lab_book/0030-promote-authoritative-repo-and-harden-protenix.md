---
entry: 0030
title: Promote the authoritative repo and harden the Protenix install
date: 2026-08-21
author: codex-gpt-5
type: implementation
status: complete
machine: Apple M4 Max, 40-core GPU, 64 GB unified memory, macOS 26.6.1
tags: [repository, runtime, installer, protenix, msa, uninstall, reproducibility]
---

## Context

Protenix installation appeared to remain at one progress position despite a fast
connection. Work had also diverged between `/Users/thomasfryer/iProteinStudio`
and an older `/Users/thomasfryer/NanoHunterStudio` working copy, while the app's
managed files were visible under the similar but hidden `~/.iproteinstudio`.
Before changing the installer, the source/runtime boundary and every relevant
checkout had to be resolved without deleting user work.

The validated Protenix v2/Mini MPS work existed only in the older working copy.
It was ported selectively into the newer authoritative repo; files were not
copied wholesale because that would have restored the AlphaFold 3 and IntelliFold
JAX/Metal routes retired by [[0029-retire-untrusted-jax-metal-predictors]].

## Repository and runtime audit

| Path | Role at start | Git state / measured size |
|---|---|---|
| `/Users/thomasfryer/iProteinStudio` | authoritative Studio source | `main`, `40284c7` before this work, newer uncommitted product/QC changes; ~1.5 GB |
| `/Users/thomasfryer/NanoHunterStudio` | superseded Studio working copy where Protenix work first landed | `agent/standalone-intellifold-install`, `7e7e850`, dirty; ~2.0 GB |
| `/Users/thomasfryer/.iproteinstudio` | active managed runtime, not a Git repo | models, venvs, staged scripts, projects and MSA caches; ~28 GB before Protenix finished |
| `/Users/thomasfryer/NanoHunter` | legacy/upstream iterative-science development checkout | `main`, `434b8ff`, dirty; ~35 GB |
| `/Users/thomasfryer/RFD3` | upstream RFdiffusion3/MLX development checkout | `main`, `a871ccf`, dirty; ~6.3 GB |
| `/Users/thomasfryer/iProteinHunter` | older legacy checkout | `7e2637b`, dirty |

`/Users/thomasfryer/.iproteinstudio_freshtest` no longer exists. No checkout,
model, project, result or cache was deleted. The authoritative source is now
`/Users/thomasfryer/iProteinStudio`; its built app is the only Studio bundle
launched during acceptance. The other Git checkouts remain references until the
owner explicitly chooses to archive or delete them.

The hidden runtime is intentional, not a duplicate source repository. Models and
Python environments must not live in Git or inside the replaceable app bundle.
The space-free home-directory path is also required because Python console-script
shebangs break under `Application Support`, whose name contains a space.

## What was done

- Reproduced the stall at exactly 1,300,234,240 bytes in
  `protenix-v2.pt.part`. The downloader process retained an established TLS
  socket but wrote no bytes for more than 40 minutes. A separate HTTP Range
  request to the same immutable Hugging Face URL immediately returned HTTP 206,
  isolating the fault to the old no-timeout read loop rather than the connection
  or server.
- Stopped only the stalled downloader and retained the 1.30 GB partial file.
- Added `scripts/download_verified.py`: timed connects/reads, HTTP Range resume,
  bounded retry/backoff, byte-level `NHSTEP` progress, exact expected-length
  checks, pinned SHA-256 verification and atomic final replacement. Transient
  failure keeps `.part`; a checksum mismatch removes untrusted bytes.
- Added a local regression server that deliberately disconnects after 700,000
  bytes. The real helper resumed with Range, completed a 2.4 MB artifact, verified
  its digest and removed the partial file.
- Integrated one Protenix component containing pinned upstream 2.0.0 source,
  the reviewed native-MPS patch, inference-only dependency lock, both checkpoints
  and required chemical data. No weights are in Git. CPU fallback is refused.
- Added Protenix v2 and Mini to Predict, Target Prep, iterative design/checking
  and RFdiffusion3 verification. Both use one YAML-to-Protenix adapter, the same
  durable input A3Ms and distinct result identities. v2 is accuracy-first; Mini
  is labelled a preview.
- Used upstream `protenix msa` for a missing alignment whenever a Protenix model
  is selected. Protenix no longer depends on Boltz. Query-only recovery output
  is rejected, generated A3Ms are query-validated and atomically cached, and
  provider failure never silently changes scientific inputs.
- Added component-scoped uninstall with confirmation, live-process protection,
  lexical managed-root containment and a fixed target allow-list. Engine source,
  environments and weights can be removed; projects, results, shared MSAs and
  scaffold MSAs cannot.
- Prevented Protenix Mini and v2 from being described as independent validators
  of each other in iterative and RFdiffusion3 workflows. Plain Predict may still
  run both for a useful same-family comparison.
- Rebuilt and launched
  `/Users/thomasfryer/iProteinStudio/build/iProteinStudio.app`; startup staged
  the authoritative resources into `~/.iproteinstudio`. The old bundle under
  `NanoHunterStudio/build` was not running.

## Results

The interrupted real installer resumed at 1.30 GB, rather than downloading v2
again, and progressed normally under `caffeinate`. It verified the immutable
1,859,785,497-byte v2 checkpoint before downloading Mini and common data. The
complete install ended with `NHDONE|ok`; final detection reported Boltz, MPNN,
AntiFold, IntelliFold PyTorch, Protenix, OpenFold-3, LASErMPNN and RFdiffusion3
all `ok`.

The model-quality and compatibility figures below were measured earlier on the
same machine in the superseded working copy and are preserved here because this
entry promotes that implementation into the authoritative repo; they were not
remeasured during the installer repair.

| Model/route | n | Whole inference phase | 2CTX C-alpha RMSD | C-alpha lDDT | pTM |
|---|---:|---:|---:|---:|---:|
| Protenix Mini, upstream-ranked sample 0 | 1 | 5.61 s | 2.723 Å | 0.8234 | 0.8600 |
| Protenix v2, upstream-ranked sample 0 | 1 | 17.23 s | 2.163 Å | 0.8545 | 0.8977 |
| Boltz-2 model 0 comparator | 1 | not measured in that run | 2.044 Å | 0.8430 | 0.8630 |
| IntelliFold PyTorch v2-flash comparator | 1 | not measured in that run | 2.706 Å | 0.8290 | 0.7194 |

These were the same 71-residue cobratoxin sequence and shipped A3M (Protenix
featurisation `N_msa=1087`) against exact-sequence X-ray 2CTX. They are narrow
compatibility observations, not a general benchmark. The two Protenix models
share an AlphaFold-3-family architecture and are not independent evidence.

Acceptance checks:

| Check | Result |
|---|---|
| Forced-disconnect downloader resume/checksum test | passed |
| RFdiffusion3/plain-prediction Python contracts | passed |
| Iterative CLI contract | passed |
| Bash syntax + Python compilation | passed |
| Debug Swift build | passed |
| Release `.app` assembly | passed |
| Ad-hoc signature verification (`codesign --deep --strict`) | passed |
| Authoritative bundle resource staging | passed |
| Managed Protenix install detection + native-MPS probe | passed |
| Installed Mini production adapter (71 aa, seed 42, five samples) | 2.06 s model forward; 5.04 s job; pLDDT 88.265; pTM 0.8600 |
| Installed v2 production adapter (71 aa, seed 42, five samples) | 16.19 s model forward; 19.14 s job; pLDDT 90.151; pTM 0.8977 |
| Staged GUI plain-Predict driver, Mini, offline cached MSA | 1/1 cache hit; 1/1 fold; 18.1 s driver wall; `PBDONE|ok` |
| Live Protenix-native MSA route, 71 aa cobratoxin | 6,371 records; exact query retained; 987,622-byte A3M; temporary work directory cleaned |

## Decision and rationale

1. `/Users/thomasfryer/iProteinStudio` is the only Studio source of truth.
   `~/.iproteinstudio` remains the only active runtime and must stay outside Git.
2. Both Protenix models remain visible. Mini is roughly three times faster on the
   one measured fixture and useful for preview; v2 had better reference agreement
   and is the accuracy-first choice.
3. Protenix is an independent install but not an independent *model family* from
   its own Mini checkpoint. Its upstream MSA client removes any Boltz dependency.
4. Installer progress represents bytes transferred, not a guessed phase fraction.
   A dead connection must visibly retry rather than leave a plausible progress bar
   waiting forever.
5. The duplicate source working copies are retained until explicit cleanup is
   authorized. A dirty scientific checkout is not safe to delete merely because a
   newer application repo exists.

## Reproduce

```bash
cd /Users/thomasfryer/iProteinStudio

bash -n Sources/iProteinStudio/Resources/pipeline/setup_pipeline.sh
bash -n Sources/iProteinStudio/Resources/pipeline/nanohunter_run.sh
python3 Tests/test_verified_downloader.py
/Users/thomasfryer/.iproteinstudio/venvs/NanoHunter_boltz/bin/python \
  Tests/test_workflow_pipelines.py
bash Tests/test_iterative_cli_contract.sh
swift build
./build_app.sh

# Runtime installation/detection; all long work stays caffeinated.
caffeinate -dimsu bash /Users/thomasfryer/.iproteinstudio/setup_pipeline.sh \
  --with-protenix
bash /Users/thomasfryer/.iproteinstudio/setup_pipeline.sh --detect

# Production-adapter acceptance used an existing exact-sequence Cobratoxin YAML
# with the 1,087-row cached A3M, once with --model mini and once with --model v2.
# Both commands used the managed scripts/protenix_predict.py and were wrapped in
# caffeinate -dimsu.

# The complete GUI batch route was also exercised without server access:
caffeinate -dimsu /usr/bin/python3 \
  /Users/thomasfryer/.iproteinstudio/rfd3_scripts/predict_batch.py \
  --config /private/tmp/iproteinstudio-protenix-plain-smoke-config.json

# The Protenix-native public MSA route was exercised live under caffeinate:
caffeinate -dimsu \
  /Users/thomasfryer/.iproteinstudio/venvs/NanoHunter_protenix/bin/python \
  /Users/thomasfryer/.iproteinstudio/scripts/protenix_msa.py \
  --sequence IRCFITPDITSKDCPNGHVCYTKTWCDAFCSIRGKRVDLGCAATCPTVKTGVDIQCCSTDNCNPFPTRKRP \
  --output /private/tmp/iproteinstudio-protenix-msa-20260821.a3m \
  --nanohunter-root /Users/thomasfryer/.iproteinstudio \
  --work-dir /private/tmp/iproteinstudio-protenix-msa-work-20260821
```

## Limits and what was not tested

- The downloader regression forces an early disconnect, not a truly silent TCP
  half-open; the real stalled install and subsequent timed resume cover the latter
  operationally.
- The uninstall implementation compiled but no multi-gigabyte installed engine was
  deleted during acceptance. The fixed allow-list and symlink behavior should still
  receive a disposable-root click test.
- Protenix scientific validation remains one old, likely training-set monomer.
  No blinded post-cutoff set, protein complex, protein-ligand case, CUDA parity,
  paired MSA, multiple-seed or maximum-token run was added here. The public MSA
  route was tested live for the single cobratoxin chain and returned 6,371
  records; server availability and biological coverage will vary by query.
- The live ligand-PDB unittest was not run because the system Python lacks RDKit;
  its unrelated contract was not changed.
- The pre-existing dirty work in the authoritative repo was preserved. This entry
  does not claim that every older uncommitted feature has been committed or pushed.

## Next

Run a Protenix target-prep fold and one RFdiffusion3 verification job from GUI
controls, then exercise uninstall/reinstall in a disposable managed root. Archive
the superseded `NanoHunterStudio` checkout only after its remaining diff has been
reviewed against this authoritative tree.
