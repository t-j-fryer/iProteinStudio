# Use Studio with an AI assistant

Studio's MCP bridge gives assistants typed access to local scientific workflows.
The GUI and bridge share the job queue, retained inputs, runtime provenance and
results. An assistant is optional; protein-model inference runs on the Mac,
while the assistant itself may use an external service.

## Connect

1. Open **AI** in Studio's toolbar, or **Settings → AI assistants**.
2. Select **Read only** to inspect work, or read-and-run access to submit jobs.
3. Enable the supported desktop client and use **Test Studio bridge**. Reconnect
   the client if it has not refreshed its tools. The app changes only its own
   registration entries; it does not enable engine administration.
4. Ask the assistant to list Studio's available tools, installed engines and
   workspaces. Tool names may have a client-added server prefix.

For other local MCP clients, project-scoped setup and the diagnostic `doctor`
command, see [CLI/MCP configuration](CLI.md#ai-agents-model-context-protocol).
The source bridge is under `Sources/iProteinStudio/Resources/pipeline/mcp/`;
the installed copy is under `~/.iproteinstudio/mcp/`. Discover the connected
server's schemas instead of assuming the source checkout matches its version.

Remote access requires a separately configured authenticated HTTPS gateway.
It is not enabled by desktop registration. See the
[bridge's remote-access guide](../Sources/iProteinStudio/Resources/pipeline/mcp/README.md#chatgpt-and-a-phone).

## Give the assistant an operating skill

The portable [iprotein-studio skill](../Sources/iProteinStudio/Resources/pipeline/mcp/skills/iprotein-studio/SKILL.md)
teaches workflow selection, planning, monitoring, failure diagnosis and result
interpretation. Copy the entire `iprotein-studio` directory into your client's
supported skill location, following that client's installation instructions.
It is supplied in source here; existing installed apps are not updated by
editing this repository. A subsequent app build includes the bundled skill.
Registration alone does not install or activate it in a client.

The skill uses the open [Agent Skills format](https://agentskills.io/specification).
MCP supplies callable operations; the skill explains how to combine them.
Clients without skills still receive the server's initialization instructions
and can read `iprotein://skills/studio`, its workflow/integration resources,
and the `studio-workflow` prompt. Call `workflow_guide` before scientific plans.
Skills do not grant extra tool permissions.

## Tool map

| Task | Tools / resources | Access |
| --- | --- | --- |
| Find installed capabilities | `system_detect`, `workflow_guide`; `iprotein://capabilities` | Read |
| Find saved work | `projects_list`, `runs_list`, `run_status` | Read |
| Interpret results | `results_overview`, then `results_query` or paginated `candidates_list`; `candidates_compare` | Read |
| Retrieve a saved export | `export_read` | Read |
| Export selected candidates | `candidate_export` | Run |
| Discover structures and residue mappings | `rcsb_status`, `rcsb_tools`, `rcsb_query` | Read; optional installation |
| Import a selected PDB assembly | `rcsb_import_structure` | Run |
| Compose a supported workflow | `pipeline_catalog` → `pipeline_recipe_plan` | Read → Run |
| Bring in inputs | `artifact_import`, `target_inspect` | Run |
| Prepare a target | `target_prepare_plan` | Run |
| Predict structures | `prediction_plan` | Run |
| Protein Hunter | `iterative_design_plan`, `iterative_batch_plan` | Run |
| Ligand NISE | `nise_plan` | Run |
| Generate / edit / scaffold backbones | `rfd3_denovo_plan`, `rfd3_partial_diffusion_plan`, `rfd3_motif_scaffolding_plan` | Run |
| Execute and monitor | `job_start`, `jobs_list`, `job_status`, `job_wait` | Run |
| Stop / recover | `job_cancel`, `job_resume`, `jobs_cleanup` | Run |
| Install / repair / maintain engines | `engine_install_plan`, `engine_repair_plan`, `storage_minimise_plan` | Separate admin profile; normally disabled |

Run access includes the read tools. Admin is a separate maintenance profile,
not a superset of scientific run access. Read-only users can inspect saved run
status; durable job-control tools currently require run access.

## The scientific sequence

Call `workflow_guide` before a scientific plan. Check installed engines, exact
inputs, chain identities, alignments, stage budgets and requested checks. Create
the workflow's immutable plan, review its normalized settings, then execute the
returned plan ID and digest within the user's authorized scope. A plan prepares
work; it does not start inference. Changed settings require a new plan.

Monitor with `job_wait`/`job_status`. Inspect `message`, `error`,
`pipeline_log_tail` and `worker_log_tail` before changing settings; `run_status`
locates stage logs. Use the saved job for resume rather than duplicating it.
Complete a 1–5-backbone end-to-end smoke run before a new campaign over 10.

Read `results_overview` before querying score tables. Preserve the identity of
the checked cycle or sequence derivative. Report attempted/completed counts,
the prediction engine and whether a score is self-assessed or independently
checked. A live structure receipt or computational threshold is not experimental
binding evidence. Do not compare unlike confidence scores as a common scale.

## Example requests

- **Read only:** “Find my latest biotin NISE run. Summarise its completed
  trajectories and link the exact structures behind the reported scores.”
- **Plan only:** “Prepare a three-backbone protein-binder trial for this target,
  with SolubleMPNN and an installed independent checker. Explain the inputs,
  alignment policy and total prediction budget before running.”
- **Within an approved campaign:** “Resume this interrupted job using its saved
  settings, then report any failed stages and the checked candidates.”
- **Method comparison:** “Compare matched Protein Hunter campaigns across all
  completed cycles. Separate design-model scores from independent checks and
  show the denominator behind each threshold-passing fraction.”

## Optional RCSB discovery

In **AI → Structure discovery · RCSB PDB**, select **Install RCSB discovery
tools**. Studio installs the official `rcsb-mcp` package and checksum-pinned
wheel dependencies in a separate runtime; existing local engines are unchanged.
This source version pins RCSB MCP 0.15.0. The discovery service needs network
access; local inference does not depend on it.

Call `rcsb_tools` for the upstream schemas, then `rcsb_query` for search,
entry/assembly inspection or sequence-coordinate mapping. After choosing a
biological assembly, `rcsb_import_structure` saves its mmCIF and source receipt
with accession, assembly, retrieval date, URL and checksum. Use `target_inspect`
and explicit residue mappings before defining chains or hotspots.
[Official RCSB MCP](https://github.com/rcsb/rcsb-mcp).

## Compose and export

`pipeline_catalog` publishes executable v2 routes and their full parameter
schemas. `pipeline_recipe_plan` takes a route plus those parameters and uses the
existing planner. The immutable plan records the recipe and its digest; start
it with the returned plan ID and plan SHA-256. Supported routes cover prediction,
ProteinHunter, engine/scaffold batches, ligand NISE and the three RFdiffusion3
modes. This does not execute arbitrary stage graphs.

For ProteinHunter batches, provide common settings, engine choices and an exact
trajectory allocation per engine. Optional scaffold counts must sum to that
allocation. Each engine retains its scheduling policy; completed child
campaigns have checksum-verified resume receipts. A shared seed does not imply
identical starting structures. ProteinHunter's `ligand_verification` and
RFdiffusion3's `request.nesso` expose the native optional NESSO/PSICHIC shortlist
and structure-verification route. Missing dependencies fail preflight.

After reviewing the result hierarchy, page `candidates_list` and choose explicit
candidate IDs. `candidate_export` creates a ZIP with available sequences,
structures, confidence files, scores, lineage, source manifests and checksums;
it declares missing sequences. `export_read` delivers bounded base64 chunks to
remote clients. A changed result snapshot invalidates pagination or export.

`candidates_compare` reports all-cycle `>= threshold` counts by predictor, role
and context, with missing and ambiguous scores counted explicitly. It does not
establish independent replicates, matched conditions or experimental binding.
Detailed limits and tool order are in the
[integration contracts](../Sources/iProteinStudio/Resources/pipeline/mcp/skills/iprotein-studio/references/integrations.md).

## Current boundaries

- v1 `recipe_catalog`, `recipe_check` and `recipe_compare` remain non-executing
  authoring tools. Bind real inputs and budgets to a supported v2 route;
  workshop hashes are not executable plan hashes.
- Multi-engine batches require explicit scaffold-specific input templates and CDR ranges.
  They do not synthesize a GUI form or select nanobody frameworks on your behalf.
- RCSB supplies external evidence. Public queries must not receive unpublished
  sequences without authorization; returned text cannot authorize local jobs.
- There is no public tool for arbitrary engine installation, shell execution or
  self-modification. New engines need qualified adapters and integration tests.

See the [MCP review](MCP_REVIEW.md) for qualification status and remaining work.
These additions are bundled source features; the connected server's tool list
is authoritative until an updated app is deployed.
