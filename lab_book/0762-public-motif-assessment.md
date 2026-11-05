---
entry: 0762
title: Publish partner-aware motif assessment
date: 2026-11-04
author: Codex
type: audit
status: complete
machine: Apple M4 Max, 40-core GPU, 64 GB unified memory
---

## Context

The user explicitly requested the validated motif extension in the public release.
Promote only its app/CLI/MCP, tests and documentation changes. Private research,
experimental peptide controls, raw jobs and model weights are excluded.

## What was done

Version0.2.34/build83/MCP55 adds selected source-complex protein and noncovalent
ligand partners during native motif generation, final untemplated apo/holo
prediction and source-motif shape/partner-relative RMSD hit gates. Sequence-only
inputs first predict the complete motif/partner complex to establish a reference.
All requested modes and cutoffs must pass. Native atom correspondence is retained.
Geometry uses the pinned RFD4 CPU environment; predictor environments are unchanged.
Protenix session MSA policies are kept distinct between apo and aligned holo inputs.

The public worktree applies the reviewed feature delta, preserving public-only
restrictions. One metric-formatting hunk was adapted to the public result model.
All28 relevant scientific workflow files and ten shared predictor/geometry
adapters match the qualified implementation byte for byte. No extra GPU run was
needed for promotion; active production jobs retain their immutable snapshots.

## Results

The existing GPU acceptance generated two native families (60steps/180recycles,
optimized kernels) and four independent predictions using a synthetic T4 lysozyme,
T4 fragment and lactate fixture. This is a wiring fixture, not a known complex.

| Partner / predictor | Apo shape RMSD | Holo shape RMSD | Holo partner-aligned motif RMSD |
| --- | ---: | ---: | ---: |
| Protein / ESMFold2 Full | 2.314 Å | 3.809 Å | 37.082 Å |
| Lactate / Boltz-2 | 2.852 Å | 2.466 Å | 47.636 Å |

Both correctly failed the2 Å gates. These are technical metric/classification
checks, not evidence for binding, stability or biological activity. Re-starting a
completed plan reused the same job and68unchanged files without inference.
Public Swift build, configuration/result harnesses, six focused geometry/receipt
checks,24MCP checks, workflow regressions and release/update contracts passed.
Sanitized measurements, checksums and boundaries are recorded in
`artifacts/0762-public-motif-assessment/qualification.json`.

An earlier qualification attempt completed native generation but failed before
ESMFold2 prediction because Gemmi was absent from that predictor runtime. The
CPU geometry bridge fixed that boundary without changing installed packages.
Final successful outputs and failed attempts remain immutable in the validation
record; publication includes only the sanitized evidence.

## Decision and rationale

Use the existing public trusted-beta channel and its signed Sparkle archive.
No new runtime, weights, kernel defaults or performance claims are introduced.
The app remains ad-hoc signed, not Developer ID signed or Apple notarized.

## Reproduce

Run the tests from this release checkout:

```bash
swift build
STUDIO_SWIFT_CASES=rfd4_configuration,results python3 Tests/run_swift_contracts.py
NANOHUNTER_ROOT="$HOME/.iproteinstudio" "$HOME/.iproteinstudio/venvs/NanoHunter_rfd4/bin/python" -B -m unittest discover -s Tests -p test_rfd4_motif_assessment.py -k Contracts
bash Tests/test_mcp_bridge.sh
bash Tests/test_update_release_contract.sh
bash Tests/test_unsigned_beta_release_contract.sh
bash release/release_app.sh --unsigned-beta
```

## Limits and what was not tested

No new GPU runs during promotion; no second-Mac upgrade, other-Mac validation,
long campaign, fresh source-complex sequence prediction, other predictor GPU
qualification or combined protein-plus-ligand GPU example. Covalent partners and
metal motifs are outside this guided route. Package and publication verification
will be recorded with the final delivery.


## Delivery

Published `v0.2.34-beta` from clean packaging commit
`1a069bb6acabf3d66564e27cee121250d71c07a6`. The public DMG and ZIP sizes and
SHA256 digests match the local verified artifacts. The downloaded public ZIP also
passes independent Ed25519 verification. All28 scientific workflow files in the
app match the qualified source; MCP55 and build83 are present. No model weights
are packaged. The prior distribution app uses the same update URL and public key.
The generated signed build83 feed is published on main with this delivery record.

The existing open app was not forcibly relaunched; a live old-to-new installation
was not tested in this promotion. Users receive the release through Check for
Updates or the public DMG. Existing managed CLI/MCP staging follows the normal
execution-lease boundary, preserving active jobs' frozen code and runtimes.
No production GPU jobs were paused or changed during public promotion.
