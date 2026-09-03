---
entry: 0071
title: Make agent RFdiffusion3 guidance fail-safe
date: 2026-09-02
author: gpt-5.6-sol
type: bugfix
status: complete
machine: Apple M4 Max, 40-core GPU, 64 GB unified memory, macOS 26.6.1
tags: [mcp, agents, claude, rfd3, mlx, diagnostics, usability]
---

## Context

A first real Claude-driven MCP trial exposed several failures that unit-level
tool availability had not tested. Claude correctly detected engines and listed
projects, but then chose LASErMPNN for a soluble protein target, described
coarse exposed-residue candidates as a coherent epitope, proposed ranking before
independent prediction, skipped a small end-to-end smoke campaign, and authored
an RFdiffusion1-style contig. When the campaign failed, the MCP job response was
nearly blank, so Claude guessed about potentials, stale directories and ligand
fields before asking the user for manual filesystem access.

The real terminal error was already present in `logs/fixtures.log`:

```text
cannot count fixed motif residues in contig segment: 'B1-236/0 45-75'
```

The pinned Apple-Silicon adapter expects binder-first comma-delimited syntax,
for example `65-65,/0,B1-236`. This follows
[[0069-add-client-neutral-agent-bridge]] and
[[0070-add-one-click-ai-and-private-remote-gateway]].

## What was done

- Added a client-neutral `workflow_guide` MCP tool. It describes the workflow
  order, model routing, prediction-before-ranking rule, filter defaults,
  1–5-backbone smoke policy, partial-diffusion semantics and motif constraints.
  It lives in the server rather than only in one client's repository skill.
- Added concise MCP server `instructions`, richer tool descriptions and
  normalized-plan `operator_guidance`. Codex, Claude Code and desktop/remote MCP
  clients therefore receive the core rules even if they do not load repository
  files.
- Made SolubleMPNN, Boltz verification, binder-only prediction and the GUI's
  protein-binder hit filters the protein de-novo defaults. LASErMPNN and
  LigandMPNN now produce an explanatory protein/small-molecule routing error.
- Kept `contig` recognizable only to produce a direct migration error. The MCP
  planner rejects every agent-supplied protein de-novo contig; campaign
  preparation derives the exact binder-first form from the chosen lengths and
  normalized target-chain ranges. This avoids both invalid syntax and a valid
  looking value silently disagreeing with the imported target.
- Removed irrelevant ligand defaults from normalized protein requests.
- Corrected durable job observability. `job_status` now exposes the child
  `pipeline.log`, keeps worker output separately, preserves a specific failure
  instead of replacing it with a generic exit status, and returns the captured
  error tail. `run_status` returns the newest RFdiffusion3 stage logs.
- Updated `AGENTS.md`, `CLAUDE.md`, Claude's `iprotein-run` skill, the versioned
  RFD3 schema, MCP/CLI documentation and integration tests.

## Results

no performance measurements — implementation and correctness validation only

| Condition | n | Metric | Value |
|---|---:|---|---:|
| MCP bridge integration suite | 12 tests | passed | 12/12 |
| Workflow pipeline contracts | 1 suite | result | passed |
| AI integration UI contract | 1 suite | result | passed |
| Content-addressed pipeline snapshot contract | 1 suite | result | passed |
| Swift debug build | 1 build | result | passed |
| Installed MLX RFD3, mNeonGreen target, 65-residue binder | 1 uncached fixture | former contig failure | passed |

The fixture check exercised the installed Apple-Silicon adapter and built its
oracle fixture successfully. Its elapsed time is not treated as a benchmark.

## Decision and rationale

Put compact universal rules in MCP `instructions`, detailed workflow-specific
rules in a callable MCP tool, and client-specific detail in repository
instructions/skills. A Claude-only skill was rejected as the sole solution
because Claude Desktop, Codex, ChatGPT and other MCP clients do not necessarily
load it. Tool descriptions alone were also insufficient: they are discovered
piecemeal and do not reliably communicate a multi-tool scientific workflow.

Derive protein de-novo contigs rather than accepting expert overrides through
MCP. This is an adapter implementation detail already known from inspected
chains and binder lengths; exposing it created failure modes without adding
scientific choice. Merely validating the syntax was rejected because campaign
preparation would then ignore an apparently valid client override, violating
the no-silent-divergence requirement.

Do not automatically turn coarse exposure labels into hotspots. They are useful
candidates for human review, but neither spatial coherence nor biological
epitope suitability is established by the current inspector.

## Reproduce

```bash
cd /Users/thomasfryer/iProteinStudio
/usr/bin/python3 Tests/test_mcp_bridge.py
"$HOME/.iproteinstudio/rfd3/.venv/bin/python3" Tests/test_workflow_pipelines.py
bash Tests/test_mcp_bridge.sh
bash Tests/test_ai_integrations_ui_contract.sh
bash Tests/test_pipeline_snapshot.sh
swift build

# Adapter-boundary regression used the failed campaign's normalized target and:
"$HOME/.iproteinstudio/rfd3/.venv/bin/python3" \
  "$HOME/.iproteinstudio/rfd3/scripts/design_from_yaml.py" \
  /tmp/iproteinstudio-mcp-rfd3-regression/design.yaml \
  --name mcp_contig_regression \
  --output /tmp/iproteinstudio-mcp-rfd3-regression/campaign-uncached \
  --num-designs 1 --lengths 65 --batch-size 1 --queues-per-bin 1 \
  --precision bf16 --timesteps 200 --n-recycle 2 --seed-base 0 \
  --stage fixtures
```

## Limits and what was not tested

- No RFdiffusion3 backbone sampling, SolubleMPNN sequence design, target MSA,
  Boltz complex prediction or binder-only prediction was launched in this
  entry. The test stops after the formerly failing fixture boundary.
- Claude was not rerun after staging the repair, so improved agent adherence is
  not yet an observed result.
- The workflow guide cannot establish a biological epitope automatically. The
  target inspector's exposure candidates remain deliberately labeled coarse.
- Default protein hit filters are editable starting gates, not experimentally
  calibrated guarantees for mNeonGreen or every binder topology.
- No phone/remote gateway or administrative MCP operation was exercised.

## Next

Stage the updated bridge, open a fresh Claude or Codex chat, call
`workflow_guide` for `rfd3_protein_binder`, and run a one-backbone end-to-end
mNeonGreen smoke campaign. Compare the agent's choices and its failure handling
against this transcript before allowing the 500-backbone campaign.
