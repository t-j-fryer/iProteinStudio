---
entry: 0057
title: Repair the fresh AntiFold hash-locked install
date: 2026-09-01
author: codex-gpt-5
type: bugfix
status: complete
machine: Apple M4 Max, macOS
tags: [antifold, installer, dependencies, hashes, mps, distribution]
---

# Repair the fresh AntiFold hash-locked install

## Context

The first external clean-Mac engine installation from unsigned beta build 3
stopped with `AntiFold hash-locked dependency install failed`. The failure was
reported after the packaged application itself had passed its clean-machine
startup test, so this was investigated as a separate managed-runtime defect.

## Root cause

The failure was reproduced without changing the active runtime:

```text
error: In --require-hashes mode, all requirements must be pinned upfront with ==, but found: packaging
```

`antifold.txt` had been compiled for the validated runtime and then manually
extended with `setuptools==79.0.1` and `wheel==0.48.0`. Published metadata for
`wheel==0.48.0` now resolves `packaging`, but that transitive dependency was not
part of the hash lock. uv therefore correctly rejected the incomplete graph.
AntiFold's pinned source uses setuptools for its editable installation; it does
not require the `wheel` package. The validated pre-existing AntiFold environment
also contained no installed `wheel` package.

## What was done

- Removed the unnecessary `wheel==0.48.0` entry and its hashes from the
  AntiFold lock while retaining the explicitly pinned setuptools backend.
- Documented why the lock must not acquire a manually appended wheel entry.
- Added a lightweight installer contract that fails if `wheel` returns to the
  AntiFold runtime lock without a deliberate re-resolution.
- Made a retry remove only abandoned, installer-owned staging directories for
  that same component before creating a replacement. Unknown, malformed and
  committed directories are preserved.
- Incremented the unsigned beta build number to 4 and added the repair to the
  user-facing release notes.

Adding `packaging` merely to satisfy `wheel` was rejected: it would preserve an
unneeded package and conceal that the hand-edited lock did not describe the
runtime being installed. Removing hash enforcement was also rejected because it
would turn a visible, safe failure into an unreproducible installation.

## Verification

The exact installer toolchain and runtime route were exercised in an isolated
directory:

| Check | Result |
|---|---|
| uv | Exact pinned `0.11.32`, archive SHA-256 verified |
| Python | Exact managed CPython `3.10.18` |
| Environment creation | The installer's `python -m venv` route |
| Hash-locked dependency installation | 35 packages installed successfully |
| AntiFold source | Pinned revision `789d46786624c01eb44f177ef4c0deeeb6e77469` installed editable with `--no-deps --no-build-isolation` |
| Imports | `antifold`, PyTorch `2.2.0` and NumPy `1.26.4` passed |
| Apple GPU | PyTorch reported MPS built and available |
| Real inference | One 9HZJ nanobody-antigen sequence sampled successfully; model log reported `Loaded model to mps` |
| Output cardinality | One requested sample plus the input/reference record were written |
| `swift build` | Passed |
| Installer hardening contract | Passed |
| Failed-stage retry contract | Owned incomplete stage removed; replacement created |
| Unsigned-beta and update contracts | Passed |
| Build 4 packaged resource lock | Byte-identical to source, SHA-256 `ac6cfb7aed1237c0da6037a5f8a2040875eea045ac2d960738047bbc22aa3e16` |
| Read-only DMG launch outside checkout | Remained running for 5 s |

The one-sequence smoke inference used the pinned upstream 9HZJ fixture, CDR1-3,
temperature 0.20, batch size 1 and seed 42. It completed in approximately nine
seconds after model startup on this machine. This timing is diagnostic only, not
a product performance claim.

Build 4 private-test artifacts:

- DMG: `5653741db51e7a17b53e2ac2ae08a7d9db2ce3eb2f35d274f912740465d8356e`
- ZIP: `b652ff80a362df9ecace9be7d35945cdf8c65ce96a40fa6a83839f1db95601e0`

Both entries passed their generated SHA-256 manifest. The DMG was mounted
read-only, reported bundle build number 4, passed the packaged-resource and
signature contract, contained no `wheel` requirement in the AntiFold lock,
contained the owned-stage retry cleanup and launched successfully from the
mounted image.

## Reproduce

The disposable acceptance root was
`/private/tmp/iproteinstudio-antifold-clean-20260901-1`. The substantive commands
were equivalent to:

```bash
uv pip install --python transaction-venv/bin/python --link-mode clone \
  --require-hashes -r Sources/iProteinStudio/Resources/pipeline/locks/antifold.txt
uv pip install --python transaction-venv/bin/python --link-mode clone \
  --no-deps --no-build-isolation -e ~/.iproteinstudio/src/AntiFold
transaction-venv/bin/python antifold/main.py \
  --pdb_file data/nanobody/nanobody_antigen_9hzj_imgt.pdb \
  --nanobody_chain A --antigen_chain B --nanobody_mode \
  --regions 'CDR1 CDR2 CDR3' --num_seq_per_target 1 \
  --sampling_temp 0.20 --batch_size 1 --num_threads 1 --seed 42
```

## Limits and what was not tested

- The full core-plus-AntiFold GUI installation was not repeated because that
  would redundantly install the complete MPNN family and download its models.
  The exact failing dependency stage, subsequent editable build, imports and a
  real MPS inference were tested instead.
- Build 4 has not yet been retried on the reporting second Mac.
- The AntiFold checkpoint download was not repeated; the smoke test used the
  already checksummed pinned checkpoint from the active source checkout.
- No long nanobody campaign or numerical comparison was run; this change is
  confined to installation resolution.

## Next

Retry the engine installation on the clean Mac using build 4. Retry is safe: the
transactional installer does not activate the failed staged environment, and
verified downloads are resumable.
