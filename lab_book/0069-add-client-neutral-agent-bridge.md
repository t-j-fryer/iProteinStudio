---
entry: 0069
title: Add a client-neutral agent bridge
date: 2026-09-02
author: gpt-5-codex
type: implementation
status: complete
machine: Apple M4 Max, 40-core GPU, 64 GB unified memory, macOS 26.6.1
tags: [mcp, agents, codex, claude, reproducibility, security]
---

## Context

iProteinStudio's underlying workflows were scriptable, but an AI agent had to
discover changing script arguments and could bypass the GUI's scientific
constraints. Codex and Claude Code both support local Model Context Protocol
(MCP) servers, but a single broad shell tool would have made the bridge less
reproducible and more privileged than the application. Entries
[[0053-make-resident-scheduling-automatic]],
[[0066-add-rfd3-partial-motif-and-dual-validation]] and
[[0068-reuse-resident-predictors-for-rfd3-validation]] define behaviour that the
agent route must preserve rather than reimplement.

## What was done

- Added a dependency-free local stdio MCP implementation under the packaged
  `pipeline/mcp/` resources. The same server is divided into `read`, `run` and
  opt-in `admin` profiles; the normal client configuration receives only the
  first two.
- Added strict, versioned JSON request schemas for prediction, target
  preparation, iterative design, the three RFdiffusion3 modes and job start.
  Unknown fields fail before a plan is written.
- Added typed discovery, target inspection, immutable artifact import,
  immutable preflight plans, durable start/status/wait/cancel/resume jobs and
  bounded result queries. There is no arbitrary shell, Python, executable,
  environment, deletion or raw RFD3-YAML tool.
- Plans record a canonical SHA-256 digest, normalized request, command preview,
  imported input hashes and runner hashes. Start and resume recheck both the
  plan and runner provenance. Long jobs detach from the MCP process, checkpoint
  under `agent/jobs/`, enforce no MPS CPU fallback and serialize through one
  advisory `execution.lock` shared by Codex, Claude and `studioctl.py`.
- Routed model work to the existing production scripts. Iterative plans inject
  the measured resident/cycle-wave policy and durable pipeline snapshot;
  RFdiffusion3 remains split into de-novo, partial-diffusion and motif modes and
  delegates preparation, validation and resident verification to the existing
  runners.
- Added content-addressed imports restricted to managed storage, standard user
  document folders or explicitly configured roots. Audit rows store argument
  digests rather than raw sequences or structures.
- Added non-destructive Codex TOML and Claude `.mcp.json` configuration writers,
  a JSON `studioctl.py` controller and an offline `doctor` command. Configuration
  is a dry run unless `--write` is explicit, and enabling `admin` also requires
  `IPROTEINSTUDIO_ENABLE_ADMIN_MCP=1`.
- Updated agent instructions, Claude's run skill, CLI documentation and the
  signed-app resource contract. Added integration coverage for protocol
  negotiation/resources, privilege separation, schema errors, runner changes,
  concurrent jobs, cancellation, resume, result distributions, imports and
  preservation of unrelated client configuration.

## Results

no measurements — implementation only

| Condition | n | Metric | Value |
|---|---:|---|---:|
| MCP bridge integration suite | 9 tests | passed | 9/9 |
| Related CLI/UI/snapshot/installer contracts | 7 scripts | passed | 7/7 |
| Swift debug build | 1 build | result | passed |
| Ad-hoc release app resource contract | 1 bundle | result | passed |

The installed-engine detection path also returned successfully for the current
managed installation. This is an availability check, not a model correctness or
performance measurement.

## Decision and rationale

Use one client-neutral implementation with three least-privilege profiles. This
keeps Codex and Claude on identical scientific semantics while allowing a user
to omit all mutating tools or opt into administration separately. A single
omnipotent server and an arbitrary command wrapper were rejected because tool
descriptions are not a security boundary and cannot make an unvalidated command
reproducible.

Use immutable plan/start as a two-step contract. An agent can inspect exactly
what Studio normalized before expensive work begins; a changed runner invalidates
the plan instead of silently changing the experiment.

Use detached per-job workers plus a shared file lock rather than a permanent
launchd daemon. This provides disconnect survival and cross-client serialization
without adding an install-time service, socket authentication or another daemon
lifecycle. The existing GUI is deliberately not migrated behind this broker:
doing that could change its validated interactive launch and cancellation
semantics. The documented rule is therefore not to overlap GUI and agent jobs.

Keep the bridge local stdio only. A remote HTTP server would require an explicit
authentication, host authorization, transport and deployment threat model that
is unnecessary for agents on the same Mac.

## Reproduce

```bash
cd /Users/thomasfryer/iProteinStudio
/usr/bin/python3 Tests/test_mcp_bridge.py
bash Tests/test_iterative_cli_contract.sh
bash Tests/test_pipeline_snapshot.sh
bash Tests/test_rfd3_results_ui_contract.sh
bash Tests/test_iterative_results_ui_contract.sh
bash Tests/test_workspace_organization.sh
bash Tests/test_installer_hardening_contract.sh
bash Tests/test_installer_component_contract.sh
swift build
./build_app.sh release
bash Tests/test_packaged_resource_bundle.sh

# After installing/staging the app resources:
/usr/bin/python3 "$NANOHUNTER_ROOT/mcp/studioctl.py" doctor
/usr/bin/python3 "$NANOHUNTER_ROOT/mcp/configure.py" \
  --client both --scope project --project-root /path/to/trusted/project
```

## Limits and what was not tested

- No real Boltz, IntelliFold, Protenix, OpenFold, MPNN or RFdiffusion3 model was
  launched through MCP in this entry. Existing model and workflow tests cover
  those runners; the new integration suite uses deterministic fake workers.
- Codex parsed and listed the generated configuration in an isolated temporary
  home. Claude Code was not installed on this machine, so its JSON was parsed
  and merge-tested but not loaded by the real Claude CLI.
- Agent jobs serialize against other agent jobs, not against GUI jobs. Running
  both concurrently is unsupported until the GUI is deliberately migrated and
  revalidated.
- No remote transport, multi-user host, Windows/Linux client, M1 execution,
  notarised application or DMG was tested. The built app is ad-hoc signed.
- The JSON-schema validator implements the subset used by the shipped schemas;
  adding new schema keywords requires a corresponding validator test.
- Administration plans were privilege-tested with fake setup scripts; no engine
  was installed, repaired, removed or storage-minimized in this entry.

## Next

Load the project configuration in a real Claude Code installation and run one
small prediction and one resumable RFdiffusion3 campaign through each client.
Consider migrating the GUI to the broker only after a separate lifecycle and
performance study proves parity with its current launch path.
