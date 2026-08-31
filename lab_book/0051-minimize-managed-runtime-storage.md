---
entry: 0051
title: Minimize managed runtime storage without merging incompatible engines
date: 2026-08-31
author: codex-gpt-5
type: implementation
status: complete
machine: Apple M4 Max, 40-core GPU, 64 GB unified memory, macOS 26.x
tags: [installer, dependencies, storage, uv, protenix, reproducibility]
---

## Context

Installer v2 made the runtime deterministic but did not prove that its physical
layout was minimal. The installed root occupied 33 GB. Eight Studio venvs plus
RFdiffusion3's nested venv were present, and standard/Constraint Protenix each
stored the same 625 MB chemical-component dataset. The goal was to remove safe
physical duplication without merging scientifically incompatible environments
or making an installed engine depend on a disposable cache.

## What was done

- Re-audited the installed Python/Torch/NumPy boundaries. The independent
  environments remain intentional: they span Python 3.10/3.11/3.12, PyTorch
  2.2/2.6/2.7/2.13, NumPy 1.23/1.26/2.4 and mutually incompatible Protenix ESM
  policies. No environment was merged merely to reduce the directory count.
- Replaced direct `pip install` calls with the checksum-pinned managed uv binary
  in copy-on-write `clone` mode for every Studio-managed environment. The cache
  and environments are on the same APFS volume. Editable engine installs still
  use `--no-deps --no-build-isolation` over the already hash-locked graph.
- Routed RFdiffusion3's nested installer through the same exact uv binary,
  CPython 3.12.11 and clone-backed cache rather than an ambient `uv`/Python.
- Added one managed bare Git object store per upstream URL. Independent patched
  source worktrees reference that durable store, so standard and Constraint
  Protenix no longer need duplicate Git histories on fresh installs.
- Extended receipts to verify every version in the curated dependency lock,
  while not requiring Protenix's irrelevant CUDA/training extras. Fixed receipt
  auditing so `venv/bin/python` is not resolved to and mistaken for base Python.
- Added interrupted-receipt recovery: an atomically committed `ready` venv with
  no receipt is re-health-checked and receipted on retry rather than rebuilt as
  an identical second version.
- Added `managed_storage.py`, `setup_pipeline.sh --minimize-storage`, and an
  Engines-screen action. It consolidates only a complete enumerated Protenix
  common-data set whose four SHA-256 values match the manifest. Unknown,
  modified or partial directories are retained unchanged.
- Applied that migration to the installed `~/.iproteinstudio` runtime while no
  engine process was active. Both common-data paths now link to
  `shared/protenix-common/v0.5`.

## Results

No predictor-speed or structure-quality benchmark was performed.

| Condition | n | Metric | Result |
|---|---:|---|---:|
| Installed Protenix common-data copies before migration | 2 | verified allocated bytes reclaimable | 655,114,240 |
| Installed shared copies after migration | 1 | allocated size | 625 MB |
| Standard + Constraint post-migration imports | 2 | successful | 2/2 |
| Shared common files | 4 | pinned SHA-256 matches | 4/4 |
| Clean clone-backed MPNN install | 1 | setup final state | `NHDONE\|ok` |
| Clean receipt dependency graph | 21 packages | exact locked versions | 21/21 |
| ProteinMPNN smoke inference, bundled 71-aa target | 1 sample | FASTA/PDB outputs | 1/1 |
| Disposable uv cache clean | 21,951 files | bytes removed | 892.7 MiB |
| Inference after cache clean | 1 sample | FASTA/PDB outputs | 1/1 |
| Partial downloads after cold install | 1 root | `.part` files | 0 |
| Release-mode app assembly | 1 | helper present and ad-hoc signature valid | passed |

The cold run found two defects before release. First, a bare repository's
transient `FETCH_HEAD` was invisible to a child checkout; pinned commits are now
anchored under persistent private refs and consumed through an explicit managed
object alternate. Second, receipt code resolved the venv Python symlink and
audited base Python; receipts now preserve the venv launch path. Both fixes were
retested in the clean root. The resulting MPNN engine continued to import and
perform real inference after its entire uv cache was removed.

## Decision and rationale

Logical isolation and physical duplication are different problems. A single
monolithic environment would reduce folder count while increasing solver
conflicts, silent upgrades and cross-engine breakage. The supported design is
therefore nine honest runtime boundaries with shared immutable storage beneath
them: copy-on-write package payloads, one object store per source repository and
one Protenix chemical dataset.

The minimizer does not delete historical environment versions or source
backups. Automatic timestamp-based pruning was rejected because it can remove a
meaningful rollback without proving that the current engine has passed the
user's workload. **Clear safe caches** remains limited to reconstructable
Studio-owned caches.

## Reproduce

```bash
cd /Users/thomasfryer/iProteinStudio
bash -n Sources/iProteinStudio/Resources/pipeline/setup_pipeline.sh
bash -n Sources/iProteinStudio/Resources/rfd3_overlay/install_rfd3.sh
python3 Tests/test_component_receipt.py
python3 Tests/test_managed_storage.py
bash Tests/test_installer_hardening_contract.sh
bash Tests/test_installer_component_contract.sh
swift build
bash build_app.sh
```

The clean acceptance staged the complete bundled pipeline under `/private/tmp`,
ran the mandatory MPNN install, verified `receipts/mpnn.json --packages`, ran
`--detect`, executed `LigandMPNN/run.py --model_type protein_mpnn` with one batch
and seed 11, cleaned only that root's uv cache, and repeated inference.

## Limits and what was not tested

- The clean install/inference covered the mandatory MPNN family. Optional
  multi-gigabyte engines were not all downloaded again in this entry.
- RFdiffusion3 now shares exact uv/Python/cache policy, but its upstream nested
  requirement file has exact direct versions and a pinned Git dependency rather
  than a complete hash-locked transitive graph.
- Existing standalone Git checkouts and existing pip-created venvs are not
  destructively rewritten in place. Shared Git objects and APFS package clones
  apply when an engine is freshly installed or updated. The verified Protenix
  common-data migration was safe to apply independently and was completed.
- No automatic rollback-history pruning was added. A future cleanup must be
  receipt-aware, show reclaimable bytes, identify exactly which rollback would
  be removed and require explicit user confirmation.

## Next

Run the optional-engine cold-install matrix on a second clean Apple-Silicon
account before a public release. Design an explicit rollback browser before
offering deletion of superseded version history.
