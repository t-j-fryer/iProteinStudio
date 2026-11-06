---
entry: 0786
title: Publish ligand geometry filters and molecule views
date: 2026-11-06
author: Codex
type: audit
status: in-progress
machine: Apple Silicon development Mac; CPU and native UI qualification
tags: [release, ligand, ui, mcp, cli]
---

## Context

The user explicitly requested delivery of Labs0784–0785 to beta, the public
repository, app releases, MCP and CLI. Initial delivery0.2.35/build85 carries MCP56; final upgrade correction is
0.2.36/build86 with the same MCP56 contract.

## What was done

Review the complete public feature delta from0.2.34. Preserve public result-model
restrictions and omit private experiments, model weights and raw research outputs.
The matching changed source files are byte-identical to beta; three result
files retain their existing public/private scope differences. The three Figure4
classifier hashes match the prior qualification. No runtime or weights changed.

Release through the existing trusted-beta channel: ad-hoc application signature
and Sparkle Ed25519 archive signature, without Developer ID signing or Apple
notarization. The release script packages the clean public worktree. Publication uses an explicit public URL; the canonical checkout keeps its
disabled public push URL. The combined release script first stopped at that
intentional push block after successful packaging; publication resumed using
the exact verified artifacts and tag, without rebuilding or changing assets.

## Results

Public Swift build and request/result contract executables passed. All24 MCP
regressions passed with normal macOS system-reading access; the first sandboxed
attempt was blocked from reading installed memory. Four public CPU geometry
tests passed; one private-coordinate replay was explicitly skipped. CLI doctor
loads MCP56 and all ten schemas; shell help exposes the optional geometry flag.
Update/release and unsigned-beta packaging contracts pass. Native build85 drag
and reset checks are recorded in Lab0785. Prior broader qualification remains
in Lab0784. No performance measurements or new neural inference.

The public feature delta reviewed before release metadata contains72files,
55under Sources. No weights, private research or added machine-specific source
paths. Sanitized source and qualification evidence is in
`artifacts/0786-public-ligand-release/qualification.json`.

## Decision and rationale

Ship the same validated optional geometry policy across app/CLI/MCP, and the
viewer changes through the shared app components. Reuse the established release
channel and update key. Existing accepted jobs keep their immutable snapshots.

## Reproduce

```bash
swift build --disable-sandbox
STUDIO_SWIFT_CASES=rfd4_configuration,nise,workflow_requests,iterative,results python3 Tests/run_swift_contracts.py
bash Tests/test_mcp_bridge.sh
"$HOME/.iproteinstudio/venvs/NanoHunter_boltz/bin/python" -B -m unittest discover -s Tests -p test_ligand_geometry.py -v
python3 Sources/iProteinStudio/Resources/pipeline/mcp/studioctl.py doctor
bash Tests/test_update_release_contract.sh
bash Tests/test_unsigned_beta_release_contract.sh
bash release/release_app.sh --publish-unsigned-beta
```

## Limits and what was not tested

No fresh GPU design campaign, binding assay, second-Mac upgrade, macOS14 hardware
check or performance benchmark. Public tests omit the private paper-coordinate
fixtures. Generic geometry uses selected contact/SASA; the paper exit preset is
restricted to free biotin. No new chemistry or continuous exit-volume method.

## Upgrade correction

Published0.2.35/build85 and independently verified downloaded assets, Ed25519
signature,29packaged resources and live update feed. After the user approved the
public app restart, installed the downloaded app and reopened it. Local CLI
reported MCP56, but the full staging audit found the RFD3 campaign wrapper still
old: its OVERLAY_VERSION had not changed with the wrapper. No active jobs.

Regenerated the sorted Python-content checksum and overlay update marker in both
beta/public. Added a release-contract check that validates source and packaged
overlay receipts against actual Python contents. That check rejects build85's
stale receipt. Publish the correction as0.2.36/build86; leave published0.2.35
archives immutable. Portable engine inventories, runtime code and weights remain
unchanged; the staged campaign wrapper is the Studio orchestration layer.

## Delivery

Initial0.2.35 release verification is retained in delivery-0.2.35.json.
Final0.2.36 packaging/publication and managed-staging verification are in progress.
