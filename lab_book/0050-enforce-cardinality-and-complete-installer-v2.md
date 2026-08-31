---
entry: 0050
title: Enforce iterative cardinality and complete installer v2
date: 2026-08-31
author: codex-gpt-5
type: implementation
status: complete
machine: Apple M4 Max, 40-core GPU, 64 GB unified memory, macOS 26.x
tags: [iterative-design, cardinality, results, installer, reproducibility, transactions]
---

## Context

A student reported that iterative campaigns appeared to stop at approximately
72–73 structures regardless of the count selected in the GUI, and that opening a
live design structure could leave a small window that could not be closed. The
installer audit in entries 0047–0049 also retained a defined second roadmap:
exact managed toolchains, complete dependency locks and receipts, transactional
versioned environments, capability-level checkpoints, shared Protenix data,
safe cache management, immutable campaign code and real cold-install acceptance.

The 72 symptom was also a terminology problem: the historical 12-trajectory,
5-cycle default produces 12 cycle-00 starts plus 60 optimized checkpoints = 72
structures. Cycle 00 is not a design. The software nevertheless needed an
end-to-end contract proving that a non-default GUI value could not be ignored.

## What was done

### Iterative cardinality and result presentation

- Renamed the GUI control to **Independent trajectories** and show the exact
  requested product: trajectories × optimized cycles, with cycle-00 starting
  structures reported separately.
- Recorded requested trajectories, cycles and expected optimized structures in
  `studio_run.json`, and wrote `campaign_budget.json` before compute begins.
- Added `scripts/audit_design_cardinality.py`. A successful runner now requires
  exactly `N_RUNS × N_CYCLES` complete optimized checkpoints plus `N_RUNS`
  complete cycle-00 starts. It writes an atomic
  `design_cardinality_receipt.json` and fails loudly on a short campaign.
- Kept `--num-runs` and `--num-opt-cycles` explicit in the Swift command and
  exposed both values plus the expected product in `--check-config` output.
- Classified cycle 00 as an unoptimized starting structure in the live dashboard
  and persistent results browser, not as an optimized design or hit.
- Moved structure-inspector sheet ownership out of refreshable design tiles and
  into the stable grid/gallery parents. The inspector now uses SwiftUI's
  environment dismissal, a visible **Close** button and Escape.

### Installer v2

- Pinned uv 0.11.32 by official archive SHA-256 and exact CPython 3.10.18,
  3.11.13 and 3.12.11 under the Studio root; ambient Python is not used to
  construct an engine.
- Added nine complete Apple-Silicon dependency graphs with hashes enforced by
  `pip --require-hashes`. Editable engine builds use the locked build backend
  with `--no-build-isolation --no-deps`.
- Added comprehensive atomic receipts containing exact Python, complete resolved
  packages, pinned source revision, tracked patch-state digest, artifact hashes
  and device policy.
- Added versioned environment staging, import/accelerator health checks, atomic
  legacy-path activation, recoverable prior-version retention and rollback.
- Split Boltz affinity, IntelliFold full v2, Protenix v2 and Protenix Mini into
  independently installable/removable checkpoints over shared runtimes.
- Unified all managed checkpoints, including IntelliFold and OpenFold, onto the
  timeout-aware resumable downloader. IntelliFold artifacts use immutable model
  revision `8f5ec8ab39e89fabf1887e54fe5ce588aaaaf890`; OpenFold uses the range-capable
  official S3 HTTPS object. Final filenames appear only after SHA-256 succeeds.
- Stored one verified Protenix chemical-data copy for the standard and Constraint
  products while retaining their scientifically distinct environments.
- Added Essentials, Independent validation and Complete presets, accurate
  checkpoint-only removal, managed-file reveal and cleanup limited to
  Studio-owned uv/pip/Numba caches. Cache sizing runs off the SwiftUI render path.
- Blocked install/update while any process is using a managed venv.
- Bound each new iterative run to an immutable app-owned pipeline snapshot under
  the campaign. Resume uses the recorded snapshot and fails if it is absent.

## Results

No predictor-speed or GPU-quality benchmark was performed in this entry.

| Condition | n | Metric | Value |
|---|---:|---|---:|
| Non-default GUI/CLI contract | 37 trajectories × 7 optimized cycles | expected optimized structures | 259 |
| Cardinality fixture, complete | 259 optimized + 37 cycle-00 | receipt status | passed |
| Cardinality fixture, one optimized output removed | 1 | runner/auditor status | failed as required |
| Versioned runtime transaction | 1 update + 1 invalid stage | preserved live version | 2/2 |
| Component receipt | package/source/artifact mutations | detected | 3/3 |
| Hash-lock graphs | 9 | complete, portable, all requirements hashed | 9/9 |
| Isolated cold minimal install | 1 | final root logical size | 1.1 GB |
| Cold toolchain | 1 | Python/Torch/NumPy | 3.11.13 / 2.2.1 / 1.23.5 |
| Cold MPNN capability detection | 1 | state after install | `ok` |
| Cold receipt/package verification | 1 | status | passed |
| Cold ProteinMPNN inference, 71-aa bundled target | 1 sampled design | FASTA outputs | 1/1 |
| Exposed partial downloads after cold install | 1 root | `.part` files | 0 |

The first cold attempt found a real migration defect: the newly resolved
setuptools 84 no longer provided `pkg_resources`, which ProDy imports at runtime.
The installer had passed its initial `torch,numpy` health check but real
ProteinMPNN inference failed. MPNN now pins the validated setuptools 79.0.1;
editable builds pin their build backends and forbid isolated dependency fetches.
A second genuinely clean install and real inference passed.

## Decision and rationale

The user-facing quantity is optimized structures, not all intermediate files.
The runner therefore treats the GUI's trajectory and cycle values as a durable
campaign budget and independently audits the filesystem before final summaries.
Cycle 00 remains valuable provenance but is never counted as a design.

Structure sheets belong to stable collection views. A tile in a live, frequently
recomputed grid is not a reliable presentation owner; destroying it can orphan
its window state.

The nine environment boundaries remain. Measured incompatibilities and the
Constraint ESM-absence contract make a monolithic environment less reproducible,
not simpler. Installer v2 instead standardizes the lifecycle around those
islands: one toolchain policy, lock format, receipt, downloader, transaction and
user-facing manager.

## Reproduce

```bash
cd /Users/thomasfryer/iProteinStudio

python3 Tests/test_design_cardinality.py
python3 Tests/test_component_receipt.py
python3 Tests/test_runtime_transaction.py
python3 Tests/test_installer_lock_contract.py
bash Tests/test_iterative_cli_contract.sh
bash Tests/test_iterative_results_ui_contract.sh
bash Tests/test_installer_hardening_contract.sh
bash Tests/test_installer_component_contract.sh
python3 Tests/test_verified_downloader.py
swift build
```

The cold acceptance copied the bundled pipeline into a `mktemp -d` root under
`/private/tmp`, ran `setup_pipeline.sh` with no optional engines under
`caffeinate`, verified `receipts/mpnn.json --packages`, ran `--detect`, then
executed the installed LigandMPNN `run.py` in ProteinMPNN mode against
`Sources/iProteinStudio/Resources/examples/acbx/target.pdb` with one batch and
seed 11.

## Limits and what was not tested

- The cardinality proof executes the real Swift command builder, real shell
  parser/check-config and real filesystem auditor, but it does not spend GPU
  compute on a new 259-structure campaign. Entry 0046 separately completed
  1,080/1,080 optimized structures across the resident-engine benchmark.
- The close action and stable presentation ownership compile and have a source
  contract; clicking every route in a packaged GUI remains manual UI acceptance.
- The real cold acceptance covers the mandatory MPNN family. The optional
  multi-gigabyte engines use the same tested transaction/downloader/receipt
  primitives and have existing GPU acceptances, but were not all reinstalled
  from zero in this entry.
- Source checkouts are staged and swapped with recoverable dated backups; Python
  environment activation is the atomic versioned boundary. RFdiffusion3 retains
  its upstream nested environment/install mechanism, guarded by Studio locking,
  pinned source, verified weights and a receipt.
- Retained rollback/source/common-data backups are not deleted automatically.
  They are intentionally outside **Clear safe caches** until a dedicated,
  receipt-aware cleanup/rollback UI exists.

## Next

Package and manually exercise the Engines screen, one non-default iterative
campaign and repeated open/Close/Escape result inspection. Before a public
release, repeat the full optional-engine cold matrix on a second clean Apple-
Silicon account; this is release acceptance, not remaining installer architecture.
