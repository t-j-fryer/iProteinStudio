# iProteinStudio MCP bridge

This client-neutral bridge exposes the existing iProteinStudio command-line
workflows to Codex, Claude Code, and other Model Context Protocol clients. It is
an orchestration layer only: prediction, iterative design, RFdiffusion3, MPNN,
MSA and analysis behaviour remains in the same scripts used by the GUI.

## Profiles

- `read`: engine detection, projects, run status and bounded result queries.
- `run`: all read capabilities plus immutable preflight plans,
  content-addressed imports, scientific jobs, cancellation and resume. A single
  run-profile conversation can therefore inspect its outputs without changing
  servers.
- `admin`: engine install/repair and checksum-constrained storage maintenance.
  It is not configured by default.

Each client starts its own local stdio process. Durable worker processes and the
shared `~/.iproteinstudio/agent/execution.lock` serialize environment changes
and Apple-GPU campaigns across every MCP or `studioctl.py` client. Closing a
client does not terminate the job. The GUI currently remains on its validated
direct launch path, so do not overlap GUI and agent campaigns.

## Configure clients

Normal users do this from **iProteinStudio → AI** or **Settings → AI
assistants**. The app presents the access level and adds/removes only Studio's
entries for Codex or Claude Desktop. No terminal is required.

The commands below are retained for automation and diagnosis.

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

`--client codex --scope user` configures clients that share Codex's user
configuration. `--client claude-desktop --scope user` safely merges Claude
Desktop's JSON. The historical `claude` name means Claude Code; it remains
available separately because Claude Code and Claude Desktop do not use the same
registration route.

Verify the staged bridge without starting a model:

```bash
/usr/bin/python3 "$NANOHUNTER_ROOT/mcp/studioctl.py" doctor
```

## Agent operating contract

Call `workflow_guide` before creating a scientific plan. Its guidance is served
through MCP itself, so clients that do not load repository instruction files
still receive Studio's workflow order and defaults. In particular:

- use SolubleMPNN by default for soluble protein binders; LASErMPNN and
  LigandMPNN are small-molecule-interface models;
- secondary-structure control is initialization-only `--negative-helix-constant 0..1`;
  zero disables it and subsequent MPNN cycles use normal sampling. Retired beta,
  mixed, sustained, inspection, loop-kill and global composition-bias flags fail
  preflight. Historical results remain readable.
- `monomer_control_benchmark: true` validates an unconditioned monomer with empty
  MSA and pins the recorded run scheduler across arms.

- omit a protein de-novo `contig` and let Studio derive the pinned adapter's
  canonical binder-first grammar;
- use `binding_site_mode: surface_scan` when no epitope is known. It creates
  several solvent-accessible outward ORIs and divides the exact design quota
  among them. `surface_patch` uses broad region residues only for placement;
  `targeted_epitope` is the only common mode that emits hotspot conditioning;
  `manual` accepts expert XYZ coordinates. Never use protein target COM as the
  no-hotspot fallback;
- complete a 1–5-backbone end-to-end smoke run before a large campaign;
- independently predict every candidate before ranking; and
- diagnose failures from `message`, `error`, `pipeline_log_tail`,
  `worker_log_tail`, and the stage logs returned by `run_status` rather than
  requesting arbitrary filesystem access.

Call `results_overview` before reading individual score tables. It exposes the
same scientific organization as the app:

- iterative design: run → ordered cycle → design structure, independently
  repredicted complex and binder-alone fold. Its `trajectory.frames` contains
  only design-stage cycles; the app rigidly aligns them to cycle 00 using
  matching target-chain Cα atoms on chains B onward;
- RFdiffusion3: generated MLX backbone → MPNN sequence derivative → complex
  and binder-alone validation. A generated backbone is not itself a validated
  hit, and one derivative's verdict does not silently promote its siblings.

Then use `results_query` for a named raw table or numeric distribution. New
campaigns persist `predictor` and `prediction_context`; for older Studio
campaigns, the bridge adds bounded labels from Studio-owned dataset and
predictor paths without modifying the run on disk. Artifact paths returned by
the overview are verified run-relative paths, including relocated/self-contained
campaign folders; raw obsolete absolute paths are not exposed.

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

## ChatGPT and a phone

`remote_gateway.py` provides the local half of an opt-in remote connection. It
uses the same MCP implementation and durable job broker, permits only `read` or
`run`, binds to loopback, requires a random mode-0600 capability credential and
keeps the Mac awake only while enabled. The secret is accepted as a bearer token
or as the unguessable endpoint path for clients that support no-auth custom MCP
URLs.

Every start rotates the capability URL. A previously shared read-only URL can
therefore never acquire `run` privileges after the gateway is restarted with a
different profile.

The gateway deliberately does **not** publish itself. ChatGPT executes remote
tools from OpenAI infrastructure, so a trusted HTTPS tunnel or hosted relay must
forward to the loopback port. The full secret URL can appear in proxy logs and
must be treated like a password. Stop or rotate the gateway to revoke it. Never
forward the bare local port, and never expose the `admin` profile remotely.

For diagnosis:

```bash
/usr/bin/python3 "$NANOHUNTER_ROOT/mcp/remote_gateway.py" status
/usr/bin/python3 "$NANOHUNTER_ROOT/mcp/remote_gateway.py" start --profile read
/usr/bin/python3 "$NANOHUNTER_ROOT/mcp/remote_gateway.py" stop
/usr/bin/python3 "$NANOHUNTER_ROOT/mcp/remote_gateway.py" rotate-token
```


MCP v9 adds `workflow_guide(workflow="nise")` and the run-profile `nise_plan`
tool (`nise-v1.json`). Native and MCP submissions use the same ligand NISE
contract, campaign-owned code snapshot and durable broker. Results preserve
trajectory/candidate/holo/apo parentage. Protein Hunter keeps the historical
`iterative` workflow identity. Cross-cycle structure/affinity residency remains
experimental for ligand throughput; no alternative model or missing-affinity
fallback is allowed.


MCP v10 extends `nise-v1.json` compatibly with separate Phase-0 funnel budgets,
`beam` (parents advanced per trajectory), and optional `nesso_screen` /
`nesso_top_k`. The shortlist is per trajectory across its sampled parents;
NESSO never generates initial backbones or replaces the Boltz search score.
Missing new fields retain v9 behavior. Plans fingerprint the optional installed
NESSO assets, code and screening protocol; resume reuses the saved scores and
shortlist. Read `docs/NISE.md` for the stage diagram and budget examples.

Iterative cycle overviews include `geometry_diagnostics` when available: a
verified report path, `record_only` policy and violation/error counts. Bond-distance
violations do not stop cycling or alter hit verdicts. The referenced
`pred_min/geometry_report.json` records atom pairs, residues, distances, thresholds
and the structure checksum; unusable coordinates still fail. Historical runs
retain their original policy and may have no geometry report.

MCP v12 adds `backbone_method` (`protein-hunter` or experimental `rfdiffusion3`)
and `rfd3_num_bins` to the NISE request, with 100 starts by default. Initial
RFdiffusion3 backbones and Boltz prediction budgets are reported separately;
the same job digest, code/model provenance and execution lease apply.

MCP v15 adds optional NISE `hotspot_atoms`, `exposed_atoms`, `hotspot_distance`,
`exposure_min_fraction`, `ligand_atom_signature` and `ligand_atoms_generated_for`.
Selected names must come from `scripts/nise/ligand_atoms.py` run in the installed
Boltz environment. Its signature binds the original SMILES, standardized chemical
state and installed mapper. Defaults preserve no user-selected atom requirements.
The shared contract rejects stale/conflicting selections; the campaign validates
the actual molecule and checkpoints structural checks before advancement.


MCP v16 extends ligand NISE with independent `phase0_nesso_screen`,
`phase0_nesso_refine_top_k` (default 1 per lineage) and
`phase0_nesso_expand_top_k` (default 20 total, maximum one per original lineage).
The initial gate remains unscreened. `phase0_gate_seqs` separates gate sampling
from refinement sampling; omitted values retain the old shared count. Advanced
`phase0_sc_ca`, `nise_sc_ca`, `nise_sc_lig` and `nise_ligand_sc_from_cycle` controls
retain the prior cutoffs. Either NESSO switch requires its pinned installation.
No NESSO pLDDT is fabricated: screening ranks P(bind) + (1 - entropy_crop_pl), rejecting entropy outside (0.000001, 1]; Boltz
still supplies the structural and affinity objective. See `docs/NISE.md`.

MCP v18 records the `nesso-pbind-placement-v2` ranking policy in NESSO selection
receipts, including the pocket-cropped protein-ligand entropy field, validity guard and
combined score. Both initial and optimisation shortlists use it. Reports retain
invalid-placement rejections and historical probability-only score provenance.

Native Protein Hunter and RFdiffusion3 ligand campaigns can opt into a broker-owned NESSO shortlist and chosen structural verifier. Protein Hunter screens completed optimized cycles; RFdiffusion3 screens MPNN derivatives before folding. These options are not yet part of the public iterative/RFdiffusion MCP schemas. The results catalog includes `nesso_verification/nesso_screening.csv`.
