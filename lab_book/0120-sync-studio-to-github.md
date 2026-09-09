---
entry: 0120
title: Sync accumulated Studio changes to GitHub
date: 2026-09-09
author: Codex
type: implementation
status: in-progress
machine: local Apple Silicon Mac; Command Line Tools selected
tags: [repository, release, tests]
---

## Context

After build 32 and the scaffold checklist work in entry 0119, the user requested
that GitHub be updated. The local main branch and origin/main were both at
`37cc954`; the accumulated implementation, documentation, tests and validation
harnesses had not yet been committed.

## What was done

Fetched origin and reviewed the pending source inventory. No model weights or
release archives are among the pending files. Generated validation outputs,
installed runtimes and `build/` remain ignored. Added the new nanobody catalog
test to the standard fast test runner so GitHub Actions exercises it as well.

The source update includes the prior NISE/NESSO integrations, prediction templates,
engine/scaffold checklists, durable workflow jobs, workspace fixes, validation
scripts and their Lab Book records. Existing local app/DMG artifacts are retained;
this source synchronization does not publish a release or update the appcast.

## Results

No measurements — repository synchronization only. Debug and release Swift builds
and scaffold/batch contract checks passed in entry 0119. The current fast suite's
Python and shell checks passed. `swift test` cannot compile XCTest on this host:
`no such module 'XCTest'`. Only Command Line Tools are installed; no full Xcode
application is present. The separate executable Swift contracts remain available.
The final suite summary and GitHub synchronization results will be recorded below.

The staged whitespace check identifies existing blank-line/trailing-space issues
in newly tracked historical files, including required blank context-line markers
inside the NESSO patch. These files were retained intact rather than rewriting
validated historical sources during publication. No staged weights, build archives
or generated campaign outputs were found. A credential-pattern scan's sole match
was an amino-acid sequence in an already tracked MSA, not a credential.

## Decision and rationale

Commit the complete coherent source tree rather than only the most recent scaffold
diff: the new controls depend on other pending model and durable-job changes.
Use an ordinary push to main, preserving remote history. Keep generated data and
local unsigned-beta binaries separate from source control.

## Reproduce

```bash
git fetch origin
git diff --check
python3 Tests/run.py
git push origin main
git ls-remote origin refs/heads/main
```

## Limits and what was not tested

No new model inference, GUI acceptance, release publication or second-Mac install.
The existing design job is not stopped or modified. This machine selects Command
Line Tools rather than a full Xcode installation, which may prevent XCTest from
running; any such failure must remain explicit.

## Next

Finish tests, commit the reviewed source files, push and verify the remote commit.
