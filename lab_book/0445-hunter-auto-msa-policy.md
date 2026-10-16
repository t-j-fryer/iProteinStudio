---
entry: 0445
title: Correct Protein Hunter auto MSA policy parsing
date: 2026-10-16
author: Codex
type: bugfix
status: complete
tags: [msa, mcp, rfd3, esmfold2]
---

## Context

The user reported another Mac treating `msa: auto` as a filename during RFdiffusion3 initialization followed by ESMFold2 Full cycling. The other Mac's log and exact version were not provided.

## What was done

Traced MCP guidance, initialization template handoff, the common Protein Hunter shell runner, and the ESMFold2 adapter. Reproduced the runner's actual `extract_target_msa_from_yaml` function in isolation. It excluded empty/none/null but not auto, returning literal `auto`. The caller makes relative paths absolute and fails file validation before reaching the shared target-MSA cache/server resolver. The same omission is present in release tag v0.2.24-beta.

Added auto to that function's non-path policies. Added `Tests/test_hunter_msa_auto.py`, executing the actual shell function with case/quoting variants, other sentinel policies, and real path strings. Explicit paths remain untouched; auto now reaches the existing resolver. No substitution with an empty alignment was introduced.

## Results

Before correction: auto returned `auto`, empty returned no path, target.a3m returned target.a3m. After correction: three regression tests passed, covering ten inputs. No performance measurements or scientific predictions.

## Decision and rationale

This is a Studio parsing defect, not evidence of an agent error: MCP guidance explicitly recommends auto for natural target chains. Keep resolution in the shared orchestrator rather than adding network access or silently dropping alignments inside ESMFold2. The adapter itself expects resolved files or explicit empty mode.

## Reproduce

```bash
python3 -m unittest discover -s Tests -p test_hunter_msa_auto.py
```

## Limits and what was not tested

No remote log inspected; exact remote failure cannot be confirmed. No network MSA generation, complete RFD3/refinement campaign or GPU inference performed. The active benchmark retains frozen code/settings. Initial diagnosis was source-only; release work is recorded below.

## Next

Include the regression in release checks and ship the correction. Inspect the affected job log before choosing a recovery path; use a validated target alignment as a temporary workaround if needed.

## Release validation (0.2.25 / build 71)

User authorized app/MCP/CLI/GitHub/release deployment. Curated clean release branch excludes unrelated manuscript/benchmark work. MCP version43, bridge1.17.1; the shared runner fix serves app and CLI. Added the regression to Tests/run.py.

Swift release build passed. Hunter tests21/21, MSA diagnostics4/4, ESMFold2 adapter8/8, CLI contract, update contract and unsigned-beta contract passed. Initial control-Python Hunter discovery lacked PyYAML; reran with the installed Protenix Python, without installing dependencies. Bridge process/HTTP integration tests require unsandboxed loopback/process access; the properly permissioned rerun passed24/24. Packaging and deployment results follow.
