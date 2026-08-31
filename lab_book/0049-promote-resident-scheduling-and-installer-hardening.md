---
entry: 0049
title: Promote resident scheduling and installer hardening
date: 2026-08-31
author: codex-gpt-5
type: integration
status: complete
machine: Apple M4 Max, 40-core GPU, 64 GB unified memory, macOS 26.6.1
tags: [iterative-design, residency, installer, release, validation]
---

## Context

The resident-predictor implementation and the safe installer-hardening slice
were developed in isolated worktrees while the 18-arm performance campaign was
running. The benchmark completed before either branch was promoted, allowing
the scheduler decision and installer Swift code to be tested together in the
canonical iProteinStudio repository.

## What was done

- Promoted Optimized as the default for new iterative campaigns. Boltz 2 (with
  or without steering potentials), IntelliFold v2-flash/full v2, Protenix Mini
  and Protenix Constraint use one campaign-resident worker. Full Protenix v2
  uses cycle-wave, its fastest measured arm. Compatibility mode preserves the
  historical process-per-trajectory path and saved `batched` values still
  decode without migration failure.
- Scoped the resident single-thread environment to IntelliFold. The earlier
  launcher accidentally applied it to every engine; a paired Protenix v2 check
  showed it was a small penalty rather than the cause of v2's sustained-run
  slowdown.
- Integrated the managed-runtime lock, sleep protection, disk preflight,
  durable logs, explicit partial/broken/update states, verified resumable
  downloads, process-tree cancellation and transactional bundled-resource
  replacement.
- Fixed two integration-review edge cases: stubborn installer descendants are
  now killed even when the immediate shell exits before the grace period, and
  resource-swap backups are removed from the destination's actual sibling
  directory.
- Preserved exact pipeline runner provenance after the merge.

## Results

The integrated deterministic suite passed:

| Contract | Result |
|---|---|
| Iterative CLI and Swift command routing | passed |
| Verified downloader (three tests, including interrupted Range resume) | passed |
| Installer lock/state and component reuse/materialisation | passed |
| Compiled SIGTERM-resistant descendant cancellation | passed |
| Application/engine update boundary | passed |
| Ligand conditioning and RFdiffusion3/plain-predict helpers | passed |
| Multichain workflow request, result provenance and workspace organization | passed |
| Full Swift package build | passed |
| Packaged release app and strict code-signature verification | passed |

The performance values supporting scheduler selection remain in Lab Book 0046
and `Validation/lab_book/0001-resident-design-plan.md`; this integration did not
repeat them or introduce a new performance claim.

## Reproduce

```bash
bash Tests/test_iterative_cli_contract.sh
python3 Tests/test_verified_downloader.py
bash Tests/test_installer_hardening_contract.sh
bash Tests/test_installer_component_contract.sh
bash Tests/test_process_runner_cancellation.sh
bash Tests/test_update_release_contract.sh
/Users/thomasfryer/.iproteinstudio/rfd3/.venv/bin/python Tests/test_ligand_conditioning.py
/Users/thomasfryer/.iproteinstudio/rfd3/.venv/bin/python Tests/test_workflow_pipelines.py
swift build
./build_app.sh release
codesign --verify --deep --strict --verbose=2 build/iProteinStudio.app
```

## Limits and what was not tested

- No cold multi-gigabyte installation, live checkpoint interruption, update,
  repair, removal or disk-full failure was deliberately triggered on the
  working managed runtime. Those remain acceptance gates before describing the
  installer as fully transactional.
- The integrated test did not launch a second GPU campaign; scientific speed
  and output audits are the completed frozen campaign in entries 0046 and 0001.
- The resident default is evidenced for fixed 80-aa SUMO protein binders on
  this M4 Max. Ligands, nanobodies, mixed lengths and other Apple chips remain
  outside that performance comparison.
- Exact managed CPython/uv pinning, versioned engine environments, comprehensive
  receipts, checkpoint-level install/removal and Protenix data deduplication
  remain future installer work.
