---
entry: 0058
title: Close the remaining clean-Mac installer failures
date: 2026-09-01
author: codex-gpt-5
type: bugfix
status: complete
machine: Apple M4 Max, macOS
tags: [installer, protenix, lasermpnn, rfd3, mpnn, receipts, ui]
---

# Close the remaining clean-Mac installer failures

## Context

Six logs from the first external standalone installation showed that successful
downloads and scientific health checks were being followed by unrelated setup
failures. They also exposed a product-language problem: users could select
ProteinMPNN, SolubleMPNN and LigandMPNN in workflows without seeing those tools
as separately installable Engines entries.

## What the logs established

The attempts were cumulative rather than six failures of one component:

1. Boltz installed, then the old AntiFold lock failed on unpinned `packaging`.
   Entry [[0057-repair-antifold-hash-lock]] fixes and validates that defect.
2. IntelliFold v2 Flash installed, then Protenix stopped with
   `model_dir: unbound variable` after the Protenix package itself built.
3. A Protenix-only retry reproduced the same nounset failure.
4. LASErMPNN stopped because its bootstrap expected two hashes that do not
   belong to the published `filelock==3.32.3` artifacts.
5. RFdiffusion3 downloaded and converted its checkpoint, passed MLX Metal,
   PyTorch MPS, CCD and both weight-checksum checks, then failed only while
   writing a receipt because its intentionally lean uv environment has no
   `pip` module.
6. A later Protenix retry again reproduced the same nounset failure.

Every log that reached the core sequence-design stage reported:

```text
NHSTATE|mpnn|ok|ProteinMPNN / SolubleMPNN / LigandMPNN / AbMPNN
```

The MPNN family was therefore installed correctly. Studio deliberately treats
it as one unconditional core component rather than four optional engines.

## Fixes

### Protenix

Two functions declared `model_dir` and expanded `${model_dir}` in the same
`local` command. Under `set -u`, Bash expands the right-hand expressions before
the new local has a value. Both helpers now declare their locals first and
derive `source` or `common` on the following line.

### LASErMPNN

PyPI's official release metadata for `filelock==3.32.3` reports:

- wheel SHA-256: `7f0ca4bcc0e181c60dbbd8aa9ab5b120ebb99e4e064e83636340056f833a1f09`
- source SHA-256: `0ffa185a3540854c95caa7fa76b76cb219d907415e2c5dc9af25fd970563487f`

The bootstrap lock now contains those two values. The wheel value also agrees
with all other curated Studio locks that use this release.

### RFdiffusion3 receipts

Component receipts formerly depended on `python -m pip freeze`. That was an
invalid assumption for a uv-managed environment that deliberately omits pip.
Receipt creation now uses pip freeze when available for compatibility with
existing receipts, otherwise inventories non-editable distributions through
Python's standard `importlib.metadata`. The selected method is stored and reused
during verification, so the digest remains deterministic.

Detection distinguishes the log's exact partial state: valid RFD3 weights and
environment without `receipts/rfd3.json` are reported as **update available**,
with the engine described as usable. This lets the user select it once to finish
provenance without implying that its already-validated checkpoint is broken.

### MPNN presentation

The Engines screen now contains a permanent **Core sequence designers** row that
lists ProteinMPNN, SolubleMPNN, LigandMPNN and AbMPNN, reports their shared
installation state, explains why they are automatic and offers **Install core…**
if the suite is missing or incomplete. It remains non-removable. Download review
also includes it whenever repair is required.

## Verification

| Check | Result |
|---|---|
| Protenix helper execution under `bash -eu` | Both exact shared-data functions passed |
| LASErMPNN clean bootstrap install | 13 locked packages installed; filelock 3.32.3, NumPy 1.26.4 and PyTorch 2.2.1 imported |
| Receipt unit contract | Passed, including synthetic pip-less environment |
| Real installed RFdiffusion3 receipt | 118 packages inventoried and re-verified via `importlib.metadata` |
| All nine hash-lock structure contracts | Passed |
| Installer hardening contract | Passed |
| Receipt-less usable RFD3 detection | Reported as repairable `update` |
| Shell/Python syntax and `git diff --check` | Passed |
| `swift build` | Passed |
| Build 5 DMG/ZIP checksum manifests | Passed |
| Mounted build 5 resource/signature contract | Passed |
| Bundled receipt helper against real pip-less RFD3 | Passed |
| Read-only DMG launch outside checkout | Remained running for 5 s |

No performance measurements were made; this was installer correctness work.

Build 5 private-test artifacts:

- DMG SHA-256: `b0aa07f4f70353c7fcbda359ff5cbede532885da9771d9ab411f60baa056cc91`
- ZIP SHA-256: `be4561ddc6594cbdcfe9b0b52228a11b9df1ccc791284c87d5f882746b9a9451`

The DMG was mounted read-only and reported bundle build number 5. Its bundled
resources contained the corrected LASErMPNN hashes, split Protenix local
initialization, pip-less receipt inventory and the earlier AntiFold correction.

## Decision and rationale

- MPNN remains a mandatory shared core because every sequence-design workflow
  needs one of its closely related variants and its footprint is small relative
  to the optional structure engines. The UI now says this directly instead of
  presenting selectable tools whose installation origin is invisible.
- RFdiffusion3 remains pip-less. Installing pip only to create a receipt would
  enlarge and mutate a runtime that had already passed its scientific checks;
  standard-library package metadata provides the needed provenance directly.
- Hash enforcement remains mandatory. The LASErMPNN mismatch was corrected
  against publisher metadata rather than bypassed.

## Limits and what was not tested

- A complete Protenix checkpoint download and prediction were not repeated;
  the exact failing helpers were executed under nounset, and prior validated
  Protenix GPU results remain unchanged.
- The full compiled PyG extension phase and a LASErMPNN inference were not
  repeated. The failed bootstrap stage was installed cleanly and imported.
- RFdiffusion3 generation was not rerun because the external log already showed
  every scientific installation check passing before the receipt-only failure.
- The corrected build still needs one complete retry on the external Mac.
- The new core-suite Engines row compiled and the packaged app launched, but its
  layout has not yet been visually inspected on the external Mac.

## Next

Retry the incomplete components on the external Mac with private-test build 5.
Completed checkpoints and resumable downloads should be reused.
