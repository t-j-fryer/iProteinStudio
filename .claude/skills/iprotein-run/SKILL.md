---
name: iprotein-run
description: Use iProteinStudio's connected MCP bridge to predict structures, run Protein Hunter, ligand NISE, RFdiffusion3/RFD4 or the Boltz motif beta, review results, and resume saved work. Repository entry point to the portable Studio operating skill; preserves immutable plans, scientific defaults and the shared job queue.
---

# Operate iProteinStudio

Read the [portable operating skill](../../../Sources/iProteinStudio/Resources/pipeline/mcp/skills/iprotein-studio/SKILL.md)
and its [workflow routing reference](../../../Sources/iProteinStudio/Resources/pipeline/mcp/skills/iprotein-studio/references/workflows.md).
These are the client-neutral authority for workflow selection, scientific defaults,
MCP planning, recovery and result interpretation; do not keep a competing copy here.

Prefer the connected bridge's typed tools. Discover its current schemas and
installed engines; call `workflow_guide` before scientific planning. Use existing
user authorization and the immutable plan ID/digest to start authorized work.
Do not bypass the broker through manual shell launches or change a running job's
saved settings. A plan-only request does not authorize inference.

The [assistant guide](../../../docs/AI_ASSISTANTS.md) documents setup, tool access
and GUI/MCP differences. For a specifically requested CLI/developer task, read
[CLI.md](../../../docs/CLI.md) and detect the installed engines first:

```bash
export NANOHUNTER_ROOT="$HOME/.iproteinstudio"
bash "$NANOHUNTER_ROOT/setup_pipeline.sh" --detect
```

Do not substitute installed single-sequence inference for a requested target MSA,
use Fast or whole-chain Full for X-token initialization, reuse stale ligand atom mappings, or
interpret design-engine confidence as independent validation. Do not benchmark
while another GPU workload is active. The portable skill details these rules.

For repository work, follow the root `AGENTS.md`. Record experiments, changes and
material decisions in the project Lab Book, including what was not tested. Read
`Validation/AGENTS.md` before working in that tree. Neither source prototype
recipe tools nor a new skill imply deployment to the user's installed app.

Read the portable skill’s [evidence reference](../../../Sources/iProteinStudio/Resources/pipeline/mcp/skills/iprotein-studio/references/evidence.md) when advising on methods. Full CDR-only starts are supported; RFD3 fixed-framework nanobody generation was tried unsuccessfully and is excluded.
