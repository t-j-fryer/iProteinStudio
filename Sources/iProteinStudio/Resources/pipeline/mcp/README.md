# iProteinStudio MCP bridge

This client-neutral bridge exposes the existing iProteinStudio command-line
workflows to Codex, Claude Code, and other Model Context Protocol clients. It is
an orchestration layer only: prediction, iterative design, RFdiffusion3, MPNN,
MSA and analysis behaviour remains in the same scripts used by the GUI.

## Profiles

- `read`: engine detection, projects, run status and bounded result queries.
- `run`: immutable preflight plans, content-addressed imports, scientific jobs,
  cancellation and resume.
- `admin`: engine install/repair and checksum-constrained storage maintenance.
  It is not configured by default.

Each client starts its own local stdio process. Durable worker processes and the
shared `~/.iproteinstudio/agent/execution.lock` serialize environment changes
and Apple-GPU campaigns across every MCP or `studioctl.py` client. Closing a
client does not terminate the job. The GUI currently remains on its validated
direct launch path, so do not overlap GUI and agent campaigns.

## Configure clients

From the staged installation:

```bash
/usr/bin/python3 "$NANOHUNTER_ROOT/mcp/configure.py" \
  --client both --scope project --project-root /path/to/a/trusted/project
```

This is a dry run. Add `--write` after reviewing it. The command writes only a
marked iProteinStudio section to Codex TOML and merges only
`iproteinstudio-*` entries in Claude's `.mcp.json`.

The normal profiles are `read,run`. Installing `admin` additionally requires an
explicit `IPROTEINSTUDIO_ENABLE_ADMIN_MCP=1` environment variable.

Verify the staged bridge without starting a model:

```bash
/usr/bin/python3 "$NANOHUNTER_ROOT/mcp/studioctl.py" doctor
```

## Direct protocol smoke test

```bash
printf '%s\n' \
  '{"jsonrpc":"2.0","id":1,"method":"initialize","params":{"protocolVersion":"2025-06-18","capabilities":{},"clientInfo":{"name":"smoke","version":"1"}}}' \
  '{"jsonrpc":"2.0","method":"notifications/initialized"}' \
  '{"jsonrpc":"2.0","id":2,"method":"tools/list","params":{}}' \
  | /usr/bin/python3 "$NANOHUNTER_ROOT/mcp/server.py" --profile read
```

## Safety contract

- There is no shell, Python, arbitrary executable, arbitrary environment or raw
  RFD3 YAML tool.
- Scientific and administration plans are separate profiles.
- `job_start` requires the plan ID and SHA-256 digest and rechecks the installed
  scripts before execution.
- Missing engines, scripts, alignments and artifacts fail rather than selecting
  a weaker route.
- Files outside managed storage are copied into immutable content-addressed
  storage only from configured import roots.
- `PYTORCH_ENABLE_MPS_FALLBACK=0` is enforced for worker processes.
- Every tool call is recorded under `agent/audit/` without copying full
  sequences, structures or arguments into the audit record.
